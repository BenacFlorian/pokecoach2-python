from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.db.session import create_db_engine
from pokecoach_python.main import create_app


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if not re.search(r"(_test|/pokecoach2_test\b)", url):
        pytest.fail("TEST_DATABASE_URL must target an explicit test database")
    return url


@pytest.fixture(scope="module")
def demo_client():
    _require_test_database_url()
    settings = Settings(
        POSTGRES_PASSWORD=SecretStr(os.environ["WORKER_DB_PASSWORD"]),
        POSTGRES_HOST=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        POSTGRES_PORT=int(os.environ.get("POSTGRES_PORT", "5442")),
        POSTGRES_DB=os.environ.get("POSTGRES_TEST_DB", "pokecoach2_test"),
        POSTGRES_USER="pokecoach_worker",
        ENABLE_DEMO_SEED=True,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, settings


def test_demo_seed_integration(demo_client):
    client, settings = demo_client
    response = client.post("/api-python/demo/seed", json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["matchupId"] == "c3333333-3333-4333-8333-333333333301"

    engine = create_db_engine(settings)
    with Session(engine) as session:
        run_id = body["runId"]
        result = session.connection().execute(
            text("SELECT report FROM core.matchup_runs WHERE id = :rid"),
            {"rid": run_id},
        )
        report = result.scalar_one()
        assert report is not None
    engine.dispose()

    second = client.post("/api-python/demo/seed", json={})
    assert second.status_code == 200
    assert second.json()["counts"]["teams"] == 3
