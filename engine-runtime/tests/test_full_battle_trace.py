"""Tests for complete battle trace normalization."""

from __future__ import annotations

import pytest

from pokecoach_vgc_bridge.full_battle_trace import (
    build_fixture_complete_trace,
    capture_terminal_state_from_battle,
    normalize_complete_battle,
)
from pokecoach_vgc_bridge.fixture_sim import FixtureRuntime, manifest_path_default


def test_normalize_complete_battle_stores_all_turns():
    turns, terminal_state, damage_events = build_fixture_complete_trace(
        seed=7,
        outcome="win",
        opponent_lead=(0, 1),
        our_four=(0, 1, 4, 5),
        our_lead=(0, 1),
        opponent_selected=(0, 1, 2, 3),
        our_actions_turn1=[{"kind": "move", "actor": {"side": "ours", "slot": 0}, "move": "Protect"}],
        opponent_actions_turn1=[],
        digest_byte=5,
    )
    record = normalize_complete_battle(
        opponent_lead=(0, 1),
        our_lead=(0, 1),
        our_four=(0, 1, 4, 5),
        opponent_selected=(0, 1, 2, 3),
        our_actions_turn1=turns[0]["ourActions"],
        opponent_actions_turn1=turns[0]["opponentActions"],
        outcome="win",
        seed=7,
        engine="fixture-bridge",
        turns=turns,
        terminal_state=terminal_state,
        terminal_evidence={"kind": "simulator", "turnCount": len(turns), "finished": True},
        damage_events=damage_events,
    )
    assert len(record["turns"]) == len(turns)
    assert record["meta"]["terminalState"]["ours"]["survivorSlots"]
    assert record["meta"]["terminalEvidence"]["turnCount"] == len(turns)


def test_normalize_rejects_turn_count_mismatch():
    with pytest.raises(ValueError, match="turnCount"):
        normalize_complete_battle(
            opponent_lead=(0, 1),
            our_lead=(0, 1),
            our_four=(0, 1, 2, 3),
            opponent_selected=(0, 1, 2, 3),
            our_actions_turn1=[],
            opponent_actions_turn1=[],
            outcome="win",
            seed=1,
            engine="test",
            turns=[{"turn": 1, "ourActions": [], "opponentActions": [], "events": []}],
            terminal_state={
                "ours": {
                    "selectedSlots": [0, 1, 2, 3],
                    "enteredSlots": [0, 1],
                    "survivorSlots": [0],
                },
                "opponent": {
                    "selectedSlots": [0, 1, 2, 3],
                    "enteredSlots": [0, 1],
                    "survivorSlots": [],
                },
            },
            terminal_evidence={"kind": "simulator", "turnCount": 3, "finished": True},
        )


def test_capture_terminal_state_maps_opponent_roster_when_team_len_four():
    class Mon:
        def __init__(self, *, active=False, fainted=False, hp=100):
            self.active = active
            self.fainted = fainted
            self.current_hp = 0 if fainted else hp
            self.max_hp = 100

    our_selected = (0, 1, 2, 3)
    opp_selected = (3, 5, 1, 2)
    battle = type(
        "B",
        (),
        {
            "team": {f"p{i}": Mon(active=i < 2) for i in range(6)},
            "opponent_team": {
                "a": Mon(active=True, fainted=False),
                "b": Mon(active=True, fainted=True),
                "c": Mon(fainted=False),
                "d": Mon(fainted=False),
            },
        },
    )()
    state = capture_terminal_state_from_battle(
        battle,
        our_selected=our_selected,
        opponent_selected=opp_selected,
    )
    assert state["opponent"]["selectedSlots"] == list(opp_selected)
    assert 3 in state["opponent"]["survivorSlots"]
    assert 5 not in state["opponent"]["survivorSlots"]


def test_fixture_runtime_full_battle_is_complete_for_e():
    runtime = FixtureRuntime(manifest_path_default())
    snap = {
        "pokemon": [{"species": f"M{i}", "moves": ["Protect"]} for i in range(6)]
    }
    payload = {
        "seed": 42,
        "ourSnapshot": snap,
        "opponentSnapshot": snap,
        "opponentLead": [0, 1],
        "ourSelection": [0, 1, 2, 3],
        "ourLeadSlots": [0, 1],
    }
    record = runtime.full_battle(payload)
    assert record["meta"]["terminalState"]["ours"]["selectedSlots"] == [0, 1, 2, 3]
    turn_count = record["meta"]["terminalEvidence"]["turnCount"]
    assert turn_count == len(record["turns"])
    assert turn_count >= 1
