"""Subprocess client against fixture bridge (no Torch)."""

from __future__ import annotations

import sys
import time

import pytest

from pokecoach_python.core.config import Settings, reset_settings_cache
from pokecoach_python.engine.errors import EngineBridgeError, EngineUnavailableError
from pokecoach_python.engine.subprocess_client import VgcSubprocessClient
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter


@pytest.fixture
def fixture_env(monkeypatch):
    monkeypatch.setenv("POKECOACH_BRIDGE_FIXTURE", "1")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    reset_settings_cache()
    yield
    reset_settings_cache()


SAMPLE_SNAPSHOT = {
    "pokemon": [
        {"name": "A", "moves": ["Protect", "Moonblast", "Dazzling Gleam", "Tailwind"]},
        {"name": "B", "moves": ["Fake Out", "Knock Off", "Parting Shot", "Flare Blitz"]},
        {"name": "C", "moves": ["Earthquake", "Rock Slide", "Protect", "Wide Guard"]},
        {"name": "D", "moves": ["Hydro Pump", "Ice Beam", "Protect", "Muddy Water"]},
        {"name": "E", "moves": ["Thunderbolt", "Volt Switch", "Protect", "Electro Drift"]},
        {"name": "F", "moves": ["Heat Wave", "Overheat", "Protect", "Helping Hand"]},
    ]
}


def test_fixture_bridge_preflight_and_preview(fixture_env):
    settings = Settings(
        POKECOACH_ENGINE="vgc_bench",
        POSTGRES_PASSWORD="test",
    )
    engine = VgcBenchEngineAdapter(settings)
    try:
        caps = engine.preflight(
            {"regulation": "M-B", "checkpoint_id": "fixture"},
            (SAMPLE_SNAPSHOT, SAMPLE_SNAPSHOT),
        )
        assert caps.supports_preview
        hello = engine.hello()
        assert hello.get("engine") == "fixture-bridge"
        from pokecoach_python.engine.contracts import SimulationRequest

        req = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=SAMPLE_SNAPSHOT,
            regulation="M-B",
            checkpoint_id="fixture",
            seed=42,
            timeout_seconds=5.0,
        )
        preview = engine.preview(req)
        assert len(preview.opponent_lead_slots) == 2
        turn1 = engine.first_turn(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=SAMPLE_SNAPSHOT,
                regulation="M-B",
                checkpoint_id="fixture",
                seed=42,
                timeout_seconds=5.0,
                opponent_lead=preview.opponent_lead_slots,
                our_selection=(0, 1, 2, 3),
                our_lead_slots=preview.our_lead_slots or (0, 1),
            )
        )
        assert turn1.payload.get("opponentActions") or turn1.payload.get("actions")
        assert len(turn1.payload.get("ourActions") or []) == 2
        battle = engine.full_battle(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=SAMPLE_SNAPSHOT,
                regulation="M-B",
                checkpoint_id="fixture",
                seed=42,
                timeout_seconds=5.0,
                opponent_lead=preview.opponent_lead_slots,
            )
        )
        assert battle.outcome in ("win", "loss", "draw")
        assert battle.meta.get("terminalEvidence")
    finally:
        engine.close()


def test_vgc_bench_requires_checkpoint_without_fixture(monkeypatch):
    monkeypatch.delenv("POKECOACH_BRIDGE_FIXTURE", raising=False)
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    reset_settings_cache()
    settings = Settings(
        POKECOACH_ENGINE="vgc_bench",
        POSTGRES_PASSWORD="test",
        VGC_CHECKPOINT_PATH="",
    )
    with pytest.raises(EngineUnavailableError):
        VgcBenchEngineAdapter(settings)


def test_bridge_close_terminates_process(fixture_env):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    engine.hello()
    client = engine._client
    proc = client._proc
    assert proc is not None
    engine.close()
    assert proc.poll() is not None


def test_bridge_request_timeout_does_not_wait_for_blocked_reader():
    settings = Settings(POSTGRES_PASSWORD="test")
    client = VgcSubprocessClient(
        settings,
        argv=[sys.executable, "-c", "import time; time.sleep(5)"],
    )
    started = time.monotonic()
    try:
        with pytest.raises(EngineBridgeError) as exc_info:
            client.request("hello", {}, timeout_seconds=0.05)
        assert exc_info.value.code == "BRIDGE_TIMEOUT"
        assert time.monotonic() - started < 1
    finally:
        client.close()
