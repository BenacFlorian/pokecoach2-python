"""First turn (phase B) — fixture or real."""

from __future__ import annotations

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter

from tests.integration.sample_teams import OPPONENT_SNAPSHOT, SAMPLE_SNAPSHOT


def test_first_turn_moves_from_sets(fixture_bridge_env):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        base = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id="fixture",
            seed=99,
            timeout_seconds=30.0,
        )
        preview = engine.preview(base)
        turn1 = engine.first_turn(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=OPPONENT_SNAPSHOT,
                regulation="M-B",
                checkpoint_id="fixture",
                seed=99,
                timeout_seconds=30.0,
                opponent_lead=preview.opponent_lead_slots,
            )
        )
        moves = [a.get("move") for a in turn1.payload.get("actions", [])]
        assert all(isinstance(m, str) and m for m in moves)
        assert turn1.payload.get("backPair")
    finally:
        engine.close()


def test_first_turn_real(require_vgc_real):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        base = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id=settings.analysis_checkpoint_id,
            seed=2,
            timeout_seconds=120.0,
        )
        preview = engine.preview(base)
        turn1 = engine.first_turn(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=OPPONENT_SNAPSHOT,
                regulation="M-B",
                checkpoint_id=settings.analysis_checkpoint_id,
                seed=2,
                timeout_seconds=120.0,
                opponent_lead=preview.opponent_lead_slots,
            )
        )
        assert len(turn1.payload.get("actions", [])) == 2
    finally:
        engine.close()
