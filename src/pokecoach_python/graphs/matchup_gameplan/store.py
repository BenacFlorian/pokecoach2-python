"""Persistent storage for prepared synthesis sources."""

from __future__ import annotations

from pokecoach_python.graphs.matchup_gameplan.models import PreparedSources


class MatchupGameplanStore:
    def __init__(self, repository) -> None:
        self._repository = repository

    def create_sources(
        self,
        *,
        run_id,
        token,
        expected_revision: int,
        sources: PreparedSources,
    ) -> None:
        self._repository.create_synthesis_sources(
            run_id,
            token,
            expected_revision=expected_revision,
            sources_payload=sources.model_dump(mode="json"),
        )

    def update_sources(
        self,
        *,
        run_id,
        token,
        expected_revision: int,
        sources: PreparedSources,
    ) -> None:
        self._repository.update_synthesis_sources(
            run_id,
            token,
            expected_revision=expected_revision,
            sources_payload=sources.model_dump(mode="json"),
        )

    def delete_sources(self, *, run_id, token) -> None:
        self._repository.delete_synthesis_sources(run_id, token)

    def load_sources(self, run_id) -> PreparedSources:
        payload = self._repository.load_synthesis_sources(run_id)
        if payload is None:
            raise RuntimeError("synthesis sources not prepared")
        return PreparedSources.model_validate(payload)
