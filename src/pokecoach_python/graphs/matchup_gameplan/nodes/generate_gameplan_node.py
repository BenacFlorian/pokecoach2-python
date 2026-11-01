"""Generate the matchup strategy from prepared sources."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from pokecoach_python.graphs.matchup_gameplan.models import validate_strategy_against_sources
from pokecoach_python.graphs.matchup_gameplan.prompts.generate_gameplan_prompt import (
    get_generate_gameplan_prompt,
)
from pokecoach_python.graphs.matchup_gameplan.states import MatchupGameplanState

logger = logging.getLogger(__name__)


def build_generate_gameplan_node(client: Any):
    def generate_gameplan_node(state: MatchupGameplanState | dict[str, Any]) -> dict[str, Any]:
        parsed = MatchupGameplanState.model_validate(state)
        if parsed.sources is None:
            raise RuntimeError("sources must be loaded before generation")
        logger.info(
            "matchup_gameplan generate_gameplan start execution_id=%s run_id=%s",
            parsed.execution_id,
            parsed.run_id,
        )
        prompt = get_generate_gameplan_prompt(
            parsed.sources,
            output_locale=parsed.output_locale,
        )
        human_message = HumanMessage(content=prompt)
        strategy = client.generate(parsed.sources, [human_message])
        strategy = validate_strategy_against_sources(strategy, parsed.sources)
        logger.info(
            "matchup_gameplan generate_gameplan done execution_id=%s run_id=%s",
            parsed.execution_id,
            parsed.run_id,
        )
        return {"strategy": strategy}

    return generate_gameplan_node
