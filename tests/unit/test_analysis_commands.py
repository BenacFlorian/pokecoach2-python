from __future__ import annotations

from fastapi import HTTPException

from pokecoach_python.core.config import Settings
from pokecoach_python.services.analysis_commands import analysis_capabilities


def test_analysis_capabilities_exposes_synthesis_available(monkeypatch) -> None:
    class FakeEngine:
        def hello(self):
            return {"supportedModes": ["preview", "first_turn", "full_battle"]}

        def preflight(self, *_args, **_kwargs):
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands.build_engine_adapter",
        lambda _settings: FakeEngine(),
    )
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key")
    capabilities = analysis_capabilities(settings)
    assert capabilities.synthesis_available is True
    assert capabilities.phases == ["A", "C", "B", "D"]


def test_analysis_capabilities_returns_synthesis_when_engine_is_down(monkeypatch) -> None:
    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands.build_engine_adapter",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("down")),
    )
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key")
    capabilities = analysis_capabilities(settings)
    assert capabilities.phases == []
    assert capabilities.synthesis_available is True


def test_analysis_capabilities_still_fails_without_engine_or_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands.build_engine_adapter",
        lambda _settings: (_ for _ in ()).throw(RuntimeError("down")),
    )
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")
    try:
        analysis_capabilities(settings)
        raise AssertionError("expected engine failure")
    except HTTPException as exc:
        assert exc.status_code == 503
