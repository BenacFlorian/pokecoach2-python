from __future__ import annotations

from dataclasses import replace

import pytest

from pokecoach_python.llm.battle_sources import (
    normalize_stored_d_battle,
    validate_d_synthesis_source,
)
from tests.unit.phase_e_fixtures import damage_event, make_stored_battle


def test_validate_d_synthesis_source_rejects_turns_without_events() -> None:
    stored = make_stored_battle(
        "b-empty",
        "refinement:0003",
        outcome="win",
        our_survivors=(0,),
        opponent_survivors=(),
        turn_count=12,
    )
    turns = list(stored.record.turns)
    turns[1] = {**turns[1], "events": []}
    hollow = replace(stored.record, turns=tuple(turns))
    with pytest.raises(ValueError, match="turn 2 has no captured events"):
        validate_d_synthesis_source(hollow)


def test_validate_d_synthesis_source_accepts_switch_only_turn() -> None:
    stored = make_stored_battle(
        "b-switch",
        "refinement:0004",
        outcome="win",
        our_survivors=(0, 1),
        opponent_survivors=(),
        turn_count=2,
        damage_events=(),
    )
    turns = list(stored.record.turns)
    turns[1] = {
        **turns[1],
        "events": [{"kind": "switch", "turn": 2, "side": "ours", "fromSlot": 0, "toSlot": 4}],
    }
    switched = replace(stored.record, turns=tuple(turns))
    validate_d_synthesis_source(switched)


def test_validate_d_synthesis_source_rejects_incomplete_trace() -> None:
    stored = make_stored_battle(
        "b1",
        "refinement:0001",
        outcome="win",
        our_survivors=(0,),
        opponent_survivors=(),
        declared_turn_count=3,
        turn_count=2,
    )
    with pytest.raises(ValueError, match="incomplete"):
        validate_d_synthesis_source(stored.record)


def test_normalize_stored_d_battle_reads_terminal_state_and_damage() -> None:
    stored = make_stored_battle(
        "b2",
        "refinement:0002",
        outcome="loss",
        our_survivors=(1,),
        opponent_survivors=(2, 3),
        damage_events=[
            damage_event(
                turn=1,
                source_side="opponent",
                source_slot=2,
                target_side="ours",
                target_slot=0,
                hp_percent_loss=55.0,
                caused_ko=True,
            ),
            damage_event(
                turn=2,
                source_side=None,
                source_slot=None,
                target_side="ours",
                target_slot=1,
                hp_percent_loss=10.0,
                attributed=False,
                direct=False,
            ),
        ],
    )
    battle = normalize_stored_d_battle(stored)
    assert battle.battleId == "b2"
    assert battle.turnCount == 2
    assert battle.opponentSelectedSlots == (0, 1, 2, 3)
    assert battle.survivorSlots["opponent"] == (2, 3)
    assert battle.damageEvents[0].source is not None
    assert battle.damageEvents[0].source.slot == 2
    assert battle.captureQuality.unattributedDamageEvents == 1
