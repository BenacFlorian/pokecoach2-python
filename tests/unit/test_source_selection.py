from __future__ import annotations

import pytest

from pokecoach_python.llm.battle_sources import normalize_stored_d_battle
from pokecoach_python.llm.source_preparation import prepare_sources
from pokecoach_python.llm.source_selection import validate_source_selection
from pokecoach_python.schemas.analysis_result import LeadSelection
from tests.unit.phase_e_fixtures import make_snapshots, make_stored_battle


def test_prepare_sources_limits_our_team_to_four() -> None:
    battles = [
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(0, 1),
            opponent_survivors=(),
        )
    ]
    our_four = (0, 1, 4, 5)
    prepared = prepare_sources(
        battles,
        snapshots=make_snapshots(),
        token_budget=50_000,
        our_four=our_four,
    )
    assert len(prepared.ourTeam) == 4
    assert {row.slot for row in prepared.ourTeam} == set(our_four)
    selection = LeadSelection(ourFourSlots=list(our_four), ourLeadSlots=[0, 1])
    validate_source_selection(prepared, selection)


def test_prepare_sources_accepts_showdown_order_our_four_argument() -> None:
    stored_four = (0, 1, 3, 5)
    battles = [
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(3, 5),
            opponent_survivors=(),
            our_four=stored_four,
        ),
        make_stored_battle(
            "b2",
            "refinement:0002",
            outcome="loss",
            our_survivors=(3,),
            opponent_survivors=(0, 1),
            our_four=stored_four,
        ),
    ]
    prepared = prepare_sources(
        battles,
        snapshots=make_snapshots(),
        token_budget=50_000,
        our_four=(3, 5, 0, 1),
    )
    assert prepared.selectedBattles[0].ourFourSlots == stored_four


def test_validate_source_selection_rejects_mismatched_four() -> None:
    battle = normalize_stored_d_battle(
        make_stored_battle(
            "b1",
            "refinement:0001",
            outcome="win",
            our_survivors=(0, 1),
            opponent_survivors=(),
            our_four=(0, 1, 2, 3),
        )
    )
    prepared = prepare_sources(
        [
            make_stored_battle(
                "b1",
                "refinement:0001",
                outcome="win",
                our_survivors=(0, 1),
                opponent_survivors=(),
                our_four=(0, 1, 2, 3),
            )
        ],
        snapshots=make_snapshots(),
        token_budget=50_000,
        our_four=(0, 1, 2, 3),
    )
    selection = LeadSelection(ourFourSlots=[0, 1, 4, 5], ourLeadSlots=[0, 1])
    with pytest.raises(ValueError, match="ourTeam slots must match selection C"):
        validate_source_selection(prepared, selection)
    assert battle.ourFourSlots == (0, 1, 2, 3)
