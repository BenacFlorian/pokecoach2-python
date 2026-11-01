"""Persisted phase D battles (requires TEST_DATABASE_URL)."""

from __future__ import annotations

import json
import os
import re
import uuid

import pytest

from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.phases.phase_c import run_phase_c
from pokecoach_python.workflow.phases.phase_d import run_phase_d
from pokecoach_python.workflow.types import PhaseContext


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if not re.search(r"(_test|/pokecoach2_test\b)", url):
        pytest.fail("TEST_DATABASE_URL must target an explicit test database")
    return url


def test_phase_d_publishes_global_refinement_shape():
    _require_test_database_url()
    pytest.skip(
        "Repository-backed D persistence test: run manually with worker DB + migrate V1.0.14"
    )


def test_phase_d_checkpoint_envelope_from_stub_smoke():
    """In-memory smoke remains the default CI proof for D publication."""
    partial: dict = {"completedPhases": []}

    def _ctx(profile: str, target: str, partial_in: dict, seed: int = 19) -> PhaseContext:
        return PhaseContext(
            run_id=uuid.uuid4(),
            lease_token=uuid.uuid4(),
            matchup_id=uuid.uuid4(),
            regulation="M-B",
            target_phase=target,  # type: ignore[arg-type]
            profile=profile,
            seed=seed,
            our_snapshot={"pokemon": []},
            opponent_snapshot={"pokemon": []},
            partial_result=partial_in,
            parameters={"profile": profile, "checkpoint_id": "stub-bc-v1"},
            engine=StubEngineAdapter(),
            report_progress=lambda *_: None,
        )

    partial = run_phase_a(_ctx("smoke", "A", partial)).result.model_dump(mode="json")
    partial = run_phase_c(_ctx("smoke", "C", partial)).result.model_dump(mode="json")
    partial = run_phase_b(_ctx("smoke", "B", partial)).result.model_dump(mode="json")
    out = run_phase_d(_ctx("smoke", "D", partial))
    ref = out.result.refinement
    assert ref is not None
    payload = json.loads(out.result.model_dump_json())
    assert payload["refinement"]["samplingPolicy"] == "weighted-ab"
    assert sum(ref.outcomes.values()) == ref.sampleSize
