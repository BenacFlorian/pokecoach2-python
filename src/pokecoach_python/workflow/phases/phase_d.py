"""Phase D — targeted full battles with fixed selections on both sides."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, SimulationRequest
from pokecoach_python.schemas.analysis_result import SimulationResultV2, validate_result
from pokecoach_python.workflow.aggregation.refinement import (
    aggregate_refinement,
    select_refinement_configuration,
    studied_lead_count_from_parameters,
    validate_refinement_battle,
)
from pokecoach_python.workflow.battle_records import sample_key_for_refinement
from pokecoach_python.workflow.budgets import max_attempts, phase_d_valid_budget
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput


def _attempt_seed(run_seed: int, sample_index: int, attempt: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:D:{sample_index}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _load_phase_abc(partial: dict[str, Any]) -> SimulationResultV2:
    if partial.get("completedPhases") != ["A", "B", "C"]:
        raise RuntimeError("phase D requires completed phases A, B and C")
    payload = {
        "schemaVersion": 2,
        "source": "simulation",
        "refinement": None,
        "gameplan": None,
        "winCondition": None,
        **partial,
    }
    try:
        validated = validate_result(payload)
    except ValueError as exc:
        raise RuntimeError("phase D requires valid A+B+C checkpoint") from exc
    if validated.completedPhases != ["A", "B", "C"]:
        raise RuntimeError("phase D requires completed phases A, B and C")
    if validated.leadPick is None or validated.opponentLeads is None:
        raise RuntimeError("phase D requires leadPick and opponentLeads")
    return validated


def run_phase_d(context: PhaseContext) -> PhaseOutput:
    checkpoint = _load_phase_abc(context.partial_result)
    config = select_refinement_configuration(
        checkpoint,
        studied_lead_count=studied_lead_count_from_parameters(context.parameters),
    )
    budget = phase_d_valid_budget(context.profile)
    attempt_cap = max_attempts(budget, multiplier=8)
    done = 0
    attempts_total = 0
    rejects_total = 0
    errors_total = 0
    local_battles: list[BattleRecord] = []
    battle_ids: list[str] = []

    def default_insert(record: BattleRecord, _sample_key: str) -> str:
        local_battles.append(record)
        return f"local-{len(local_battles)}"

    insert_fn = context.insert_battle or default_insert

    context.report_progress("D", 0, budget)

    sample_index = 0
    while done < budget and attempts_total < attempt_cap:
        attempts_total += 1
        req = SimulationRequest(
            our_snapshot=context.our_snapshot,
            opponent_snapshot=context.opponent_snapshot,
            regulation=context.regulation,
            checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
            seed=_attempt_seed(context.seed, sample_index, attempts_total),
            timeout_seconds=context.preview_timeout_seconds,
            opponent_lead=config.opponent_lead,
            our_selection=config.our_four,
            our_lead_slots=config.our_lead,
            opponent_back_pair=config.opponent_back,
        )
        try:
            record = context.engine.full_battle(req)
            if record.outcome == "technical":
                rejects_total += 1
                continue
            validate_refinement_battle(record, config)
            sample_key = sample_key_for_refinement(done)
            battle_id = insert_fn(record, sample_key)
            battle_ids.append(battle_id)
            done += 1
            sample_index += 1
            context.report_progress("D", done, budget)
        except ValueError:
            rejects_total += 1
        except Exception:
            errors_total += 1

    if done < budget:
        raise RuntimeError(
            f"phase D budget not met: {done}/{budget} "
            f"(attempts={attempts_total}, rejects={rejects_total}, errors={errors_total})"
        )

    battles = list(context.list_battles()) if context.list_battles else local_battles
    if len(battles) != budget:
        raise RuntimeError(
            f"phase D battle count mismatch: stored {len(battles)} expected {budget}"
        )

    refinement = aggregate_refinement(battles, config, battle_ids=battle_ids)
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "B", "C", "D"],
        opponentLeads=checkpoint.opponentLeads,
        leadPick=checkpoint.leadPick,
        refinement=refinement,
        gameplan=None,
        winCondition=None,
    )
    audit_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "battles": len(battles),
                "outcomes": refinement.outcomes,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    return PhaseOutput(
        phase="D",
        result=envelope,
        execution_slice={
            "phase": "D",
            "attempts": attempts_total,
            "rejects": rejects_total,
            "errors": errors_total,
            "budget": budget,
            "opponentLeadId": config.opponent_lead_id,
            "auditFingerprint": audit_fingerprint,
        },
    )
