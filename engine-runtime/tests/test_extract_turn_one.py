"""Unit tests for turn-1 extraction from replay."""

from __future__ import annotations

from pokecoach_vgc_bridge.battle_capture import BattleCapture
from pokecoach_vgc_bridge.extract_turn_one import (
    _mon_for_roster_slot,
    _target_roster_from_move_target,
    _target_roster_slot_from_token,
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


def test_target_roster_from_move_target_maps_showdown_foe_positions():
    class _EmptyBattle:
        active_pokemon: list = []
        opponent_active_pokemon: list = []
        team = {}
        opponent_team = {}

    battle = _EmptyBattle()
    assert (
        _target_roster_from_move_target(
            battle,
            side="opponent",
            move_target=1,
            target_side="ours",
            our_active_roster=(0, 1, 2, 3),
            opp_active_roster=(4, 5, 6, 7),
        )
        == 0
    )
    assert (
        _target_roster_from_move_target(
            battle,
            side="opponent",
            move_target=2,
            target_side="ours",
            our_active_roster=(0, 1, 2, 3),
            opp_active_roster=(4, 5, 6, 7),
        )
        == 1
    )
    assert (
        _target_roster_from_move_target(
            battle,
            side="ours",
            move_target=1,
            target_side="opponent",
            our_active_roster=(0, 1),
            opp_active_roster=(3, 5, 0, 1),
        )
        == 3
    )
    assert (
        _target_roster_from_move_target(
            battle,
            side="ours",
            move_target=2,
            target_side="opponent",
            our_active_roster=(0, 1),
            opp_active_roster=(3, 5, 0, 1),
        )
        == 5
    )


def test_target_roster_slot_from_token_uses_field_lead_not_team_index():
    class _Battle:
        def get_pokemon(self, ident: str):
            return self._mons.get(ident.split(":")[0].strip())

    battle = _Battle()
    back = _FakeMon()
    battle._mons = {"p2c": back}
    battle.opponent_active_pokemon = [None, None]
    battle.opponent_team = [back, back, back, back]
    assert (
        _target_roster_slot_from_token(
            battle,
            "p2a:Incineroar",
            target_side="opponent",
            our_active_roster=(0, 1),
            opp_active_roster=(3, 5, 0, 1),
        )
        == 3
    )
    assert (
        _target_roster_slot_from_token(
            battle,
            "p2b:Garchomp",
            target_side="opponent",
            our_active_roster=(0, 1),
            opp_active_roster=(3, 5, 0, 1),
        )
        == 5
    )


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
    assert actions[0]["targets"][0]["ref"]["slot"] == 0
    assert actions[1]["move"] == "Fake Out"
