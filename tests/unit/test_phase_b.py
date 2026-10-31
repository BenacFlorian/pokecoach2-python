"""Unit tests for phase B aggregation and handler."""

from __future__ import annotations

import pytest

from pokecoach_python.engine.contracts import TurnOneRecord
from pokecoach_python.engine.stub_adapter import StubEngineAdapter
from pokecoach_python.schemas.analysis_result import validate_result
from pokecoach_python.workflow.aggregation.turn_one import aggregate_turn_one, canonical_joint_key
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.types import PhaseContext


def _move(side: str, slot: int, move: str, target_side: str, target_slot: int) -> dict:
    return {
        "kind": "move",
        "actor": {"side": side, "slot": slot},
        "move": move,
        "targets": [{"kind": "pokemon", "ref": {"side": target_side, "slot": target_slot}}],
    }


def _record(lead: tuple[int, int], actions: list[dict], back: tuple[int, int]) -> TurnOneRecord:
    return TurnOneRecord(
        opponent_lead_slots=lead,
        payload={"actions": actions, "backPair": list(back), "endStateNotes": []},
    )


def test_joint_actions_group_by_actor_and_targets():
    lead = (0, 1)
    same = [
        _move("opponent", 0, "A", "ours", 2),
        _move("opponent", 1, "B", "ours", 3),
    ]
    permuted = [
        _move("opponent", 1, "B", "ours", 3),
        _move("opponent", 0, "A", "ours", 2),
    ]
    other_target = [
        _move("opponent", 0, "A", "ours", 4),
        _move("opponent", 1, "B", "ours", 3),
    ]
    records = [
        _record(lead, same, (2, 3)),
        _record(lead, permuted, (2, 4)),
        _record(lead, other_target, (2, 5)),
    ]
    section = aggregate_turn_one(records, lead)
    assert section.sampleSize == 3
    assert len(section.jointActions) == 2
    assert section.jointActions[0]["count"] == 2
    assert canonical_joint_key(section.jointActions[0]["value"]) == canonical_joint_key(same)
    assert section.jointActions[1]["count"] == 1


def test_back_marginals_sum_to_twice_sample_on_three_games():
    lead = (0, 1)
    records = [
        _record(lead, [_move("opponent", 0, "A", "ours", 2), _move("opponent", 1, "B", "ours", 3)], (2, 3)),
        _record(lead, [_move("opponent", 0, "A", "ours", 2), _move("opponent", 1, "B", "ours", 3)], (2, 4)),
        _record(lead, [_move("opponent", 0, "A", "ours", 2), _move("opponent", 1, "B", "ours", 3)], (3, 5)),
    ]
    section = aggregate_turn_one(records, lead)
    marginal_total = sum(row["count"] for row in section.backSlotMarginals)
    assert marginal_total == 6
    assert sum(row["count"] for row in section.backPairs) == 3


def test_phase_b_preserves_phase_a_fields():
    engine = StubEngineAdapter()

    def progress(_phase: str, _done: int, _total: int) -> None:
        return None

    base = PhaseContext(
        run_id=__import__("uuid").uuid4(),
        lease_token=__import__("uuid").uuid4(),
        matchup_id=__import__("uuid").uuid4(),
        regulation="M-B",
        target_phase="A",
        profile="smoke",
        seed=99,
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        partial_result={"completedPhases": []},
        parameters={"profile": "smoke", "checkpoint_id": "stub-bc-v1"},
        engine=engine,
        report_progress=progress,
    )
    phase_a = run_phase_a(base)
    partial = phase_a.result.model_dump(mode="json")
    ctx_b = PhaseContext(
        run_id=base.run_id,
        lease_token=base.lease_token,
        matchup_id=base.matchup_id,
        regulation=base.regulation,
        target_phase="B",
        profile="smoke",
        seed=base.seed,
        our_snapshot=base.our_snapshot,
        opponent_snapshot=base.opponent_snapshot,
        partial_result=partial,
        parameters=base.parameters,
        engine=engine,
        report_progress=progress,
    )
    phase_b = run_phase_b(ctx_b)
    assert phase_b.result.completedPhases == ["A", "B"]
    assert phase_a.result.opponentLeads is not None
    assert phase_b.result.opponentLeads is not None
    for before, after in zip(
        phase_a.result.opponentLeads.leads,
        phase_b.result.opponentLeads.leads,
        strict=True,
    ):
        assert before.id == after.id
        assert before.slots == after.slots
        assert before.count == after.count
        assert after.turn1 is not None
        assert after.turn1.sampleSize == 3
    validate_result(phase_b.result.model_dump(mode="json"))


def test_phase_b_requires_phase_a_checkpoint():
    with pytest.raises(RuntimeError, match="phase A"):
        run_phase_b(
            PhaseContext(
                run_id=__import__("uuid").uuid4(),
                lease_token=__import__("uuid").uuid4(),
                matchup_id=__import__("uuid").uuid4(),
                regulation="M-B",
                target_phase="B",
                profile="smoke",
                seed=1,
                our_snapshot={},
                opponent_snapshot={},
                partial_result={"completedPhases": []},
                parameters={"profile": "smoke"},
                engine=StubEngineAdapter(),
                report_progress=lambda *_: None,
            )
        )
