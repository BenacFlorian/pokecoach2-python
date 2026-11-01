from __future__ import annotations

import pytest

from pokecoach_python.graphs.matchup_gameplan.models import (
    PokemonHighlight,
    PokemonRef,
    StrategyGameplan,
    StrategyOutput,
    StrategyWinCondition,
)
from pokecoach_python.llm.strategy_references import (
    render_strategy_references,
    validate_strategy_reference_tokens,
    validate_strategy_team_references,
)
from tests.unit.phase_e_fixtures import make_snapshots


def _strategy(opening: str) -> StrategyOutput:
    return StrategyOutput(
        gameplan=StrategyGameplan(
            opening=opening,
            midgame="Trade with {{ours:1}}.",
            endgame="Close.",
            threats=[
                PokemonHighlight(
                    pokemon=PokemonRef(side="opponent", slot=2),
                    explanation="Threat {{opponent:2}}.",
                )
            ],
            strengths=[
                PokemonHighlight(
                    pokemon=PokemonRef(side="ours", slot=0),
                    explanation="Strength {{ours:0}}.",
                )
            ],
            evidenceBattleIds=["b1"],
        ),
        winCondition=StrategyWinCondition(
            description="Win with {{ours:0}}.",
            rationale="Evidence.",
            evidenceBattleIds=["b1"],
        ),
    )


def test_render_strategy_references_replaces_tokens():
    our, opp = make_snapshots()
    rendered = render_strategy_references(
        _strategy("Lead with {{ours:0}}."),
        snapshots=(our, opp),
    )
    assert "{{" not in rendered.gameplan.opening
    assert "Flutter Mane" in rendered.gameplan.opening


def test_validate_strategy_reference_tokens_rejects_outside_bring_four():
    with pytest.raises(ValueError, match="outside bring-4"):
        validate_strategy_reference_tokens(
            _strategy("Use {{ours:2}}."),
            our_four=(0, 1, 4, 5),
        )


def test_validate_strategy_team_references_after_render():
    our, opp = make_snapshots()
    rendered = render_strategy_references(
        _strategy("Press with {{ours:0}}."),
        snapshots=(our, opp),
    )
    validate_strategy_team_references(
        rendered,
        our_snapshot=our,
        our_four=(0, 1, 4, 5),
    )
