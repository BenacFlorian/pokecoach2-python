"""Full battle records for C/D — fixture or real."""

from __future__ import annotations

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter
from pokecoach_python.workflow.battle_records import validate_real_engine_battle

from tests.integration.sample_teams import OPPONENT_SNAPSHOT, SAMPLE_SNAPSHOT


def test_full_battle_terminal_evidence(fixture_bridge_env):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        base = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id="fixture",
            seed=11,
            timeout_seconds=30.0,
        )
        preview = engine.preview(base)
        battle = engine.full_battle(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=OPPONENT_SNAPSHOT,
                regulation="M-B",
                checkpoint_id="fixture",
                seed=11,
                timeout_seconds=30.0,
                opponent_lead=preview.opponent_lead_slots,
            )
        )
        assert battle.meta.get("terminalEvidence")
        assert battle.turns
        assert battle.turns[0].get("ourActions")
    finally:
        engine.close()


def test_full_battle_real(require_vgc_real):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        base = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id=settings.analysis_checkpoint_id,
            seed=3,
            timeout_seconds=180.0,
        )
        preview = engine.preview(base)
        battle = engine.full_battle(
            SimulationRequest(
                our_snapshot=SAMPLE_SNAPSHOT,
                opponent_snapshot=OPPONENT_SNAPSHOT,
                regulation="M-B",
                checkpoint_id=settings.analysis_checkpoint_id,
                seed=3,
                timeout_seconds=180.0,
                opponent_lead=preview.opponent_lead_slots,
            )
        )
        validate_real_engine_battle(battle, expected_engine="vgc-bench")
    finally:
        engine.close()
