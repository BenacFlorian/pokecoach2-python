"""Phase D — global full battles with sampled opponent scenarios."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, SimulationRequest
from pokecoach_python.schemas.analysis_result import SimulationResultV2, validate_result
from pokecoach_python.workflow.aggregation.refinement import (
    aggregate_refinement,
    validate_refinement_battle,
)
from pokecoach_python.workflow.battle_records import sample_key_for_refinement
from pokecoach_python.workflow.budgets import max_attempts, phase_d_valid_budget
from pokecoach_python.workflow.refinement_sampling import (
    OpponentScenario,
    build_refinement_plan,
)
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput

_MAX_ATTEMPTS_PER_INDEX = 8


def _battle_seed(run_seed: int, plan_index: int, attempt: int) -> int:
    digest = hashlib.sha256(f"{run_seed}:D:battle:{plan_index}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _load_phase_acb(partial: dict[str, Any]) -> SimulationResultV2:
    if partial.get("completedPhases") != ["A", "C", "B"]:
        raise RuntimeError("phase D requires completed phases A, C and B")
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
        raise RuntimeError("phase D requires valid A+C+B checkpoint") from exc
    if validated.completedPhases != ["A", "C", "B"]:
        raise RuntimeError("phase D requires completed phases A, C and B")
    if (
        validated.leadPick is None
        or validated.opponentLeads is None
        or validated.openings is None
    ):
        raise RuntimeError("phase D requires leadPick, opponentLeads and openings")
    return validated


def _sampling_meta(
    *,
    plan_index: int,
    scenario: OpponentScenario,
    battle_seed: int,
    attempt: int,
) -> dict[str, Any]:
    return {
        "refinementSampling": {
            "planIndex": plan_index,
            "opponentLeadId": scenario.opponent_lead_id,
            "opponentLeadSlots": list(scenario.opponent_lead_slots),
            "opponentBackPair": list(scenario.opponent_back_pair),
            "battleSeed": battle_seed,
            "attempt": attempt,
        }
    }


def _sort_refinement_battles(battles: list[BattleRecord]) -> list[BattleRecord]:
    indexed: list[tuple[int, BattleRecord]] = []
    for battle in battles:
        meta = battle.meta or {}
        sampling = meta.get("refinementSampling")
        if not isinstance(sampling, dict):
            raise RuntimeError("refinement battle missing refinementSampling meta")
        plan_index = sampling.get("planIndex")
        if not isinstance(plan_index, int):
            raise RuntimeError("refinement battle missing planIndex")
        indexed.append((plan_index, battle))
    indexed.sort(key=lambda item: item[0])
    seen = [idx for idx, _ in indexed]
    if seen != list(range(len(seen))):
        raise RuntimeError("refinement battle indices must be unique and cover 0..N-1")
    return [battle for _, battle in indexed]


def run_phase_d(context: PhaseContext) -> PhaseOutput:
    checkpoint = _load_phase_acb(context.partial_result)
    budget = phase_d_valid_budget(context.profile)
    plan = build_refinement_plan(checkpoint, seed=context.seed, budget=budget)
    selection = plan.our_selection
    attempt_cap = max_attempts(budget, multiplier=8)

    if context.list_battles:
        preexisting = list(context.list_battles())
        if preexisting:
            raise RuntimeError(
                "phase D requires no pre-existing battles for this run "
                f"(found {len(preexisting)})"
            )

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

    stored: list[BattleRecord] = []

    for plan_index in range(budget):
        scenario = plan.scenarios[plan_index]
        accepted: BattleRecord | None = None
        accepted_id: str | None = None
        for attempt in range(1, _MAX_ATTEMPTS_PER_INDEX + 1):
            if attempts_total >= attempt_cap:
                break
            attempts_total += 1
            battle_seed = _battle_seed(context.seed, plan_index, attempt)
            req = SimulationRequest(
                our_snapshot=context.our_snapshot,
                opponent_snapshot=context.opponent_snapshot,
                regulation=context.regulation,
                checkpoint_id=str(context.parameters.get("checkpoint_id", "stub-bc-v1")),
                seed=battle_seed,
                timeout_seconds=context.full_battle_timeout_seconds,
                opponent_lead=scenario.opponent_lead_slots,
                our_selection=selection.ourFourSlots,
                our_lead_slots=selection.ourLeadSlots,
                opponent_back_pair=scenario.opponent_back_pair,
            )
            try:
                record = context.engine.full_battle(req)
            except Exception:
                errors_total += 1
                continue
            if record.outcome == "technical":
                rejects_total += 1
                continue
            try:
                validate_refinement_battle(
                    record,
                    our_selection=selection,
                    scenario=scenario,
                )
            except ValueError:
                rejects_total += 1
                continue
            meta = dict(record.meta or {})
            meta.update(
                _sampling_meta(
                    plan_index=plan_index,
                    scenario=scenario,
                    battle_seed=battle_seed,
                    attempt=attempt,
                )
            )
            record = BattleRecord(
                preview=record.preview,
                turns=record.turns,
                outcome=record.outcome,
                participants=record.participants,
                meta=meta,
            )
            sample_key = sample_key_for_refinement(plan_index)
            try:
                battle_id = insert_fn(record, sample_key)
            except Exception as exc:
                raise RuntimeError("failed to persist refinement battle") from exc
            accepted = record
            accepted_id = battle_id
            break
        if accepted is None or accepted_id is None:
            raise RuntimeError(
                f"phase D budget not met at index {plan_index}: "
                f"(attempts={attempts_total}, rejects={rejects_total}, errors={errors_total})"
            )
        stored.append(accepted)
        battle_ids.append(accepted_id)
        context.report_progress("D", len(stored), budget)

    battles_raw = list(context.list_battles()) if context.list_battles else stored
    if len(battles_raw) != budget:
        raise RuntimeError(
            f"phase D battle count mismatch: stored {len(battles_raw)} expected {budget}"
        )
    battles = _sort_refinement_battles(list(battles_raw))
    for plan_index, battle in enumerate(battles):
        scenario = plan.scenarios[plan_index]
        validate_refinement_battle(
            battle,
            our_selection=selection,
            scenario=scenario,
        )

    refinement = aggregate_refinement(
        battles,
        selection=selection,
        plan=plan,
        battle_ids=battle_ids,
    )
    envelope = SimulationResultV2(
        schemaVersion=2,
        source="simulation",
        completedPhases=["A", "C", "B", "D"],
        opponentLeads=checkpoint.opponentLeads,
        leadPick=checkpoint.leadPick,
        openings=checkpoint.openings,
        refinement=refinement,
        gameplan=None,
        winCondition=None,
    )
    plan_fingerprint = hashlib.sha256(
        json.dumps(
            [
                {
                    "lead": s.opponent_lead_id,
                    "back": list(s.opponent_back_pair),
                }
                for s in plan.scenarios
            ],
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
            "samplingPolicy": "weighted-ab",
            "planFingerprint": plan_fingerprint,
            "scenarioHistogram": [
                row.model_dump(mode="json") for row in refinement.scenarioCounts
            ],
            "auditFingerprint": hashlib.sha256(
                json.dumps(refinement.outcomes, sort_keys=True).encode()
            ).hexdigest()[:16],
        },
    )
