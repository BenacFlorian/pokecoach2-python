"""Phase C — full battles per top opponent lead and deterministic lead-pick."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, SimulationRequest
from pokecoach_python.schemas.analysis_result import (
    OpponentLeadsSection,
    SimulationResultV2,
    validate_result,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.selections import aggregate_selections
from pokecoach_python.workflow.battle_records import sample_key_for_lead, validate_terminal_battle
from pokecoach_python.workflow.budgets import (
    max_attempts,
    phase_c_valid_budget,
    studied_opponent_lead_count,
)
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput

_RULE_VERSION = "selection-v1"


def _attempt_seed(run_seed: int, lead_index: int, sample_index: int, attempt: int) -> int:
    digest = hashlib.sha256(
        f"{run_seed}:C:{lead_index}:{sample_index}:{attempt}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _load_phase_ab(partial: dict[str, Any]) -> OpponentLeadsSection:
    if partial.get("completedPhases") != ["A", "B"]:
        raise RuntimeError("phase C requires completed phases A and B")
    payload = {
        "schemaVersion": 2,
        "source": "simulation",
        "leadPick": None,
        "refinement": None,
        "gameplan": None,
        "winCondition": None,
        **partial,
    }
    try:
        validated = validate_result(payload)
    except ValueError as exc:
        raise RuntimeError("phase C requires valid A+B checkpoint") from exc
    if validated.completedPhases != ["A", "B"] or validated.opponentLeads is None:
        raise RuntimeError("phase C requires opponentLeads from A+B")
    return validated.opponentLeads


def _persist_battle(
    insert_fn,
    record: BattleRecord,
    lead_slots: tuple[int, int],
    sample_key: str,
) -> None:
    validate_terminal_battle(record, expected_opponent_lead=lead_slots)
    insert_fn(record, sample_key)


def run_phase_c(context: PhaseContext) -> PhaseOutput:
    section_ab = _load_phase_ab(context.partial_result)
    top_n = studied_opponent_lead_count(context.parameters)
    studied = section_ab.leads[: min(top_n, len(section_ab.leads))]
    budget = phase_c_valid_budget(context.profile)
    per_lead_cap = max_attempts(budget)
    total_target = len(studied) * budget
    done_global = 0
    attempts_total = 0
    rejects_total = 0
    errors_total = 0
    local_battles: list[BattleRecord] = []

    def default_insert(record: BattleRecord, _sample_key: str) -> None:
        local_battles.append(record)

    insert_fn = context.insert_battle or default_insert

    context.report_progress("C", 0, total_target)

    for lead_index, entry in enumerate(studied):
        lead_slots = canonical_lead(entry.slots)
        valid_count = 0
        sample_index = 0
        attempts = 0

        while valid_count < budget and attempts < per_lead_cap:
            attempts += 1
            attempts_total += 1
            req = SimulationRequest(
                our_snapshot=context.our_snapshot,
                opponent_snapshot=context.opponent_snapshot,
                regulation=context.regulation,
                checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
                seed=_attempt_seed(context.seed, lead_index, sample_index, attempts),
                timeout_seconds=context.preview_timeout_seconds,
                opponent_lead=lead_slots,
            )
            try:
                record = context.engine.full_battle(req)
                if record.outcome == "technical":
                    rejects_total += 1
                    continue
                validate_terminal_battle(record, expected_opponent_lead=lead_slots)
                sample_key = sample_key_for_lead(lead_slots, valid_count)
                _persist_battle(insert_fn, record, lead_slots, sample_key)
                valid_count += 1
                sample_index += 1
                done_global += 1
                context.report_progress("C", done_global, total_target)
            except ValueError:
                rejects_total += 1
            except Exception:
                errors_total += 1

        if valid_count < budget:
            raise RuntimeError(
                f"phase C budget not met for {entry.id}: {valid_count}/{budget} "
                f"(attempts={attempts}, rejects={rejects_total}, errors={errors_total})"
            )

    battles = list(context.list_battles()) if context.list_battles else local_battles
    expected_count = len(studied) * budget
    if len(battles) != expected_count:
        raise RuntimeError(
            f"phase C battle count mismatch: stored {len(battles)} expected {expected_count}"
        )

    lead_pick = aggregate_selections(
        battles,
        section_ab,
        rule_version=_RULE_VERSION,
        top_n=top_n,
    )
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "B", "C"],
        opponentLeads=section_ab,
        leadPick=lead_pick,
        refinement=None,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "battles": len(battles),
                "selection": list(lead_pick.selection.ourFourSlots),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    return PhaseOutput(
        phase="C",
        result=envelope,
        execution_slice={
            "phase": "C",
            "attempts": attempts_total,
            "rejects": rejects_total,
            "errors": errors_total,
            "studiedLeads": len(studied),
            "budgetPerLead": budget,
            "selectionRuleVersion": _RULE_VERSION,
            "auditFingerprint": audit_fingerprint,
        },
    )
