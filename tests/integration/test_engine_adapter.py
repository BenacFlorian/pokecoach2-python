from pokecoach_python.engine.contracts import SimulationRequest
from pokecoach_python.engine.stub_adapter import StubEngineAdapter


def test_stub_preview_reproducible():
    engine = StubEngineAdapter()
    caps = engine.preflight({"regulation": "M-B"}, ({}, {}))
    assert caps.supports_preview
    req = SimulationRequest(
        our_snapshot={},
        opponent_snapshot={},
        regulation="M-B",
        checkpoint_id="stub",
        seed=12345,
        timeout_seconds=5.0,
    )
    first = engine.preview(req)
    second = engine.preview(req)
    assert first.opponent_lead_slots == second.opponent_lead_slots
