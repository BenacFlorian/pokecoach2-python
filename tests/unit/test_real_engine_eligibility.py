from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.engine.provenance import (
    assert_real_battles_eligible,
    build_run_provenance,
)
from pokecoach_python.engine.errors import EngineBridgeError
import pytest


def test_stub_run_rejected_for_llm():
    prov = build_run_provenance(
        engine_mode="stub",
        product_phases=["A"],
        hello=None,
        checkpoint_id="stub-bc-v1",
    )
    record = BattleRecord(
        preview=PreviewRecord(opponent_lead_slots=(0, 1)),
        turns=({"turn": 1, "ourActions": []},),
        outcome="win",
        participants={"ourFourSlots": [0, 1, 2, 3], "ourLeadSlots": [0, 1]},
        meta={"engine": "stub", "terminalEvidence": {"kind": "x"}},
    )
    with pytest.raises(EngineBridgeError):
        assert_real_battles_eligible(prov, [record])
