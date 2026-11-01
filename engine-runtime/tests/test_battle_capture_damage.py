"""Tests for replay damage capture."""

from __future__ import annotations

import pytest

from pokecoach_vgc_bridge.battle_capture import capture_events_from_replay
from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap


class _FakeBattle:
    def __init__(self, replay: list[list[str]]) -> None:
        self._replay_data = replay


def test_capture_damage_event_includes_target_and_hp_percent_loss():
    identity = PokemonIdentityMap.from_snapshots(
        {
            "pokemon": [
                {"species": "Flutter Mane"},
                {"species": "Incineroar"},
            ]
            + [{}] * 4,
        },
        {
            "pokemon": [
                {"species": "Urshifu"},
                {"species": "Rillaboom"},
            ]
            + [{}] * 4,
        },
    )
    replay = [
        ["", "turn", "1"],
        ["", "-damage", "p2a: Urshifu", "55/100"],
        ["", "-damage", "p2a: Urshifu", "20/100"],
    ]
    events = capture_events_from_replay(_FakeBattle(replay), identity=identity, our_is_p1=True)
    damage = [event for event in events if event.get("kind") == "damage"]
    assert len(damage) == 2
    assert damage[0]["target"] == {"side": "opponent", "slot": 0}
    assert damage[0]["hpPercentLoss"] == pytest.approx(45.0)
    assert damage[1]["hpPercentLoss"] == pytest.approx(35.0)
