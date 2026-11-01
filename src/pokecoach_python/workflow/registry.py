"""Phase handler registry."""

from __future__ import annotations

from pokecoach_python.schemas.analysis_result import Phase, phase_execution_order
from pokecoach_python.workflow.phases.phase_a import run_phase_a
from pokecoach_python.workflow.phases.phase_b import run_phase_b
from pokecoach_python.workflow.phases.phase_c import run_phase_c
from pokecoach_python.workflow.phases.phase_d import run_phase_d
from pokecoach_python.workflow.phases.phase_e import run_phase_e
from pokecoach_python.workflow.types import PhaseHandler

_HANDLERS: dict[Phase, PhaseHandler] = {
    "A": run_phase_a,
    "C": run_phase_c,
    "B": run_phase_b,
    "D": run_phase_d,
    "synthesis": run_phase_e,
}


def phase_order() -> tuple[Phase, ...]:
    return phase_execution_order()


def handler_for(phase: Phase) -> PhaseHandler | None:
    return _HANDLERS.get(phase)


def implemented_phases() -> tuple[Phase, ...]:
    return tuple(_HANDLERS.keys())


def deployed_handlers(deployed: list[str]) -> dict[Phase, PhaseHandler]:
    return {phase: _HANDLERS[phase] for phase in deployed if phase in _HANDLERS}  # type: ignore[misc]
