from __future__ import annotations

from pokecoach_vgc_bridge.battle_capture import capture_events_from_replay
from pokecoach_vgc_bridge.pokemon_identity import PokemonIdentityMap


class _FakeMon:
    pass


class _FakeBattle:
    def __init__(self, replay: list[list[str]]) -> None:
        self._replay_data = replay


def test_capture_events_from_replay_switch_and_move():
    replay = [
        ["", "switch", "p1a: Tyranitar", "100/100"],
        ["", "move", "p1a: Tyranitar", "Fake Out", "p2a: Gholdengo"],
        ["", "turn", "1"],
    ]
    identity = PokemonIdentityMap.from_snapshots(
        {"pokemon": [{"species": "Staraptor"}, {"species": "Gholdengo"}]},
        {"pokemon": [{"species": "A"}, {"species": "B"}]},
    )
    events = capture_events_from_replay(_FakeBattle(replay), identity=identity, our_is_p1=True)
    kinds = [event["kind"] for event in events]
    assert kinds == ["switch", "move"]
