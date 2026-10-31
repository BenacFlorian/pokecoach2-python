from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import text
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.db.session import create_db_engine


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if not re.search(r"(_test|/pokecoach2_test\b)", url):
        pytest.fail("TEST_DATABASE_URL must target an explicit test database")
    return url


@pytest.fixture(scope="module")
def engine():
    url = _require_test_database_url()
    settings = Settings(
        POSTGRES_PASSWORD=os.environ.get("WORKER_DB_PASSWORD", "test"),
        POSTGRES_HOST=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        POSTGRES_PORT=int(os.environ.get("POSTGRES_PORT", "5442")),
        POSTGRES_DB=url.rsplit("/", 1)[-1],
        POSTGRES_USER="pokecoach_worker",
    )
    eng = create_db_engine(settings)
    yield eng
    eng.dispose()


def test_worker_can_select_teams(engine):
    with Session(engine) as session:
        count = session.exec(text("SELECT COUNT(*) FROM core.teams")).one()
        assert count is not None


def test_isolated_sessions(engine):
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
        session.rollback()
    with Session(engine) as session:
        session.exec(text("SELECT 1"))
