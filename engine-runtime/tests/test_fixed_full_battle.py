"""Fixed full-battle participants must come from observed preview, not payload echo."""

from __future__ import annotations

from pokecoach_vgc_bridge.fixture_sim import FixtureRuntime, manifest_path_default
from pokecoach_vgc_bridge.normalization import build_battle_record


def _minimal_payload(*, seed: int, opponent_back_wrong: list[int] | None) -> dict:
    snap = {
        "pokemon": [
            {"species": f"M{i}", "moves": ["Protect"]} for i in range(6)
        ]
    }
    payload: dict = {
        "seed": seed,
        "ourSnapshot": snap,
        "opponentSnapshot": snap,
        "opponentLead": [0, 1],
        "ourSelection": [0, 1, 2, 3],
        "ourLeadSlots": [0, 1],
    }
    if opponent_back_wrong is not None:
        payload["opponentBackPair"] = opponent_back_wrong
    return payload


def test_build_battle_record_uses_explicit_back_not_payload():
    payload = _minimal_payload(seed=1, opponent_back_wrong=[4, 5])
    observed_back = (2, 3)
    record = build_battle_record(
        opponent_lead=(0, 1),
        our_lead=(0, 1),
        our_four=(0, 1, 2, 3),
        our_actions=[],
        opponent_actions=[],
        outcome="win",
        seed=1,
        engine="test",
        payload=payload,
        opponent_back_pair=observed_back,
    )
    assert record["participants"]["opponentBackPair"] == [2, 3]
    assert payload["opponentBackPair"] == [4, 5]


def test_fixture_full_battle_back_from_simulation_not_payload():
    from pokecoach_vgc_bridge.fixture_sim import _back_pair, _digest, _snapshots

    runtime = FixtureRuntime(manifest_path_default())
    payload = _minimal_payload(seed=99, opponent_back_wrong=[4, 5])
    our, opp = _snapshots(payload)
    opp_lead = (0, 1)
    digest = _digest(f"full:{99}:{opp_lead}", our, opp)
    expected_back = list(_back_pair(opp_lead, digest[3]))
    record = runtime.full_battle(payload)
    back = record["participants"].get("opponentBackPair")
    assert back == expected_back
    assert payload["opponentBackPair"] == [4, 5]
