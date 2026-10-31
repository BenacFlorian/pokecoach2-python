"""Seeded stub engine for tests and local wiring before VGC-Bench subprocess is configured."""

from __future__ import annotations

import hashlib
import sys
from typing import Any

from pokecoach_python.engine.contracts import (
    BattleRecord,
    EngineAdapter,
    EngineCapabilities,
    PreviewRecord,
    SimulationRequest,
    TurnOneRecord,
)


class StubEngineAdapter(EngineAdapter):
    """Stochastic previews from run seed + attempt index (reproducible)."""

    def preflight(
        self,
        config: dict[str, Any],
        snapshots: tuple[dict[str, Any], dict[str, Any]],
    ) -> EngineCapabilities:
        regulation = str(config.get("regulation", "M-B"))
        checkpoint = str(config.get("checkpoint_id", "stub-bc-v1"))
        fp = hashlib.sha256(checkpoint.encode()).hexdigest()[:16]
        return EngineCapabilities(
            regulation=regulation,
            checkpoint_id=checkpoint,
            checkpoint_fingerprint=fp,
            supports_preview=True,
            supports_first_turn=True,
            supports_full_battle=False,
            stochastic=True,
            python_version=sys.version.split()[0],
            notes=("stub adapter — configure VGC_BENCH for production engine",),
        )

    def preview(self, request: SimulationRequest) -> PreviewRecord:
        digest = hashlib.sha256(
            f"{request.seed}:{request.timeout_seconds}".encode()
        ).digest()
        slots = sorted(
            {
                digest[0] % 6,
                (digest[1] + 1) % 6,
            }
        )
        if slots[0] == slots[1]:
            slots[1] = (slots[1] + 1) % 6
        ordered = (digest[2] % 6, digest[3] % 6)
        if ordered[0] == ordered[1]:
            ordered = (ordered[0], (ordered[0] + 1) % 6)
        return PreviewRecord(
            opponent_lead_slots=(ordered[0], ordered[1]),
            our_lead_slots=(slots[0], slots[1]),
            meta={"engine": "stub"},
        )

    def first_turn(self, request: SimulationRequest) -> TurnOneRecord:
        """Synthetic turn-1 actions until VGC-Bench implements real first_turn."""
        if request.opponent_lead is None:
            raise ValueError("opponent_lead required for first_turn")
        lead = request.opponent_lead
        if lead[0] == lead[1]:
            raise ValueError("invalid opponent_lead")
        digest = hashlib.sha256(f"first-turn:{request.seed}".encode()).digest()
        if digest[0] == 0:
            raise ValueError("simulated lead rejection")
        slot_a, slot_b = lead[0], lead[1]
        target_a = digest[1] % 6
        target_b = digest[2] % 6
        if digest[3] % 5 == 0:
            action_a: dict[str, Any] = {
                "kind": "switch",
                "actor": {"side": "opponent", "slot": slot_a},
                "switchTo": {"side": "opponent", "slot": (digest[4] % 6)},
            }
        else:
            action_a = {
                "kind": "move",
                "actor": {"side": "opponent", "slot": slot_a},
                "move": "Stub Move A",
                "targets": [
                    {"kind": "pokemon", "ref": {"side": "ours", "slot": target_a}}
                ],
            }
        if digest[5] % 4 == 0:
            action_b = {
                "kind": "move",
                "actor": {"side": "opponent", "slot": slot_b},
                "move": "Stub Move B",
                "targets": [{"kind": "zone", "zone": "all-opponents"}],
            }
        else:
            action_b = {
                "kind": "move",
                "actor": {"side": "opponent", "slot": slot_b},
                "move": "Stub Move B",
                "targets": [
                    {"kind": "pokemon", "ref": {"side": "ours", "slot": target_b}}
                ],
            }
        if digest[6] % 7 == 0:
            action_b["terastallize"] = "Fire"
        back_pool = [s for s in range(6) if s not in {slot_a, slot_b}]
        back_idx = digest[7] % max(1, len(back_pool) - 1)
        back_pair = sorted((back_pool[back_idx], back_pool[(back_idx + 1) % len(back_pool)]))
        preview_digest = hashlib.sha256(f"our-lead:{request.seed}".encode()).digest()
        our_slots = sorted({preview_digest[0] % 6, (preview_digest[0] + 2) % 6})
        payload: dict[str, Any] = {
            "actions": [action_a, action_b],
            "backPair": back_pair,
            "ourLeadSlots": our_slots,
            "endStateNotes": [f"stub turn1 lead {slot_a}-{slot_b}"],
        }
        return TurnOneRecord(
            opponent_lead_slots=lead,
            payload=payload,
        )

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        raise NotImplementedError("stub engine does not implement full_battle")
