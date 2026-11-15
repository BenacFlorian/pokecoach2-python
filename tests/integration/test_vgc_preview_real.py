"""Preview mode — fixture bridge (default) or real BC when POKECOACH_VGC_REAL=1."""

from __future__ import annotations

from pokecoach_python.core.config import Settings, reset_settings_cache
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter

from tests.integration.sample_teams import OPPONENT_SNAPSHOT, SAMPLE_SNAPSHOT


def test_preview_fixture_bridge(fixture_bridge_env):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        req = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id="fixture",
            seed=7,
            timeout_seconds=30.0,
        )
        p1 = engine.preview(req)
        p2 = engine.preview(req)
        assert p1.opponent_lead_slots == p2.opponent_lead_slots
        assert len(p1.opponent_lead_slots) == 2
    finally:
        engine.close()


def test_preview_real_checkpoint(require_vgc_real, monkeypatch):
    monkeypatch.delenv("POKECOACH_BRIDGE_FIXTURE", raising=False)
    reset_settings_cache()
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        req = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id=settings.analysis_checkpoint_id,
            seed=1,
            timeout_seconds=120.0,
        )
        preview_a = engine.preview(req)
        preview_b = engine.preview(req)
        assert len(preview_a.opponent_lead_slots) == 2
        assert preview_a.opponent_lead_slots == preview_b.opponent_lead_slots
        assert preview_a.our_lead_slots == preview_b.our_lead_slots
    finally:
        engine.close()
