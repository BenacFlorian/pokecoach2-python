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


def test_render_strategy_references_replaces_single_brace_tokens():
    our, opp = make_snapshots()
    rendered = render_strategy_references(
        _strategy("Lead with {ours:0} and {{ours:1}}."),
        snapshots=(our, opp),
    )
    assert "{ours:" not in rendered.gameplan.opening
    assert "Flutter Mane" in rendered.gameplan.opening
    assert "Incineroar" in rendered.gameplan.opening


def test_validate_strategy_reference_tokens_rejects_outside_bring_four():
    with pytest.raises(ValueError, match="outside bring-4"):
        validate_strategy_reference_tokens(
            _strategy("Use {{ours:2}}."),
            our_four=(0, 1, 4, 5),
        )


def test_validate_strategy_team_references_before_render():
    our, opp = make_snapshots()
    validate_strategy_team_references(
        _strategy("Press with {{ours:0}}."),
        our_snapshot=our,
        our_four=(0, 1, 4, 5),
        opponent_snapshot=opp,
    )


def test_validate_strategy_team_references_allows_shared_species_on_opponent():
    our, opp = make_snapshots()
    validate_strategy_team_references(
        _strategy("Answer {{opponent:3}} with {{ours:0}}."),
        our_snapshot=our,
        our_four=(0, 1, 4, 5),
        opponent_snapshot=opp,
    )


def test_validate_strategy_team_references_rejects_literal_bench_species():
    our, opp = make_snapshots()
    our_with_bench = dict(our)
    mons = list(our_with_bench["pokemon"])
    mons[2] = {"species": "Sinistcha", "moves": ["Matcha Gotcha"]}
    our_with_bench["pokemon"] = mons
    with pytest.raises(ValueError, match="Sinistcha"):
        validate_strategy_team_references(
            _strategy("Lead with our Sinistcha."),
            our_snapshot=our_with_bench,
            our_four=(0, 1, 4, 5),
            opponent_snapshot=opp,
        )
