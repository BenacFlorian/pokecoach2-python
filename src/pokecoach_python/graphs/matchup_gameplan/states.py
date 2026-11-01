"""LangGraph state for matchup gameplan synthesis."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict

from pokecoach_python.graphs.matchup_gameplan.models import PreparedSources, StrategyOutput
from pokecoach_python.llm.output_locale import OutputLocale


class MatchupGameplanState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # metadata
    execution_id: str | None = None
    executor_label: str = "matchup_gameplan"

    # inputs
    run_id: str
    sources_hash: str
    output_locale: OutputLocale = "fr"

    # node outputs
    sources: PreparedSources | None = None
    strategy: StrategyOutput | None = None

    @classmethod
    def build(
        cls,
        *,
        run_id: uuid.UUID | str,
        sources_hash: str,
        execution_id: str,
        output_locale: OutputLocale = "fr",
    ) -> MatchupGameplanState:
        return cls(
            execution_id=execution_id,
            run_id=str(run_id),
            sources_hash=sources_hash,
            output_locale=output_locale,
        )
