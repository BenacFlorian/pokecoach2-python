"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from pokecoach_python.core.config import Settings, reset_settings_cache


@pytest.fixture(autouse=True)
def _reset_settings():
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        APP_ENV="local",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=5442,
        POSTGRES_DB="pokecoach2_test",
        POSTGRES_USER="pokecoach_worker",
        POSTGRES_PASSWORD=SecretStr(os.environ.get("WORKER_DB_PASSWORD", "test-worker-password")),
        DB_CONNECT_TIMEOUT_SECONDS=5,
        ENABLE_DEMO_SEED=False,
    )
