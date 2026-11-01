"""Workflow shared types."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pokecoach_python.engine.contracts import BattleRecord, EngineAdapter, PreviewRecord
from pokecoach_python.llm.battle_sources import StoredDBattle
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
    engine: EngineAdapter | None
    report_progress: ProgressCallback
    preview_timeout_seconds: float = 30.0
    first_turn_timeout_seconds: float = 120.0
    full_battle_timeout_seconds: float = 300.0
    engine_mode: str = "stub"
    insert_battle: Callable[[BattleRecord, str], str] | None = None
    list_battles: Callable[[], Sequence[BattleRecord]] | None = None
    list_d_battles: Callable[[], Sequence[StoredDBattle]] | None = None
    run_provenance: dict[str, Any] = field(default_factory=dict)
    result_revision: int = 0
    settings: Any = None
    analysis_repository: Any = None
    synthesis_client: Any = None
    synthesis_store: Any = None


@dataclass(frozen=True)
class PhaseOutput:
    phase: Phase
    result: SimulationResultV2
    execution_slice: dict[str, Any] = field(default_factory=dict)
    metadata_patch: dict[str, Any] = field(default_factory=dict)
    audit_traces: tuple[PreviewRecord, ...] = ()


PhaseHandler = Callable[[PhaseContext], PhaseOutput]
