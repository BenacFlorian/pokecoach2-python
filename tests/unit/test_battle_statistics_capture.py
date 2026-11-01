from __future__ import annotations

from pokecoach_python.llm.battle_statistics import compute_d_statistics
from pokecoach_python.llm.battle_sources import normalize_stored_d_battle
from tests.unit.phase_e_fixtures import make_stored_battle


def test_compute_d_statistics_reports_damage_quality():
    stored = normalize_stored_d_battle(
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(0, 1),
            opponent_survivors=(),
            damage_events=[
                {
                    "kind": "damage",
                    "turn": 1,
                    "source": {"side": "ours", "slot": 0},
                    "target": {"side": "opponent", "slot": 1},
                    "hpPercentLoss": 40.0,
                    "direct": True,
                    "attributed": True,
                }
            ],
        )
    )
    stats = compute_d_statistics([stored])
    assert stats.quality.damageEventsConsidered >= 1
