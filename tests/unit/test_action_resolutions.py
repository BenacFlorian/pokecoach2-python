from __future__ import annotations

from pokecoach_python.engine.contracts import TurnOneRecord
from pokecoach_python.workflow.aggregation.openings import aggregate_opening_study
from pokecoach_python.workflow.aggregation.action_resolutions import build_action_resolutions
from pokecoach_python.schemas.analysis_result import OpponentLeadEntry


def _move(side: str, slot: int, move: str, target_slot: int, target_side: str) -> dict:
    return {
        "kind": "move",
        "actor": {"side": side, "slot": slot},
        "move": move,
        "targets": [{"kind": "pokemon", "ref": {"side": target_side, "slot": target_slot}}],
    }


def test_aggregate_attaches_two_resolutions_for_same_decision():
    lead = OpponentLeadEntry(id="lead-0-1", slots=(0, 1), count=3)
    decision = [
        _move("ours", 0, "Fake Out", 1, "opponent"),
        _move("ours", 1, "Protect", 1, "ours"),
    ]
    events_direct = [{"kind": "move", "turn": 1, "side": "ours", "role": "a", "move": "Fake Out", "targetToken": "p2a: X"}]
    events_switch = [
        {"kind": "switch", "turn": 1, "side": "ours", "role": "a"},
        {
            "kind": "move",
            "turn": 1,
            "side": "ours",
            "role": "a",
            "move": "Fake Out",
            "targetToken": "p2b: Y",
        },
    ]
    records = [
        TurnOneRecord(
            opponent_lead_slots=(0, 1),
            payload={
                "opponentActions": [
                    _move("opponent", 0, "A", 0, "ours"),
                    _move("opponent", 1, "B", 1, "ours"),
                ],
                "ourActions": decision,
                "backPair": [2, 3],
                "turnEvents": events_direct,
            },
        ),
        TurnOneRecord(
            opponent_lead_slots=(0, 1),
            payload={
                "opponentActions": [
                    _move("opponent", 0, "A", 0, "ours"),
                    _move("opponent", 1, "B", 1, "ours"),
                ],
                "ourActions": decision,
                "backPair": [2, 3],
                "turnEvents": events_switch,
            },
        ),
    ]
    section = aggregate_opening_study(records, opponent_lead=lead)
    reco = section.recommendation
    assert reco["count"] == 2
    assert "resolutions" in reco
    assert sum(row["count"] for row in reco["resolutions"]) == 2
    assert len(reco["resolutions"]) == 2


def test_build_action_resolutions_marks_not_executed():
    action = _move("ours", 0, "Fake Out", 1, "opponent")
    resolutions = build_action_resolutions([action, _move("ours", 1, "Protect", 1, "ours")], side="ours", events=[])
    assert resolutions[0]["cause"] == "not-executed"
    assert resolutions[0]["executed"] is False
