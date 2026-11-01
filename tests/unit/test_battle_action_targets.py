from __future__ import annotations

from pokecoach_python.schemas.battle_actions import validate_move_action


def test_tailwind_action_contract() -> None:
    action = validate_move_action(
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": 0},
            "move": "Tailwind",
            "moveId": "tailwind",
            "targetType": "allySide",
            "targetSource": "dex",
            "targets": [{"kind": "zone", "zone": "allySide"}],
        }
    )
    assert action.target_type == "allySide"


def test_unknown_target_type_allows_empty_targets() -> None:
    action = validate_move_action(
        {
            "kind": "move",
            "actor": {"side": "ours", "slot": 1},
            "move": "Unknown",
            "moveId": None,
            "targetType": None,
            "targetSource": "unknown",
            "targets": [],
        }
    )
    assert action.target_source == "unknown"
