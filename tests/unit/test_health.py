from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from pokecoach_python.main import create_app


def test_import_main_does_not_connect():
    import pokecoach_python.main as main_module

    assert callable(main_module.create_app)


def test_health_ok(test_settings):
    engine = MagicMock()
    session_cm = MagicMock()
    session = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = False

    with (
        patch("pokecoach_python.main.create_db_engine", return_value=engine),
        patch("pokecoach_python.main.verify_db_connection"),
        patch("pokecoach_python.api.health.Session", return_value=session_cm),
    ):
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_db_unavailable(test_settings):
    engine = MagicMock()
    with (
        patch("pokecoach_python.main.create_db_engine", return_value=engine),
        patch("pokecoach_python.main.verify_db_connection"),
        patch("pokecoach_python.api.health.Session") as session_cls,
    ):
        session_cls.side_effect = SQLAlchemyError("boom")
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert "password" not in response.text.lower()


def test_health_response_has_no_secrets(test_settings):
    engine = MagicMock()
    session_cm = MagicMock()
    session = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = False
    with (
        patch("pokecoach_python.main.create_db_engine", return_value=engine),
        patch("pokecoach_python.main.verify_db_connection"),
        patch("pokecoach_python.api.health.Session", return_value=session_cm),
    ):
        app = create_app(test_settings)
        with TestClient(app) as client:
            response = client.get("/health")
    assert test_settings.postgres_password.get_secret_value() not in response.text
