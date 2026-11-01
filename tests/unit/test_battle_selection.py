from __future__ import annotations

import pytest

from pokecoach_python.llm.battle_selection import select_d_battles
from pokecoach_python.llm.battle_sources import normalize_stored_d_battle
from tests.unit.phase_e_fixtures import make_stored_battle


def test_select_d_battles_small_n_caps_unique_battles() -> None:
    records = [
        normalize_stored_d_battle(
            make_stored_battle(
                "b1",
                "refinement:0001",
                outcome="win",
                our_survivors=(0,),
                opponent_survivors=(),
            )
        ),
        normalize_stored_d_battle(
            make_stored_battle(
                "b2",
                "refinement:0002",
                outcome="loss",
                our_survivors=(),
                opponent_survivors=(2,),
            )
        ),
    ]
    manifest = select_d_battles(records)
    assert manifest.quotas == {"wins": 1, "losses": 1, "close": 1}
    assert len(manifest.selectedBattleIds) == 2
    assert len(set(manifest.selectedBattleIds)) == 2


def test_select_d_battles_n100_uses_expected_quotas() -> None:
    records = []
    for index in range(100):
        outcome = "win" if index % 2 == 0 else "loss"
        if index < 20:
            our_survivors = (0,) if outcome == "win" else ()
            opponent_survivors = () if outcome == "win" else (2,)
        elif index < 40:
            our_survivors = (0, 1) if outcome == "win" else ()
            opponent_survivors = () if outcome == "win" else (2, 3)
        else:
            our_survivors = (0, 1, 4) if outcome == "win" else ()
            opponent_survivors = () if outcome == "win" else (1, 2, 3)
        records.append(
            normalize_stored_d_battle(
                make_stored_battle(
                    f"b{index}",
                    f"refinement:{index:04d}",
                    outcome=outcome,
                    our_survivors=our_survivors,
                    opponent_survivors=opponent_survivors,
                )
            )
        )
    manifest = select_d_battles(records)
    assert manifest.close.requested == 20
    assert len(manifest.close.retainedBattleIds) == 20
    assert len(manifest.wins.retainedBattleIds) == 15
    assert len(manifest.losses.retainedBattleIds) == 15
    assert len(manifest.selectedBattleIds) == 50


def test_select_d_battles_rejects_when_only_draws_exist() -> None:
    records = [
        normalize_stored_d_battle(
            make_stored_battle(
                "d1",
                "refinement:0001",
                outcome="draw",
                our_survivors=(0, 1),
                opponent_survivors=(2, 3),
            )
        )
    ]
    with pytest.raises(ValueError, match="NO_SELECTABLE_D_BATTLE"):
        select_d_battles(records)
