"""Integration test fixtures (fixture bridge vs real Showdown)."""

from __future__ import annotations

import os

import pytest

from pokecoach_python.core.config import reset_settings_cache
from tests.integration.sample_teams import SAMPLE_SNAPSHOT

__all__ = ["SAMPLE_SNAPSHOT", "fixture_bridge_env", "require_vgc_real"]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "vgc_real: needs POKECOACH_VGC_REAL=1, checkpoint and local Showdown",
    )


@pytest.fixture
def fixture_bridge_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("POKECOACH_BRIDGE_FIXTURE", "1")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def require_vgc_real():
    if os.environ.get("POKECOACH_VGC_REAL") != "1":
        pytest.skip("set POKECOACH_VGC_REAL=1 with checkpoint + Showdown for real engine tests")
