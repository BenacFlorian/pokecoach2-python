"""Phase handler registry."""

from __future__ import annotations

from pokecoach_python.schemas.analysis_result import Phase
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.types import PhaseHandler

_ORDER: tuple[Phase, ...] = ("A", "B", "C", "D", "synthesis")

_HANDLERS: dict[Phase, PhaseHandler] = {
    "A": run_phase_a,
    "B": run_phase_b,
}


def phase_order() -> tuple[Phase, ...]:
    return _ORDER


def handler_for(phase: Phase) -> PhaseHandler | None:
    return _HANDLERS.get(phase)


def implemented_phases() -> tuple[Phase, ...]:
    return tuple(_HANDLERS.keys())


def deployed_handlers(deployed: list[str]) -> dict[Phase, PhaseHandler]:
    return {phase: _HANDLERS[phase] for phase in deployed if phase in _HANDLERS}  # type: ignore[misc]
