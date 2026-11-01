"""Phase B — conditioned turn-1 openings for each opponent lead from phase A."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import SimulationRequest, TurnOneRecord
from pokecoach_python.engine.seeds import phase_attempt_seed
from pokecoach_python.schemas.analysis_result import (
    LeadPickSection,
    OpponentLeadsSection,
    SimulationResultV2,
    validate_result,
)
from pokecoach_python.workflow.aggregation.leads import canonical_lead
from pokecoach_python.workflow.aggregation.openings import aggregate_openings
from pokecoach_python.workflow.battle_records import canonical_four, validate_turn_one_selection
from pokecoach_python.workflow.budgets import max_attempts, phase_b_valid_budget
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput

_SAMPLING_POLICY = "conditional-back-v1"


def _attempt_seed(run_seed: int, lead_index: int, attempt: int) -> int:
    return phase_attempt_seed(run_seed, "B", lead_index, attempt)


def _load_phase_ac(partial: dict[str, Any]) -> tuple[OpponentLeadsSection, LeadPickSection]:
    if partial.get("completedPhases") != ["A", "C"]:
        raise RuntimeError("phase B requires completed phases A and C")
    payload = {
        "schemaVersion": 2,
        "source": "simulation",
        "openings": None,
        "refinement": None,
        "gameplan": None,
        "winCondition": None,
        **partial,
    }
    try:
        validated = validate_result(payload)
    except ValueError as exc:
        raise RuntimeError("phase B requires valid A+C checkpoint") from exc
    if (
        validated.completedPhases != ["A", "C"]
        or validated.opponentLeads is None
        or validated.leadPick is None
    ):
        raise RuntimeError("phase B requires opponentLeads and leadPick from A+C")
    return validated.opponentLeads, validated.leadPick


def run_phase_b(context: PhaseContext) -> PhaseOutput:
    section_a, lead_pick = _load_phase_ac(context.partial_result)
    selection = lead_pick.selection
    our_four = canonical_four(selection.ourFourSlots)
    our_lead = canonical_lead(selection.ourLeadSlots)
    budget = phase_b_valid_budget(context.profile)
    per_lead_cap = max_attempts(budget)
    total_target = len(section_a.leads) * budget
    done_global = 0
    attempts_total = 0
    rejects_total = 0
    errors_total = 0
    records_by_id: dict[str, list[TurnOneRecord]] = {}

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
                timeout_seconds=context.first_turn_timeout_seconds,
                opponent_lead=lead_slots,
                our_selection=our_four,
                our_lead_slots=our_lead,
            )
            try:
                record = context.engine.first_turn(req)
                if canonical_lead(record.opponent_lead_slots) != lead_slots:
                    rejects += 1
                    rejects_total += 1
                    continue
                validate_turn_one_selection(
                    record.payload,
                    our_four=our_four,
                    our_lead=our_lead,
                    opponent_lead=lead_slots,
                )
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

        records_by_id[entry.id] = valid

    openings = aggregate_openings(
        records_by_id,
        section_a.leads,
        selection,
        sampling_policy=_SAMPLING_POLICY,
    )
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "C", "B"],
        opponentLeads=section_a,
        leadPick=lead_pick,
        openings=openings,
        refinement=None,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            {lead_id: len(recs) for lead_id, recs in records_by_id.items()},
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
            "samplingPolicy": _SAMPLING_POLICY,
            "auditFingerprint": audit_fingerprint,
        },
    )
