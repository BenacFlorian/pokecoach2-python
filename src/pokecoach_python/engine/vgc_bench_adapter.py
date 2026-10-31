"""Optional VGC-Bench subprocess adapter (see docs/audits/vgc-bench.md)."""

from __future__ import annotations

from typing import Any

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import (
    BattleRecord,
    EngineAdapter,
    EngineCapabilities,
    PreviewRecord,
    SimulationRequest,
    TurnOneRecord,
)
from pokecoach_python.engine.stub_adapter import StubEngineAdapter


class VgcBenchEngineAdapter(EngineAdapter):
    """Delegates to stub until a pinned VGC-Bench JSON worker is wired."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._inner = StubEngineAdapter()

    def preflight(
        self,
        config: dict[str, Any],
        snapshots: tuple[dict[str, Any], dict[str, Any]],
    ) -> EngineCapabilities:
        caps = self._inner.preflight(config, snapshots)
        notes = (
            *caps.notes,
            f"vgc_bench_root={self._settings.vgc_bench_root or 'unset'}",
        )
        return EngineCapabilities(
            regulation=caps.regulation,
            checkpoint_id=caps.checkpoint_id,
            checkpoint_fingerprint=caps.checkpoint_fingerprint,
            supports_preview=caps.supports_preview,
            supports_first_turn=caps.supports_first_turn,
            supports_full_battle=caps.supports_full_battle,
            stochastic=caps.stochastic,
            python_version=caps.python_version,
            notes=notes,
        )

    def preview(self, request: SimulationRequest) -> PreviewRecord:
        return self._inner.preview(request)

    def first_turn(self, request: SimulationRequest) -> TurnOneRecord:
        return self._inner.first_turn(request)

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        return self._inner.full_battle(request)
