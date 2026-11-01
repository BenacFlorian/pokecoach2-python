"""Integration-style tests for synthesis source persistence (repository contract)."""

from __future__ import annotations

import uuid

import pytest

from pokecoach_python.graphs.matchup_gameplan.models import PreparedSources
from pokecoach_python.graphs.matchup_gameplan.store import MatchupGameplanStore
from pokecoach_python.llm.source_preparation import prepare_sources
from tests.unit.phase_e_fixtures import make_snapshots, make_stored_battle


class _FakeSynthesisRepo:
    def __init__(self) -> None:
        self.payload: dict | None = None
        self.invoked = False

    def create_synthesis_sources(self, run_id, token, *, expected_revision, sources_payload):
        self.payload = sources_payload
        self.expected_revision = expected_revision
        self.run_id = run_id
        self.token = token

    def update_synthesis_sources(self, run_id, token, *, expected_revision, sources_payload):
        self.payload = sources_payload

    def delete_synthesis_sources(self, run_id, token):
        self.payload = None

    def load_synthesis_sources(self, run_id):
        return self.payload


def test_store_create_and_load_roundtrip():
    repo = _FakeSynthesisRepo()
    store = MatchupGameplanStore(repo)
    battles = [
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(0,),
            opponent_survivors=(),
        ),
        make_stored_battle(
            "b2",
            "refinement:0002",
            outcome="loss",
            our_survivors=(),
            opponent_survivors=(2,),
        ),
    ]
    our, opp = make_snapshots()
    prepared = prepare_sources(
        battles,
        snapshots=(our, opp),
        token_budget=8000,
        output_token_budget=1200,
        model_name="deepseek-ai/DeepSeek-V4.1-Flash-1017",
    )
    run_id = uuid.uuid4()
    token = uuid.uuid4()
    store.create_sources(
        run_id=run_id,
        token=token,
        expected_revision=1,
        sources=prepared,
    )
    loaded = store.load_sources(run_id)
    assert isinstance(loaded, PreparedSources)
    assert loaded.sourceHash == prepared.sourceHash
    assert loaded.statistics.outcomes.sampleSize == 2
