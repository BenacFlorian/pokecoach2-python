"""Audit contrefactuel du conditionnement team preview."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pokecoach_python.engine.contracts import EngineAdapter, PreviewRecord, SimulationRequest
from pokecoach_python.workflow.battle_records import canonical_four, four_slots_leads_first

PairStatus = Literal[
    "observation-and-selection-differ",
    "observation-differs-selection-stable",
    "observation-not-different",
]


@dataclass(frozen=True)
class NamedSnapshot:
    name: str
    snapshot: dict[str, Any]


@dataclass(frozen=True)
class OpponentAuditSample:
    name: str
    seed: int
    our_four: tuple[int, int, int, int]
    our_lead: tuple[int, int]
    our_observation_fingerprint: str


@dataclass(frozen=True)
class OpponentAuditSummary:
    name: str
    samples: int
    four_distribution: dict[str, float]
    selection_distribution: dict[str, float]
    unique_observation_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class OpponentPairComparison:
    opponent_a: str
    opponent_b: str
    status: PairStatus
    paired_selection_changes: int
    paired_selection_change_rate: float
    total_variation_distance: float


@dataclass(frozen=True)
class ConditioningAuditReport:
    audit_version: Literal[1]
    regulation: str
    checkpoint_id: str
    base_seed: int
    samples: int
    opponents: tuple[OpponentAuditSummary, ...]
    pair_comparisons: tuple[OpponentPairComparison, ...]


def canonical_four_slots(four: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return canonical_four(four)


def selection_key(
    four: tuple[int, int, int, int],
    lead: tuple[int, int],
) -> str:
    display = four_slots_leads_first(four, lead)
    return f"{display}/{lead}"


def four_key(four: tuple[int, int, int, int]) -> str:
    return ",".join(str(slot) for slot in canonical_four_slots(four))


def count_four_distribution(
    rows: Sequence[OpponentAuditSample],
) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts[four_key(row.our_four)] += 1
    total = len(rows)
    return {key: counts[key] / total for key in sorted(counts)}


def count_selection_distribution(
    rows: Sequence[OpponentAuditSample],
) -> dict[str, float]:
    counts: Counter[str] = Counter()
    for row in rows:
        lead = row.our_lead
        counts[selection_key(row.our_four, lead)] += 1
    total = len(rows)
    return {key: counts[key] / total for key in sorted(counts)}


def total_variation_distance(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(key, 0.0) - q.get(key, 0.0)) for key in keys)


def _preview_sample(record: PreviewRecord, *, seed: int, name: str) -> OpponentAuditSample:
    if record.our_four_slots is None:
        raise ValueError("preview missing ourFourSlots")
    meta = record.meta or {}
    fp = meta.get("ourObservationFingerprint")
    if not isinstance(fp, str) or not fp.startswith("sha256-v1:"):
        raise ValueError("preview missing ourObservationFingerprint")
    lead = record.our_lead_slots
    if lead is None:
        raise ValueError("preview missing ourLeadSlots")
    return OpponentAuditSample(
        name=name,
        seed=seed,
        our_four=record.our_four_slots,
        our_lead=lead,
        our_observation_fingerprint=fp,
    )


def run_conditioning_audit(
    engine: EngineAdapter,
    *,
    our_snapshot: dict[str, Any],
    opponents: Sequence[NamedSnapshot],
    regulation: str,
    checkpoint_id: str,
    base_seed: int,
    samples: int,
    timeout_seconds: float,
) -> ConditioningAuditReport:
    if len(opponents) < 2:
        raise ValueError("at least two opponents required")
    if samples < 2:
        raise ValueError("samples must be >= 2")

    by_opponent: dict[str, list[OpponentAuditSample]] = {o.name: [] for o in opponents}
    for index in range(samples):
        seed = base_seed + index
        for opponent in opponents:
            record = engine.preview(
                SimulationRequest(
                    our_snapshot=our_snapshot,
                    opponent_snapshot=opponent.snapshot,
                    regulation=regulation,
                    checkpoint_id=checkpoint_id,
                    seed=seed,
                    timeout_seconds=timeout_seconds,
                )
            )
            by_opponent[opponent.name].append(
                _preview_sample(record, seed=seed, name=opponent.name)
            )

    summaries: list[OpponentAuditSummary] = []
    for opponent in opponents:
        rows = by_opponent[opponent.name]
        fps = tuple(sorted({row.our_observation_fingerprint for row in rows}))
        summaries.append(
            OpponentAuditSummary(
                name=opponent.name,
                samples=len(rows),
                four_distribution=count_four_distribution(rows),
                selection_distribution=count_selection_distribution(rows),
                unique_observation_fingerprints=fps,
            )
        )

    pair_rows: list[OpponentPairComparison] = []
    for i, left in enumerate(opponents):
        for right in opponents[i + 1 :]:
            left_rows = {row.seed: row for row in by_opponent[left.name]}
            right_rows = {row.seed: row for row in by_opponent[right.name]}
            changes = 0
            fp_equal = True
            for seed in range(base_seed, base_seed + samples):
                lrow = left_rows[seed]
                rrow = right_rows[seed]
                if lrow.our_observation_fingerprint != rrow.our_observation_fingerprint:
                    fp_equal = False
                if four_key(lrow.our_four) != four_key(rrow.our_four):
                    changes += 1
            change_rate = changes / samples
            tv = total_variation_distance(
                count_four_distribution(list(left_rows.values())),
                count_four_distribution(list(right_rows.values())),
            )
            if fp_equal:
                status: PairStatus = "observation-not-different"
            elif changes > 0:
                status = "observation-and-selection-differ"
            else:
                status = "observation-differs-selection-stable"
            pair_rows.append(
                OpponentPairComparison(
                    opponent_a=left.name,
                    opponent_b=right.name,
                    status=status,
                    paired_selection_changes=changes,
                    paired_selection_change_rate=change_rate,
                    total_variation_distance=tv,
                )
            )

    return ConditioningAuditReport(
        audit_version=1,
        regulation=regulation,
        checkpoint_id=checkpoint_id,
        base_seed=base_seed,
        samples=samples,
        opponents=tuple(summaries),
        pair_comparisons=tuple(pair_rows),
    )


def report_exit_code(report: ConditioningAuditReport) -> int:
    if any(p.status == "observation-not-different" for p in report.pair_comparisons):
        return 1
    return 0


def report_to_jsonable(report: ConditioningAuditReport) -> dict[str, Any]:
    return {
        "auditVersion": report.audit_version,
        "regulation": report.regulation,
        "checkpointId": report.checkpoint_id,
        "baseSeed": report.base_seed,
        "samples": report.samples,
        "opponents": [
            {
                "name": row.name,
                "samples": row.samples,
                "fourDistribution": row.four_distribution,
                "selectionDistribution": row.selection_distribution,
                "uniqueObservationFingerprints": list(row.unique_observation_fingerprints),
            }
            for row in report.opponents
        ],
        "pairComparisons": [
            {
                "opponentA": row.opponent_a,
                "opponentB": row.opponent_b,
                "status": row.status,
                "pairedSelectionChanges": row.paired_selection_changes,
                "pairedSelectionChangeRate": row.paired_selection_change_rate,
                "totalVariationDistance": row.total_variation_distance,
            }
            for row in report.pair_comparisons
        ],
    }
