"""Deterministic opponent scenario planning for global phase D refinement."""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass

from pokecoach_python.schemas.analysis_result import (
    LeadSelection,
    OpeningStudyEntry,
    SimulationResultV2,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead


@dataclass(frozen=True)
class OpponentScenario:
    opponent_lead_id: str
    opponent_lead_slots: tuple[int, int]
    opponent_back_pair: tuple[int, int]


@dataclass(frozen=True)
class RefinementSamplingPlan:
    our_selection: LeadSelection
    scenarios: tuple[OpponentScenario, ...]


def _scenario_seed(run_seed: int, index: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:D:scenario:{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _opening_for_lead(
    result: SimulationResultV2,
    lead_id: str,
    lead_slots: tuple[int, int],
) -> OpeningStudyEntry:
    if result.openings is None:
        raise ValueError("phase D requires openings from phase B")
    canon = canonical_lead(lead_slots)
    for entry in result.openings.byOpponentLead:
        if entry.opponentLeadId != lead_id:
            continue
        if canonical_lead(entry.opponentLeadSlots) != canon:
            raise ValueError(
                f"openings entry slots mismatch for lead {lead_id}: "
                f"A has {lead_slots}, B has {entry.opponentLeadSlots}"
            )
        return entry
    raise ValueError(f"openings missing entry for lead {lead_id}")


def _parse_back_pair_row(row: object, *, lead_slots: tuple[int, int]) -> tuple[tuple[int, int], int]:
    if not isinstance(row, dict):
        raise ValueError("backPairs row must be an object")
    value = row.get("value")
    count = row.get("count")
    sample = row.get("sampleSize")
    if not isinstance(count, int) or count < 0:
        raise ValueError("backPairs count must be a non-negative integer")
    if isinstance(count, float) and count != int(count):
        raise ValueError("backPairs count must be integral")
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("backPairs value must be a pair of slots")
    if not all(isinstance(s, int) and 0 <= s <= 5 for s in value):
        raise ValueError("back pair slots must be integers 0-5")
    pair = canonical_lead((int(value[0]), int(value[1])))
    opp = canonical_lead(lead_slots)
    if pair[0] in opp or pair[1] in opp:
        raise ValueError("back pair must be disjoint from opponent lead slots")
    if pair[0] == pair[1]:
        raise ValueError("back pair slots must be distinct")
    if isinstance(sample, int) and sample < 0:
        raise ValueError("backPairs sampleSize must be non-negative")
    return pair, count


def _validated_back_distribution(
    entry: OpeningStudyEntry,
    *,
    lead_id: str,
) -> list[tuple[tuple[int, int], int]]:
    if entry.sampleSize <= 0:
        raise ValueError(f"openings sampleSize must be positive for lead {lead_id}")
    if not entry.backPairs:
        raise ValueError(f"openings require backPairs for lead {lead_id}")
    seen: set[tuple[int, int]] = set()
    rows: list[tuple[tuple[int, int], int]] = []
    total = 0
    for row in entry.backPairs:
        pair, count = _parse_back_pair_row(row, lead_slots=entry.opponentLeadSlots)
        if count <= 0:
            continue
        if pair in seen:
            raise ValueError(f"duplicate back pair after canonicalization for lead {lead_id}")
        seen.add(pair)
        rows.append((pair, count))
        total += count
    if total <= 0:
        raise ValueError(f"no positive back counts for lead {lead_id}")
    if total != entry.sampleSize:
        raise ValueError(
            f"backPairs counts must sum to openings sampleSize for lead {lead_id}"
        )
    rows.sort(key=lambda item: item[0])
    return rows


def validate_refinement_sampling_inputs(result: SimulationResultV2) -> None:
    if result.leadPick is None or result.opponentLeads is None or result.openings is None:
        raise ValueError("phase D requires leadPick, opponentLeads and openings")
    if result.openings.selection != result.leadPick.selection:
        raise ValueError("openings.selection must match leadPick.selection")
    section = result.opponentLeads
    if section.sampleSize <= 0:
        raise ValueError("opponentLeads sampleSize must be positive")
    if not section.leads:
        raise ValueError("opponentLeads must not be empty")
    total_a = 0
    seen_ids: set[str] = set()
    seen_slots: set[tuple[int, int]] = set()
    for entry in section.leads:
        if entry.count < 0:
            raise ValueError("opponent lead count must be non-negative")
        if isinstance(entry.count, float) and entry.count != int(entry.count):
            raise ValueError("opponent lead count must be integral")
        if entry.id in seen_ids:
            raise ValueError(f"duplicate opponent lead id {entry.id}")
        seen_ids.add(entry.id)
        canon = canonical_lead(entry.slots)
        if canon in seen_slots:
            raise ValueError("duplicate opponent lead slots in A")
        seen_slots.add(canon)
        total_a += entry.count
        if entry.count <= 0:
            continue
        opening = _opening_for_lead(result, entry.id, entry.slots)
        _validated_back_distribution(opening, lead_id=entry.id)
    if total_a != section.sampleSize:
        raise ValueError("opponentLeads counts must sum to sampleSize")


def _weighted_scenarios(result: SimulationResultV2) -> list[tuple[OpponentScenario, int]]:
    validate_refinement_sampling_inputs(result)
    weighted: list[tuple[OpponentScenario, int]] = []
    for entry in result.opponentLeads.leads:  # type: ignore[union-attr]
        if entry.count <= 0:
            continue
        opening = _opening_for_lead(result, entry.id, entry.slots)
        backs = _validated_back_distribution(opening, lead_id=entry.id)
        for back_pair, back_count in backs:
            weight = entry.count * back_count
            if weight <= 0:
                continue
            scenario = OpponentScenario(
                opponent_lead_id=entry.id,
                opponent_lead_slots=entry.slots,
                opponent_back_pair=back_pair,
            )
            weighted.append((scenario, weight))
    if not weighted:
        raise ValueError("no positive-weight opponent scenarios for refinement")
    weighted.sort(
        key=lambda item: (
            item[0].opponent_lead_id,
            item[0].opponent_lead_slots,
            item[0].opponent_back_pair,
        )
    )
    return weighted


def _pick_weighted(rng: random.Random, weighted: Sequence[tuple[OpponentScenario, int]]) -> OpponentScenario:
    total = sum(weight for _, weight in weighted)
    if total <= 0:
        raise ValueError("empty scenario weight total")
    roll = rng.randrange(total)
    acc = 0
    for scenario, weight in weighted:
        acc += weight
        if roll < acc:
            return scenario
    return weighted[-1][0]


def build_refinement_plan(
    result: SimulationResultV2,
    *,
    seed: int,
    budget: int,
) -> RefinementSamplingPlan:
    if budget < 1:
        raise ValueError("refinement budget must be positive")
    weighted = _weighted_scenarios(result)
    selection = result.leadPick.selection  # type: ignore[union-attr]
    scenarios: list[OpponentScenario] = []
    for index in range(budget):
        rng = random.Random(_scenario_seed(seed, index))
        scenarios.append(_pick_weighted(rng, weighted))
    return RefinementSamplingPlan(our_selection=selection, scenarios=tuple(scenarios))
