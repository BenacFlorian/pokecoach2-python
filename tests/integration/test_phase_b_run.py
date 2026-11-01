"""Integration-style tests for phase B on top of phases A and C."""

from __future__ import annotations

from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.phases.phase_c import run_phase_c
from pokecoach_python.workflow.types import PhaseContext


def _ctx(profile: str, target: str, partial: dict, seed: int = 7) -> PhaseContext:
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


def test_smoke_run_ac_then_b_adds_openings():
    phase_a = run_phase_a(_ctx("smoke", "A", {"completedPhases": []}))
    partial = phase_a.result.model_dump(mode="json")
    phase_c = run_phase_c(_ctx("smoke", "C", partial))
    partial_ac = phase_c.result.model_dump(mode="json")
    phase_b = run_phase_b(_ctx("smoke", "B", partial_ac))
    assert phase_b.result.completedPhases == ["A", "C", "B"]
    openings = phase_b.result.openings
    assert openings is not None
    leads = phase_b.result.opponentLeads
    assert leads is not None
    assert len(openings.byOpponentLead) == len(leads.leads)
    assert all(entry.sampleSize == 3 for entry in openings.byOpponentLead)
    assert openings.selection == phase_c.result.leadPick.selection  # type: ignore[union-attr]
