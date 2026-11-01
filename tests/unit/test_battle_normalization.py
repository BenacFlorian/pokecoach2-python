"""Round-trip and validation for normalized battle records (plan 04b task 3)."""

from __future__ import annotations

import json
from pathlib import Path

from pokecoach_python.engine.contracts import BattleRecord, PreviewRecord
from pokecoach_python.workflow.battle_records import (
    battle_payload_dict,
    battle_record_from_payload,
    validate_real_engine_battle,
)


def test_battle_record_round_trip():
    record = BattleRecord(
        preview=PreviewRecord(opponent_lead_slots=(0, 1), our_lead_slots=(2, 3)),
        turns=({"turn": 1, "ourActions": [], "opponentActions": []},),
        outcome="win",
        participants={"ourFourSlots": [0, 1, 2, 3], "ourLeadSlots": [2, 3]},
        meta={
            "engine": "fixture-bridge",
            "terminalEvidence": {"kind": "simulator", "turnCount": 1},
        },
    )
    payload = battle_payload_dict(record)
    restored = battle_record_from_payload(payload)
    assert restored.outcome == record.outcome
    assert restored.meta.get("terminalEvidence")


def test_validate_real_engine_record():
    record = BattleRecord(
        preview=PreviewRecord(opponent_lead_slots=(0, 1)),
        turns=({"turn": 1, "ourActions": [{"kind": "move"}]},),
        outcome="win",
        participants={"ourFourSlots": [0, 1, 2, 3], "ourLeadSlots": [0, 1]},
        meta={
            "engine": "vgc-bench",
            "terminalEvidence": {"kind": "simulator", "finished": True, "turnCount": 1},
            "terminalState": {
                "ours": {
                    "selectedSlots": [0, 1, 2, 3],
                    "enteredSlots": [0, 1],
                    "survivorSlots": [0, 1],
                },
                "opponent": {
                    "selectedSlots": [0, 1, 2, 3],
                    "enteredSlots": [0, 1],
                    "survivorSlots": [],
                },
            },
        },
    )
    validate_real_engine_battle(record, expected_engine="vgc-bench")


def test_reference_turn1_fixture_shape():
    path = Path(__file__).resolve().parents[1] / "fixtures/engine-real/reference-turn1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["actions"]) == 2
