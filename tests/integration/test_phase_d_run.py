"""Integration-style tests for phase D."""

from __future__ import annotations

from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.phases.phase_c import run_phase_c
from pokecoach_python.workflow.phases.phase_d import run_phase_d
from pokecoach_python.workflow.types import PhaseContext


def _ctx(profile: str, target: str, partial: dict, seed: int = 19) -> PhaseContext:
    return PhaseContext(
        run_id=__import__("uuid").uuid4(),
        lease_token=__import__("uuid").uuid4(),
        matchup_id=__import__("uuid").uuid4(),
        regulation="M-B",
        target_phase=target,  # type: ignore[arg-type]
        profile=profile,
        seed=seed,
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        partial_result=partial,
        parameters={"profile": profile, "checkpoint_id": "stub-bc-v1"},
        engine=StubEngineAdapter(),
        report_progress=lambda *_: None,
    )


def test_smoke_run_through_d_adds_refinement():
    partial: dict = {"completedPhases": []}
    partial = run_phase_a(_ctx("smoke", "A", partial)).result.model_dump(mode="json")
    partial = run_phase_c(_ctx("smoke", "C", partial)).result.model_dump(mode="json")
    partial = run_phase_b(_ctx("smoke", "B", partial)).result.model_dump(mode="json")
    out = run_phase_d(_ctx("smoke", "D", partial))
    ref = out.result.refinement
    assert ref is not None
    assert ref.sampleSize == 2
    assert sum(ref.outcomes.values()) == 2
