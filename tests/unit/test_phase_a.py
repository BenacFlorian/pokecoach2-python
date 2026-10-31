"""Unit tests for phase A aggregation and handler."""

from __future__ import annotations

import pytest

from pokecoach_python.engine.contracts import PreviewRecord
from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.workflow.aggregation.leads import aggregate_leads, canonical_lead, lead_id
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.types import PhaseContext


def test_canonical_lead_sorts_slots():
    assert canonical_lead((1, 0)) == (0, 1)
    assert lead_id((1, 0)) == "lead-0-1"


def test_aggregate_leads_counts_and_order():
    records = [
        PreviewRecord(opponent_lead_slots=(0, 1)),
        PreviewRecord(opponent_lead_slots=(1, 0)),
        PreviewRecord(opponent_lead_slots=(2, 3)),
    ]
    section = aggregate_leads(records)
    assert section.sampleSize == 3
    assert len(section.leads) == 2
    assert section.leads[0].count == 2
    assert section.leads[0].slots == (0, 1)
    assert section.leads[1].count == 1
    assert all(entry.turn1 is None for entry in section.leads)


def test_aggregate_rejects_invalid_slot():
    with pytest.raises(ValueError):
        aggregate_leads([PreviewRecord(opponent_lead_slots=(0, 0))])


def test_phase_a_smoke_budget():
    progress_log: list[tuple[str, int, int]] = []

    def progress(phase: str, done: int, total: int) -> None:
        progress_log.append((phase, done, total))

    ctx = PhaseContext(
        run_id=__import__("uuid").uuid4(),
        lease_token=__import__("uuid").uuid4(),
        matchup_id=__import__("uuid").uuid4(),
        regulation="M-B",
        target_phase="A",
        profile="smoke",
        seed=42,
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        partial_result={"completedPhases": []},
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1"},
        engine=StubEngineAdapter(),
        report_progress=progress,
    )
    output = run_phase_a(ctx)
    assert output.result.completedPhases == ["A"]
    assert output.result.opponentLeads is not None
    assert output.result.opponentLeads.sampleSize == 20
    assert sum(entry.count for entry in output.result.opponentLeads.leads) == 20
    assert progress_log[-1] == ("A", 20, 20)
