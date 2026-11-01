from __future__ import annotations

from pokecoach_python.graphs.matchup_gameplan.prompts.generate_gameplan_prompt import (
    get_generate_gameplan_prompt,
)
from pokecoach_python.llm.source_preparation import prepare_sources
from tests.unit.phase_e_fixtures import make_snapshots, make_stored_battle


def _minimal_sources():
    return prepare_sources(
        [
            make_stored_battle(
                "b1",
                "refinement:0001",
                outcome="win",
                our_survivors=(0, 1),
                opponent_survivors=(),
            ),
        ],
        snapshots=make_snapshots(),
        token_budget=50000,
        model_name="test-model",
        output_token_budget=1200,
    )


def test_generate_gameplan_prompt_french_by_default() -> None:
    prompt = get_generate_gameplan_prompt(_minimal_sources())
    assert "in French" in prompt


def test_generate_gameplan_prompt_english_when_requested() -> None:
    prompt = get_generate_gameplan_prompt(_minimal_sources(), output_locale="en")
    assert "in English" in prompt
    assert "in French" not in prompt
