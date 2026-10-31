"""Engine adapter contracts (workflow plan 04 — not VGC-Bench API surface)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class TeamSnapshot:
    pokemon: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class SimulationRequest:
    our_snapshot: dict[str, Any]
    opponent_snapshot: dict[str, Any]
    regulation: str
    checkpoint_id: str
    seed: int
    timeout_seconds: float
    opponent_lead: tuple[int, int] | None = None
    opponent_four: tuple[int, int, int, int] | None = None
    our_selection: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class EngineCapabilities:
    regulation: str
    checkpoint_id: str
    checkpoint_fingerprint: str
    supports_preview: bool
    supports_first_turn: bool
    supports_full_battle: bool
    stochastic: bool
    python_version: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreviewRecord:
    opponent_lead_slots: tuple[int, int]
    our_lead_slots: tuple[int, int] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnOneRecord:
    opponent_lead_slots: tuple[int, int]
    payload: dict[str, Any]


@dataclass(frozen=True)
class BattleRecord:
    preview: PreviewRecord
    turns: tuple[dict[str, Any], ...]
    outcome: Literal["win", "loss", "draw", "technical"]
    participants: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)


class EngineAdapter:
    """Protocol implemented by VGC-Bench and test doubles."""

    def preflight(
        self,
        config: dict[str, Any],
        snapshots: tuple[dict[str, Any], dict[str, Any]],
    ) -> EngineCapabilities:
        raise NotImplementedError

    def preview(self, request: SimulationRequest) -> PreviewRecord:
        raise NotImplementedError

    def first_turn(self, request: SimulationRequest) -> TurnOneRecord:
        raise NotImplementedError

    def full_battle(self, request: SimulationRequest) -> BattleRecord:
        raise NotImplementedError

    def close(self) -> None:
        return None
