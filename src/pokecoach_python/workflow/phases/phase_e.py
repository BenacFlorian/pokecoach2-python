"""Phase E - structured synthesis from Phase D battles."""

from __future__ import annotations

import uuid
from typing import Any

from pokecoach_python.engine.provenance import assert_real_battles_eligible
from pokecoach_python.graphs.matchup_gameplan.invokation import invoke_matchup_gameplan
from pokecoach_python.graphs.matchup_gameplan.store import MatchupGameplanStore
from pokecoach_python.llm.client import StrategyClient
from pokecoach_python.llm.output_locale import parse_output_locale
from pokecoach_python.llm.source_preparation import prepare_sources
from pokecoach_python.llm.source_selection import validate_source_selection
from pokecoach_python.llm.strategy_references import (
    render_strategy_references,
    validate_strategy_reference_tokens,
    validate_strategy_team_references,
)
from pokecoach_python.schemas.analysis_result import SimulationResultV2, validate_result
from pokecoach_python.workflow.types import PhaseContext, PhaseOutput


def run_phase_e(context: PhaseContext) -> PhaseOutput:
    checkpoint = _load_phase_acbd(context.partial_result)
    if context.settings is None:
        raise RuntimeError("phase E requires settings")
    if context.analysis_repository is None:
        raise RuntimeError("phase E requires analysis repository")
    if context.list_d_battles is None:
        raise RuntimeError("phase E requires identified D battles")
    settings = context.settings
    store = context.synthesis_store or MatchupGameplanStore(context.analysis_repository)
    client = context.synthesis_client or StrategyClient(settings)
    context.report_progress("synthesis", 0, 1)
    stored = list(context.list_d_battles())
    expected_ids = list(checkpoint.refinement.battleIds) if checkpoint.refinement else []
    if len(stored) != len(expected_ids):
        raise RuntimeError("phase E requires every persisted D battle from refinement")
    actual_ids = [battle.id for battle in stored]
    if set(actual_ids) != set(expected_ids):
        raise RuntimeError("phase E D battle ids do not match refinement.battleIds")
    assert_real_battles_eligible(context.run_provenance, [battle.record for battle in stored])
    selection = checkpoint.leadPick.selection
    our_four = tuple(selection.ourFourSlots)
    prepared = prepare_sources(
        stored,
        snapshots=(context.our_snapshot, context.opponent_snapshot),
        token_budget=settings.synthesis_source_token_budget(),
        output_token_budget=settings.synthesis_output_token_limit(),
        model_name=settings.synthesis_model_name(),
        our_four=our_four,  # type: ignore[arg-type]
    )
    validate_source_selection(prepared, selection)
    try:
        store.create_sources(
            run_id=context.run_id,
            token=context.lease_token,
            expected_revision=context.result_revision,
            sources=prepared,
        )
    except RuntimeError as exc:
        if "already exist" not in str(exc):
            raise
        store.update_sources(
            run_id=context.run_id,
            token=context.lease_token,
            expected_revision=context.result_revision,
            sources=prepared,
        )
    execution_id = f"synthesis-{uuid.uuid4()}"
    output_locale = parse_output_locale(context.parameters.get("locale"))
    strategy = invoke_matchup_gameplan(
        run_id=context.run_id,
        sources_hash=prepared.sourceHash,
        execution_id=execution_id,
        store=store,
        client=client,
        output_locale=output_locale,
    )
    validate_strategy_reference_tokens(strategy, our_four=our_four)  # type: ignore[arg-type]
    strategy = render_strategy_references(
        strategy,
        snapshots=(context.our_snapshot, context.opponent_snapshot),
    )
    validate_strategy_team_references(
        strategy,
        our_snapshot=context.our_snapshot,
        our_four=our_four,  # type: ignore[arg-type]
    )
    context.report_progress("synthesis", 1, 1)
    result = assemble_complete_result(context.partial_result, strategy.model_dump(mode="json"))
    invocation_meta = dict(client.last_invocation or {})
    invocation_meta["executionId"] = execution_id
    invocation_meta["selectedBattleIds"] = list(prepared.manifest.selectedBattleIds)
    execution_slice = {
        "phase": "synthesis",
        "sourcesHash": prepared.sourceHash,
        "selectedBattleIds": list(prepared.manifest.selectedBattleIds),
        "tokenEstimate": prepared.tokenEstimate,
        "model": settings.synthesis_model_name(),
        "outputLocale": output_locale,
    }
    return PhaseOutput(
        phase="synthesis",
        result=result,
        execution_slice=execution_slice,
        metadata_patch={
            "phases": {"synthesis": execution_slice},
            "synthesis": {"invocation": invocation_meta},
        },
    )


def assemble_complete_result(previous: dict[str, Any], strategy: dict[str, Any]) -> SimulationResultV2:
    payload = dict(previous)
    payload["completedPhases"] = ["A", "C", "B", "D", "synthesis"]
    payload["gameplan"] = strategy["gameplan"]
    payload["winCondition"] = strategy["winCondition"]
    return validate_result(payload, require_complete=True)


def _load_phase_acbd(partial: dict[str, Any]) -> SimulationResultV2:
    payload = {
        "schemaVersion": 2,
        "source": "simulation",
        "gameplan": None,
        "winCondition": None,
        **partial,
    }
    try:
        validated = validate_result(payload)
    except ValueError as exc:
        raise RuntimeError("phase E requires valid A+C+B+D checkpoint") from exc
    if validated.completedPhases != ["A", "C", "B", "D"]:
        raise RuntimeError("phase E requires completed phases A, C, B and D")
    if (
        validated.opponentLeads is None
        or validated.leadPick is None
        or validated.openings is None
        or validated.refinement is None
    ):
        raise RuntimeError("phase E requires A/C/B/D sections")
    return validated
