from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from pokecoach_python.core.config import Settings
from pokecoach_python.main import create_app
from pokecoach_python.schemas.demo import DemoSeedCounts, DemoSeedResponse


def _with_lifespan_mocks():
    stack = ExitStack()
    engine = MagicMock()
    stack.enter_context(patch("pokecoach_python.main.create_db_engine", return_value=engine))
    stack.enter_context(patch("pokecoach_python.main.verify_db_connection"))
    return stack


def _demo_response() -> DemoSeedResponse:
    return DemoSeedResponse(
        source="mock",
        fixtureVersion=1,
        ownedTeamIds=[
            "a1111111-1111-4111-8111-111111111101",
            "a1111111-1111-4111-8111-111111111102",
        ],
        opponentTeamId="b2222222-2222-4222-8222-222222222201",
        matchupId="c3333333-3333-4333-8333-333333333301",
        runId="f6666666-6666-4666-8666-666666666601",
        counts=DemoSeedCounts(teams=3, matchups=1, runs=1),
    )


def test_demo_disabled_returns_404_without_db():
    settings = Settings(
        POSTGRES_PASSWORD=SecretStr("secret"),
        ENABLE_DEMO_SEED=False,
    )
    with _with_lifespan_mocks(), patch("pokecoach_python.api.demo.get_session") as get_session:
        app = create_app(settings)
        with TestClient(app) as client:
            response = client.post("/api-python/demo/seed", json={})
    get_session.assert_not_called()
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "DEMO_DISABLED"


def test_demo_rejects_extra_fields(test_settings):
    test_settings.enable_demo_seed = True
    with _with_lifespan_mocks():
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.post("/api-python/demo/seed", json={"matchupId": "x"})
    assert response.status_code == 422


def test_demo_success(test_settings):
    test_settings.enable_demo_seed = True
    with _with_lifespan_mocks(), patch(
        "pokecoach_python.api.demo.reset_demo_seed",
        return_value=_demo_response(),
    ):
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.post("/api-python/demo/seed", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["fixtureVersion"] == 1
    assert len(body["ownedTeamIds"]) == 2


def test_demo_busy_maps_to_409(test_settings):
    test_settings.enable_demo_seed = True
    exc = HTTPException(
        status_code=409,
        detail={"code": "DEMO_BUSY", "message": "busy"},
    )
    with _with_lifespan_mocks(), patch(
        "pokecoach_python.api.demo.reset_demo_seed",
        side_effect=exc,
    ):
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.post("/api-python/demo/seed", json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DEMO_BUSY"


def test_demo_no_secrets_in_error(test_settings):
    test_settings.enable_demo_seed = True
    exc = HTTPException(
        status_code=500,
        detail={"code": "DEMO_RESET_FAILED", "message": "failed"},
    )
    with _with_lifespan_mocks(), patch(
        "pokecoach_python.api.demo.reset_demo_seed",
        side_effect=exc,
    ):
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.post("/api-python/demo/seed", json={})
    assert response.status_code == 500
    assert test_settings.postgres_password.get_secret_value() not in response.text
