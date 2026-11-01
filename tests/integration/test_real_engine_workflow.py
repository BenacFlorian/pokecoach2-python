"""Integration: fixture bridge end-to-end (plan 04b, no Showdown required)."""

from __future__ import annotations

import os

import pytest

from pokecoach_python.core.config import Settings, reset_settings_cache
from pokecoach_python.engine.provenance import (
    assert_real_battles_eligible,
    build_run_provenance,
)
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter


@pytest.fixture
def fixture_env(monkeypatch):
    monkeypatch.setenv("POKECOACH_BRIDGE_FIXTURE", "1")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    reset_settings_cache()
    yield
    reset_settings_cache()


SAMPLE = {
    "pokemon": [
        {
            "species": "Incineroar",
            "moves": ["Fake Out", "Knock Off", "Parting Shot", "Flare Blitz"],
            "rawBlock": "Incineroar\n- Fake Out",
        }
    ]
    * 6
}


def test_fixture_provenance_not_llm_eligible(fixture_env):
    prov = build_run_provenance(
        engine_mode="vgc_bench",
        product_phases=["A"],
        hello={"engine": "fixture-bridge", "checkpointLoaded": False},
        checkpoint_id="x",
    )
    from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
    from pokecoach_python.engine.errors import EngineBridgeError

    rec = BattleRecord(
        preview=PreviewRecord(opponent_lead_slots=(0, 1)),
        turns=({"turn": 1, "ourActions": []},),
        outcome="win",
        participants={"ourFourSlots": [0, 1, 2, 3], "ourLeadSlots": [0, 1]},
        meta={"engine": "fixture-bridge", "terminalEvidence": {"kind": "x"}},
    )
    with pytest.raises(EngineBridgeError):
        assert_real_battles_eligible(prov, [rec])


def test_stub_capabilities_list_all_phases(fixture_env):
    settings = Settings(POKECOACH_ENGINE="stub", POSTGRES_PASSWORD="test")
    from pokecoach_python.engine.capabilities import engine_supported_phases
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    phases = engine_supported_phases(StubEngineAdapter(), settings)
    assert "A" in phases and "B" in phases
