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
            supports_first_turn=False,
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
        raise NotImplementedError("stub engine does not implement first_turn")

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        raise NotImplementedError("stub engine does not implement full_battle")
