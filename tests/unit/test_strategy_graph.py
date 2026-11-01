from __future__ import annotations

import uuid

import pytest
from langchain_core.messages import HumanMessage

from pokecoach_python.core.config import Settings
from pokecoach_python.graphs.matchup_gameplan.invokation import invoke_matchup_gameplan
from pokecoach_python.graphs.matchup_gameplan.models import StrategyOutput
from pokecoach_python.llm.client import StrategyClient
from pokecoach_python.llm.source_preparation import prepare_sources
from tests.unit.phase_e_fixtures import make_snapshots, make_stored_battle


def _prepared_sources():
    return prepare_sources(
        [
            make_stored_battle(
                "b1",
                "refinement:0001",
                outcome="win",
                our_survivors=(0, 1),
                opponent_survivors=(),
            ),
            make_stored_battle(
                "b2",
                "refinement:0002",
                outcome="loss",
                our_survivors=(),
                opponent_survivors=(2,),
            ),
        ],
        snapshots=make_snapshots(),
        token_budget=50000,
        model_name="deepseek-ai/DeepSeek-V4.1-Flash-1017",
        output_token_budget=1200,
    )


def _strategy_payload() -> dict:
    return {
        "gameplan": {
            "opening": "Stabilise the first turns with speed control and safe chip.",
            "midgame": "Trade aggressively once their damage pivot is identified.",
            "endgame": "Preserve your cleaner for the final restricted exchange.",
            "threats": [
                {
                    "pokemon": {"side": "opponent", "slot": 2},
                    "explanation": "It converted the loss sample and pressured your leads immediately.",
                }
            ],
            "strengths": [
                {
                    "pokemon": {"side": "ours", "slot": 0},
                    "explanation": "It consistently created damage tempo across the sample.",
                }
            ],
            "evidenceBattleIds": ["b1", "b2"],
        },
        "winCondition": {
            "description": "Create an endgame where slot 0 closes after their slot 2 is contained.",
            "rationale": "The wins came from preserving offensive pressure into the last exchange.",
            "evidenceBattleIds": ["b1"],
        },
    }


def test_strategy_client_uses_deepinfra_structured_output() -> None:
    captured: dict = {}

    class FakeStructuredModel:
        def invoke(self, messages):
            captured["messages"] = messages
            return _strategy_payload()

    class FakeChatModel:
        def with_structured_output(self, schema, *, method, strict):
            captured["schema"] = schema
            captured["method"] = method
            captured["strict"] = strict
            return FakeStructuredModel()

    def fake_factory(**kwargs):
        captured["kwargs"] = kwargs
        return FakeChatModel()

    settings = Settings(
        _env_file=None,
        POSTGRES_PASSWORD="secret",
        DEEPINFRA_API_KEY="fake-key",
    )
    client = StrategyClient(settings, chat_factory=fake_factory)
    result = client.generate(
        _prepared_sources(),
        [HumanMessage(content="prompt")],
    )
    assert isinstance(result, StrategyOutput)
    assert captured["kwargs"]["model"] == "deepseek-ai/DeepSeek-V4.1-Flash-1017"
    assert captured["kwargs"]["base_url"] == "https://api.deepinfra.com/v1/openai"
    assert captured["kwargs"]["api_key"] == "fake-key"
    assert captured["method"] == "json_schema"
    assert captured["strict"] is True
    assert client.last_invocation is not None
    assert client.last_invocation["baseUrl"] == "https://api.deepinfra.com/v1/openai"


def test_invoke_matchup_gameplan_runs_load_and_generate() -> None:
    prepared = _prepared_sources()

    class FakeStore:
        def __init__(self) -> None:
            self.loaded = 0

        def load_sources(self, run_id):
            self.loaded += 1
            assert run_id
            return prepared

    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, sources, messages):
            self.calls += 1
            assert sources.sourceHash == prepared.sourceHash
            assert len(messages) == 1
            assert "ROLE" in messages[0].content
            assert "in English" in messages[0].content
            return StrategyOutput.model_validate(_strategy_payload())

    store = FakeStore()
    client = FakeClient()
    strategy = invoke_matchup_gameplan(
        run_id=uuid.uuid4(),
        sources_hash=prepared.sourceHash,
        execution_id="exec-1",
        store=store,
        client=client,
        output_locale="en",
    )
    assert strategy.gameplan.strengths[0].pokemon.slot == 0
    assert store.loaded == 1
    assert client.calls == 1


def test_invoke_matchup_gameplan_rejects_unknown_evidence_ids() -> None:
    prepared = _prepared_sources()

    class FakeStore:
        def load_sources(self, _run_id):
            return prepared

    class FakeClient:
        def generate(self, _sources, _messages):
            payload = _strategy_payload()
            payload["winCondition"]["evidenceBattleIds"] = ["missing"]
            return StrategyOutput.model_validate(payload)

    with pytest.raises(ValueError, match="unknown battle ids"):
        invoke_matchup_gameplan(
            run_id=uuid.uuid4(),
            sources_hash=prepared.sourceHash,
            execution_id="exec-2",
            store=FakeStore(),
            client=FakeClient(),
        )
