"""Unit tests for turn-1 extraction from replay."""

from __future__ import annotations

from pokecoach_vgc_bridge.battle_capture import BattleCapture
from pokecoach_vgc_bridge.extract_turn_one import (
    _mon_for_roster_slot,
    _turn1_actions_from_player_captures,
    _turn1_actions_from_replay,
)


class _FakeMon:
    pass


class _FakeBattle:
    def __init__(self, replay: list[list[str]], team: list[_FakeMon]) -> None:
        self._replay_data = replay
        self.team = {f"p1{i}": m for i, m in enumerate(team, start=1)}

    def get_pokemon(self, ident: str):
        key = ident.split(":")[0].strip()
        return self.team[key]


def test_turn1_actions_from_replay_maps_roles_to_lead_slots():
    replay = [
        ["", "move", "p2a: Garchomp", "Earthquake", "p1a: Drill"],
        ["", "move", "p2b: Metagross", "Protect", "p1a: Drill"],
        ["", "turn", "1"],
        ["", "turn", "2"],
    ]
    battle = _FakeBattle(replay, [_FakeMon(), _FakeMon()])
    actions = _turn1_actions_from_replay(
        battle,
        side="opponent",
        lead_order=(2, 4),
        target_side="ours",
        our_active_roster=(0, 1),
        opp_active_roster=None,
    )
    assert actions is not None
    assert actions[0]["actor"]["slot"] == 2
    assert actions[0]["move"] == "Earthquake"
    assert actions[0]["targetType"] == "allAdjacent"
    assert actions[0]["targets"] == [{"kind": "zone", "zone": "allAdjacent"}]
    assert actions[1]["actor"]["slot"] == 4
    assert actions[1]["move"] == "Protect"
    assert actions[1]["targets"][0]["ref"]["slot"] == 4


def test_turn1_replay_tailwind_ignores_decorative_target_token():
    replay = [
        ["", "move", "p1a: Staraptor", "Tailwind"],
        ["", "move", "p1b: Gholdengo", "Protect", "p1b: Gholdengo"],
        ["", "turn", "1"],
    ]
    battle = _FakeBattle(replay, [_FakeMon(), _FakeMon()])
    actions = _turn1_actions_from_replay(
        battle,
        side="ours",
        lead_order=(0, 1),
        target_side="opponent",
        our_active_roster=(0, 1),
        opp_active_roster=(2, 3),
    )
    assert actions is not None
    assert actions[0]["move"] == "Tailwind"
    assert actions[0]["targets"] == [{"kind": "zone", "zone": "allySide"}]
    assert actions[0]["targetType"] == "allySide"


def test_mon_for_roster_slot_maps_bring_four_team():
    team = [_FakeMon(), _FakeMon(), _FakeMon(), _FakeMon()]
    roster = (0, 1, 4, 5)
    assert _mon_for_roster_slot(team, 5, roster) is team[3]
    assert _mon_for_roster_slot(team, 0, roster) is team[0]


def test_turn1_actions_from_player_captures():
    capture = BattleCapture(side="opponent")
    capture.orders.append(
        {
            "turn": 1,
            "parsed": {
                "kind": "double",
                "first": {
                    "orderKind": "move",
                    "moveId": "earthquake",
                    "move_target": 0,
                },
                "second": {"orderKind": "move", "moveId": "protect", "move_target": 0},
            },
        }
    )
    battle = _FakeBattle([], [_FakeMon(), _FakeMon()])
    battle.pokecoach_player_captures = {"opponent": capture}
    actions = _turn1_actions_from_player_captures(
        battle,
        side="opponent",
        lead_order=(2, 4),
        target_side="ours",
        active_roster=(0, 1, 2, 4),
        our_active_roster=(0, 1),
        opp_active_roster=(0, 1, 2, 4),
        battle_format="gen9championsvgc2026regma",
    )
    assert actions is not None
    assert actions[0]["actor"]["slot"] == 2
    assert actions[0]["move"] == "Earthquake"
    assert actions[1]["actor"]["slot"] == 4
    assert actions[1]["move"] == "Protect"


def test_turn1_actions_from_capture_showdown_message():
    from pokecoach_vgc_bridge.battle_order_serialize import parse_doubles_choose_message

    assert parse_doubles_choose_message("/choose move earthquake, move protect") == (
        "move earthquake",
        "move protect",
    )
    capture = BattleCapture(side="opponent")
    capture.orders.append(
        {
            "turn": 0,
            "message": "/choose move closecombat 1, move fakeout",
            "parsed": {"kind": "default", "message": "/choose default"},
        }
    )
    battle = _FakeBattle([], [_FakeMon(), _FakeMon()])
    battle.pokecoach_player_captures = {"opponent": capture}
    actions = _turn1_actions_from_player_captures(
        battle,
        side="opponent",
        lead_order=(3, 5),
        target_side="ours",
        active_roster=(3, 5, 0, 1),
        our_active_roster=(0, 1),
        opp_active_roster=(3, 5, 0, 1),
        battle_format="gen9championsvgc2026regma",
    )
    assert actions is not None
    assert actions[0]["move"] == "Close Combat"
    assert actions[1]["move"] == "Fake Out"
