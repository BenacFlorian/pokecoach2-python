"""Seeded stub engine for tests and local wiring before VGC-Bench subprocess is configured."""

from __future__ import annotations

import hashlib
import sys
from typing import Any, Literal

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
            supports_full_battle=True,
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

    def _sample_our_lineup(self, seed: int) -> tuple[tuple[int, int, int, int], tuple[int, int]]:
        digest = hashlib.sha256(f"our-lineup:{seed}".encode()).digest()
        slots = list(range(6))
        picked: list[int] = []
        idx = 0
        while len(picked) < 4:
            slot = slots[(digest[idx] + idx) % 6]
            if slot not in picked:
                picked.append(slot)
            idx += 1
        four = tuple(sorted(picked))  # type: ignore[return-value]
        lead_a = picked[digest[4] % 4]
        lead_b = picked[(digest[5] % 3 + 1) % 4]
        if lead_b == lead_a:
            lead_b = picked[(picked.index(lead_a) + 1) % 4]
        our_lead = (lead_a, lead_b) if lead_a < lead_b else (lead_b, lead_a)
        return four, our_lead

    def _our_turn1_actions(self, seed: int, our_lead: tuple[int, int]) -> list[dict[str, Any]]:
        digest = hashlib.sha256(f"our-turn1:{seed}".encode()).digest()
        slot_a, slot_b = our_lead[0], our_lead[1]
        target_a = digest[1] % 6
        target_b = digest[2] % 6
        return [
            {
                "kind": "move",
                "actor": {"side": "ours", "slot": slot_a},
                "move": "Stub Move A",
                "targets": [
                    {"kind": "pokemon", "ref": {"side": "opponent", "slot": target_a}}
                ],
            },
            {
                "kind": "move",
                "actor": {"side": "ours", "slot": slot_b},
                "move": "Stub Move B",
                "targets": [
                    {"kind": "pokemon", "ref": {"side": "opponent", "slot": target_b}}
                ],
            },
        ]

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        if request.opponent_lead is None:
            raise ValueError("opponent_lead required for full_battle")
        lead = request.opponent_lead
        if lead[0] == lead[1]:
            raise ValueError("invalid opponent_lead")
        digest = hashlib.sha256(f"full-battle:{request.seed}".encode()).digest()
        if digest[0] == 0:
            raise ValueError("simulated battle rejection")
        if digest[1] == 0:
            return BattleRecord(
                preview=PreviewRecord(
                    opponent_lead_slots=lead,
                    our_lead_slots=None,
                    meta={"engine": "stub", "technical": True},
                ),
                turns=(),
                outcome="technical",
                participants={},
                meta={"engine": "stub"},
            )
        our_four, our_lead = self._sample_our_lineup(request.seed)
        outcome_roll = digest[8] % 10
        if outcome_roll == 0:
            outcome: Literal["win", "loss", "draw"] = "draw"
        elif outcome_roll <= 5:
            outcome = "win"
        else:
            outcome = "loss"
        our_actions = self._our_turn1_actions(request.seed, our_lead)
        return BattleRecord(
            preview=PreviewRecord(
                opponent_lead_slots=lead,
                our_lead_slots=our_lead,
                meta={"engine": "stub"},
            ),
            turns=(
                {
                    "turn": 1,
                    "ourActions": our_actions,
                },
            ),
            outcome=outcome,
            participants={
                "ourFourSlots": list(our_four),
                "ourLeadSlots": list(our_lead),
            },
            meta={"engine": "stub", "seed": request.seed},
        )
