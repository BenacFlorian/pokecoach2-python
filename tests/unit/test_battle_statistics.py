from __future__ import annotations

from pokecoach_python.llm.battle_sources import normalize_stored_d_battle
from pokecoach_python.llm.battle_statistics import compute_d_statistics
from tests.unit.phase_e_fixtures import damage_event, make_stored_battle


def test_compute_d_statistics_uses_all_d_battles() -> None:
    records = [
        normalize_stored_d_battle(
            make_stored_battle(
                "w1",
                "refinement:0001",
                outcome="win",
                our_survivors=(0, 1),
                opponent_survivors=(),
                opponent_lead=(0, 1),
                damage_events=[
                    damage_event(
                        turn=1,
                        source_side="ours",
                        source_slot=0,
                        target_side="opponent",
                        target_slot=0,
                        hp_percent_loss=60.0,
                    )
                ],
            )
        ),
        normalize_stored_d_battle(
            make_stored_battle(
                "l1",
                "refinement:0002",
                outcome="loss",
                our_survivors=(),
                opponent_survivors=(2, 3),
                opponent_lead=(0, 1),
                damage_events=[
                    damage_event(
                        turn=1,
                        source_side="opponent",
                        source_slot=2,
                        target_side="ours",
                        target_slot=0,
                        hp_percent_loss=70.0,
                        caused_ko=True,
                    ),
                    damage_event(
                        turn=1,
                        source_side="ours",
                        source_slot=1,
                        target_side="opponent",
                        target_slot=1,
                        hp_percent_loss=35.0,
                    ),
                ],
            )
        ),
        normalize_stored_d_battle(
            make_stored_battle(
                "w2",
                "refinement:0003",
                outcome="win",
                our_survivors=(0, 4),
                opponent_survivors=(),
                opponent_lead=(2, 3),
                damage_events=[
                    damage_event(
                        turn=2,
                        source_side="ours",
                        source_slot=4,
                        target_side="opponent",
                        target_slot=2,
                        hp_percent_loss=50.0,
                    ),
                    damage_event(
                        turn=2,
                        source_side="opponent",
                        source_slot=3,
                        target_side="ours",
                        target_slot=1,
                        hp_percent_loss=15.0,
                        direct=False,
                    ),
                ],
            )
        ),
    ]
    stats = compute_d_statistics(records)
    assert stats.outcomes.sampleSize == 3
    assert stats.outcomes.wins == 2
    assert stats.outcomes.losses == 1
    assert stats.leads[0].opponentLeadSlots == (0, 1)
    assert stats.leads[0].count == 2
    assert stats.leadResults[1].opponentLeadSlots == (2, 3)
    assert stats.threatsInLosses[0].pokemon.slot == 2
    assert stats.threatsInLosses[0].directKoCount == 1
    our_damage = {row.pokemon.slot: row.averageDirectDamagePercent for row in stats.ourDamage}
    assert our_damage[0] == 20.0
    assert our_damage[1] == (35.0 / 3)
    assert our_damage[4] == (50.0 / 3)


def test_compute_d_statistics_ignores_unattributed_or_substitute_damage() -> None:
    records = [
        normalize_stored_d_battle(
            make_stored_battle(
                "l2",
                "refinement:0004",
                outcome="loss",
                our_survivors=(),
                opponent_survivors=(2,),
                damage_events=[
                    damage_event(
                        turn=1,
                        source_side=None,
                        source_slot=None,
                        target_side="ours",
                        target_slot=0,
                        hp_percent_loss=40.0,
                        attributed=False,
                    ),
                    damage_event(
                        turn=1,
                        source_side="ours",
                        source_slot=0,
                        target_side="opponent",
                        target_slot=0,
                        hp_percent_loss=25.0,
                        target_substitute=True,
                    ),
                ],
            )
        )
    ]
    stats = compute_d_statistics(records)
    assert stats.threatsInLosses[0].directDamagePercent == 0.0
    assert stats.ourDamage[0].totalDirectDamagePercent == 0.0
    assert stats.quality.unattributedDamageEvents == 1
