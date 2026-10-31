"""Phase B — turn 1 and back distributions per opponent lead from phase A."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import SimulationRequest, TurnOneRecord
from pokecoach_python.schemas.analysis_result import (
    OpponentLeadEntry,
    OpponentLeadsSection,
    SimulationResultV2,
    Turn1Section,
    validate_result,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.turn_one import aggregate_turn_one
from pokecoach_python.workflow.budgets import max_attempts, phase_b_valid_budget
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput


def _attempt_seed(run_seed: int, lead_index: int, attempt: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:B:{lead_index}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _load_phase_a_section(partial: dict[str, Any]) -> OpponentLeadsSection:
    if partial.get("completedPhases") != ["A"]:
        raise RuntimeError("phase B requires completed phase A checkpoint")
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
        raise RuntimeError("phase B requires completed phase A checkpoint") from exc
    if validated.completedPhases != ["A"] or validated.opponentLeads is None:
        raise RuntimeError("phase B requires completed phase A checkpoint")
    return validated.opponentLeads


def _merge_turn1(
    section_a: OpponentLeadsSection,
    turn1_by_id: dict[str, Turn1Section],
) -> OpponentLeadsSection:
    leads: list[OpponentLeadEntry] = []
    for entry in section_a.leads:
        turn1 = turn1_by_id.get(entry.id)
        if turn1 is None:
            raise RuntimeError(f"missing turn1 for lead {entry.id}")
        leads.append(
            OpponentLeadEntry(
                id=entry.id,
                slots=entry.slots,
                count=entry.count,
                turn1=turn1,
            )
        )
    return OpponentLeadsSection(sampleSize=section_a.sampleSize, leads=leads)


def run_phase_b(context: PhaseContext) -> PhaseOutput:
    section_a = _load_phase_a_section(context.partial_result)
    budget = phase_b_valid_budget(context.profile)
    per_lead_cap = max_attempts(budget)
    total_target = len(section_a.leads) * budget
    done_global = 0
    attempts_total = 0
    rejects_total = 0
    errors_total = 0
    turn1_by_id: dict[str, Turn1Section] = {}

    context.report_progress("B", 0, total_target)

    for lead_index, entry in enumerate(section_a.leads):
        lead_slots = canonical_lead(entry.slots)
        valid: list[TurnOneRecord] = []
        attempts = 0
        rejects = 0
        errors = 0

        while len(valid) < budget and attempts < per_lead_cap:
            attempts += 1
            attempts_total += 1
            req = SimulationRequest(
                our_snapshot=context.our_snapshot,
                opponent_snapshot=context.opponent_snapshot,
                regulation=context.regulation,
                checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
                seed=_attempt_seed(context.seed, lead_index, attempts),
                timeout_seconds=context.preview_timeout_seconds,
                opponent_lead=lead_slots,
            )
            try:
                record = context.engine.first_turn(req)
                if canonical_lead(record.opponent_lead_slots) != lead_slots:
                    rejects += 1
                    rejects_total += 1
                    continue
                valid.append(record)
                done_global += 1
                context.report_progress("B", done_global, total_target)
            except ValueError:
                rejects += 1
                rejects_total += 1
            except Exception:
                errors += 1
                errors_total += 1

        if len(valid) < budget:
            raise RuntimeError(
                f"phase B budget not met for {entry.id}: {len(valid)}/{budget} "
                f"(attempts={attempts}, rejects={rejects}, errors={errors})"
            )

        turn1_by_id[entry.id] = aggregate_turn_one(valid, lead_slots)

    merged = _merge_turn1(section_a, turn1_by_id)
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "B"],
        opponentLeads=merged,
        leadPick=None,
        refinement=None,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            {lead_id: turn1.sampleSize for lead_id, turn1 in turn1_by_id.items()},
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    return PhaseOutput(
        phase="B",
        result=envelope,
        execution_slice={
            "phase": "B",
            "attempts": attempts_total,
            "rejects": rejects_total,
            "errors": errors_total,
            "leadsProcessed": len(section_a.leads),
            "budgetPerLead": budget,
            "auditFingerprint": audit_fingerprint,
        },
    )
