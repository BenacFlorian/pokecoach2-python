"""Phase D lineup constraints on full_battle payload."""

from __future__ import annotations

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.vgc_bench_adapter import VgcBenchEngineAdapter

from tests.integration.sample_teams import OPPONENT_SNAPSHOT, SAMPLE_SNAPSHOT


def test_full_battle_honors_our_selection(fixture_bridge_env):
    settings = Settings(POKECOACH_ENGINE="vgc_bench", POSTGRES_PASSWORD="test")
    engine = VgcBenchEngineAdapter(settings)
    try:
        our_four = (0, 1, 2, 3)
        our_lead = (0, 1)
        base = SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT,
            opponent_snapshot=OPPONENT_SNAPSHOT,
            regulation="M-B",
            checkpoint_id="fixture",
            seed=20,
            timeout_seconds=30.0,
            opponent_lead=(4, 5),
            our_selection=our_four,
            our_lead_slots=our_lead,
        )
        battle = engine.full_battle(base)
        participants = battle.participants or {}
        assert tuple(sorted(participants.get("ourFourSlots") or [])) == our_four
        assert tuple(participants.get("ourLeadSlots") or []) == our_lead
    finally:
        engine.close()
