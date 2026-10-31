"""Integration-style tests for phase C on top of phases A and B."""

from __future__ import annotations

from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.phases.phase_c import run_phase_c
from pokecoach_python.workflow.types import PhaseContext


def _ctx(profile: str, target: str, partial: dict, seed: int = 13) -> PhaseContext:
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


def test_smoke_run_through_c_adds_lead_pick():
    phase_a = run_phase_a(_ctx("smoke", "A", {"completedPhases": []}))
    partial = phase_a.result.model_dump(mode="json")
    phase_b = run_phase_b(_ctx("smoke", "B", partial))
    partial_b = phase_b.result.model_dump(mode="json")
    phase_c = run_phase_c(_ctx("smoke", "C", partial_b))
    assert phase_c.result.leadPick is not None
    studied = min(3, len(phase_b.result.opponentLeads.leads))  # type: ignore[union-attr]
    assert len(phase_c.result.leadPick.firstTurns) == studied
    assert len(phase_c.result.leadPick.comparisons) >= studied
