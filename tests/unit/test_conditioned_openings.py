"""Unit tests for conditioned openings aggregation."""

from __future__ import annotations

from pokecoach_python.engine.contracts import TurnOneRecord
from pokecoach_python.schemas.analysis_result import OpponentLeadEntry
from pokecoach_python.workflow.aggregation.openings import aggregate_opening_study


def _move(side: str, slot: int, move: str) -> dict:
    target_side = "opponent" if side == "ours" else "ours"
    return {
        "kind": "move",
        "actor": {"side": side, "slot": slot},
        "move": move,
        "targets": [{"kind": "pokemon", "ref": {"side": target_side, "slot": 0}}],
    }


def test_recommendation_is_mode_of_our_actions_not_opponent():
    lead = OpponentLeadEntry(id="lead-0-1", slots=(0, 1), count=10)
    common = [_move("ours", 2, "A"), _move("ours", 3, "B")]
    rare = [_move("ours", 2, "X"), _move("ours", 3, "Y")]
    records = [
        TurnOneRecord(
            opponent_lead_slots=(0, 1),
            payload={
                "opponentActions": [_move("opponent", 0, "O1"), _move("opponent", 1, "O2")],
                "ourActions": common,
                "backPair": [2, 3],
            },
        ),
        TurnOneRecord(
            opponent_lead_slots=(0, 1),
            payload={
                "opponentActions": [_move("opponent", 0, "O3"), _move("opponent", 1, "O4")],
                "ourActions": common,
                "backPair": [2, 4],
            },
        ),
        TurnOneRecord(
            opponent_lead_slots=(0, 1),
            payload={
                "opponentActions": [_move("opponent", 0, "O1"), _move("opponent", 1, "O2")],
                "ourActions": rare,
                "backPair": [2, 5],
            },
        ),
    ]
    study = aggregate_opening_study(records, opponent_lead=lead)
    assert study.recommendation["count"] == 2
    assert study.recommendation["value"][0]["move"] == "A"
