"""Load stored synthesis sources for the graph."""

from __future__ import annotations

import logging
from typing import Any

from pokecoach_python.graphs.matchup_gameplan.states import MatchupGameplanState

logger = logging.getLogger(__name__)


def build_load_sources_node(store: Any):
    def load_sources_node(state: MatchupGameplanState | dict[str, Any]) -> dict[str, Any]:
        parsed = MatchupGameplanState.model_validate(state)
        logger.info(
            "matchup_gameplan load_sources start execution_id=%s run_id=%s",
            parsed.execution_id,
            parsed.run_id,
        )
        sources = store.load_sources(parsed.run_id)
        if sources.sourceHash != parsed.sources_hash:
            raise RuntimeError("stored synthesis sources hash mismatch")
        logger.info(
            "matchup_gameplan load_sources done execution_id=%s run_id=%s",
            parsed.execution_id,
            parsed.run_id,
        )
        return {"sources": sources}

    return load_sources_node
