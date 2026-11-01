from __future__ import annotations

import pytest

from pokecoach_python.graphs.matchup_gameplan.models import (
    PokemonHighlight,
    PokemonRef,
    StrategyGameplan,
    StrategyOutput,
    StrategyWinCondition,
)
from pokecoach_python.llm.strategy_references import validate_strategy_team_references
from tests.unit.phase_e_fixtures import make_snapshots


def _strategy(**opening: str) -> StrategyOutput:
    text = opening.get("opening", "Press with slot 0.")
    return StrategyOutput(
        gameplan=StrategyGameplan(
            opening=text,
            midgame="Trade safely.",
            endgame="Close with slot 0.",
            threats=[
                PokemonHighlight(
                    pokemon=PokemonRef(side="opponent", slot=2),
                    explanation="Main damage threat.",
                )
            ],
            strengths=[
                PokemonHighlight(
                    pokemon=PokemonRef(side="ours", slot=0),
                    explanation="Wins converted cleanly.",
                )
            ],
            evidenceBattleIds=["b1"],
        ),
        winCondition=StrategyWinCondition(
            description="Contain slot 2.",
            rationale="Losses came from unchecked slot 2.",
            evidenceBattleIds=["b1"],
        ),
    )


def test_validate_strategy_rejects_our_species_outside_bring_four() -> None:
    our, _ = make_snapshots()
    strategy = _strategy(opening="Pivot with Rillaboom even though it is not selected.")
    with pytest.raises(ValueError, match="outside bring-4"):
        validate_strategy_team_references(
            strategy,
            our_snapshot=our,
            our_four=(0, 1, 4, 5),
        )


def test_validate_strategy_allows_species_in_bring_four() -> None:
    our, _ = make_snapshots()
    strategy = _strategy(opening="Lead Flutter Mane and protect Incineroar.")
    validate_strategy_team_references(
        strategy,
        our_snapshot=our,
        our_four=(0, 1, 4, 5),
    )
