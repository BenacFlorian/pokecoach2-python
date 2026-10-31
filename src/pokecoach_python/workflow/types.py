"""Workflow shared types."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, EngineAdapter, PreviewRecord
from pokecoach_python.schemas.analysis_result import Phase, SimulationResultV2

ProgressCallback = Callable[[str, int, int], None]


@dataclass
class PhaseContext:
    run_id: uuid.UUID
    lease_token: uuid.UUID
    matchup_id: uuid.UUID
    regulation: str
    target_phase: Phase
    profile: str
    seed: int
    our_snapshot: dict[str, Any]
    opponent_snapshot: dict[str, Any]
    partial_result: dict[str, Any]
    parameters: dict[str, Any]
    engine: EngineAdapter
    report_progress: ProgressCallback
    preview_timeout_seconds: float = 30.0
    insert_battle: Callable[[BattleRecord, str], str] | None = None
    list_battles: Callable[[], Sequence[BattleRecord]] | None = None


@dataclass(frozen=True)
class PhaseOutput:
    phase: Phase
    result: SimulationResultV2
    execution_slice: dict[str, Any] = field(default_factory=dict)
    audit_traces: tuple[PreviewRecord, ...] = ()


PhaseHandler = Callable[[PhaseContext], PhaseOutput]
