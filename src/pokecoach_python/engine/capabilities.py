"""Resolve deployed analysis phases from engine support (plan 04b task 6)."""

from __future__ import annotations

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import EngineAdapter
from pokecoach_python.workflow.registry import phase_order


def engine_supported_phases(engine: EngineAdapter, settings: Settings) -> list[str]:
    configured = settings.analysis_deployed_phase_list()
    execution_order = [p for p in phase_order() if p != "synthesis"]
    if settings.engine_mode.lower() == "stub":
        return [p for p in execution_order if p in configured]
    hello = engine.hello()
    modes = set(hello.get("supportedModes") or [])
    allowed: set[str] = set()
    if "preview" in modes:
        allowed.add("A")
    if "first_turn" in modes:
        allowed.add("B")
    if "full_battle" in modes:
        allowed.update({"C", "D"})
    if "C" not in allowed:
        allowed.discard("B")
    return [p for p in execution_order if p in configured and p in allowed]


def synthesis_available(settings: Settings) -> bool:
    return settings.synthesis_enabled()
