from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlmodel import Session

from pokecoach_python.core.analysis_errors import AnalysisTargetNotFound
from pokecoach_python.core.config import Settings
from pokecoach_python.schemas.analysis_commands import AnalysisStartRequest
from pokecoach_python.services.analysis_commands import analysis_capabilities, start_analysis


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


def test_start_analysis_matchup_not_found_after_preflight(monkeypatch) -> None:
    matchup_id = uuid.uuid4()
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret", POKECOACH_ENGINE="stub")

    class Repo:
        def find_command(self, _key):
            return None

        def resolve_matchup_regulation_for_analysis(self, *_args, **_kwargs):
            return "M-B"

        def load_matchup_snapshots(self, *_args, **_kwargs):
            return ({}, {}, "M-B")

        def record_start_command(self, **kwargs):
            raise AnalysisTargetNotFound("matchup", kwargs["matchup_id"])

    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands._repo",
        lambda _session, _settings: Repo(),
    )
    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands._load_matchup",
        lambda _session, _mid: type(
            "Row",
            (),
            {"id": matchup_id, "regulation": "M-B", "is_deleted": False},
        )(),
    )
    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands._active_run_exists",
        lambda *_args, **_kwargs: False,
    )
    session = MagicMock(spec=Session)
    with pytest.raises(HTTPException) as exc:
        start_analysis(
            session,
            settings,
            matchup_id=matchup_id,
            idempotency_key=uuid.uuid4(),
            body=AnalysisStartRequest(target_phase="A", profile="smoke", locale="fr"),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "MATCHUP_NOT_FOUND"
