"""Entrypoint for invoking the matchup gameplan graph."""

from __future__ import annotations

import uuid

from pokecoach_python.graphs.matchup_gameplan.graphs import create_matchup_gameplan_graph
from pokecoach_python.graphs.matchup_gameplan.models import StrategyOutput
from pokecoach_python.graphs.matchup_gameplan.states import MatchupGameplanState
from pokecoach_python.llm.output_locale import OutputLocale


def invoke_matchup_gameplan(
    *,
    run_id: uuid.UUID | str,
    sources_hash: str,
    execution_id: str,
    store,
    client,
    output_locale: OutputLocale = "fr",
) -> StrategyOutput:
    graph = create_matchup_gameplan_graph(store, client)
    state = MatchupGameplanState.build(
        run_id=run_id,
        sources_hash=sources_hash,
        execution_id=execution_id,
        output_locale=output_locale,
    )
    result = graph.invoke(state.model_dump(mode="json"))
    final_state = MatchupGameplanState.model_validate(result)
    if final_state.strategy is None:
        raise RuntimeError("strategy graph completed without strategy output")
    return final_state.strategy
