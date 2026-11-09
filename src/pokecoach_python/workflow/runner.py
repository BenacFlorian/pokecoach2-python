"""Sequential phase execution for one claimed run."""

from __future__ import annotations

import logging
import time
from threading import Event

from pokecoach_python.core.analysis_errors import RunExecutionStopped
from pokecoach_python.db.analysis_repository import AnalysisRepository, ClaimedRun
from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.engine.factory import build_engine_adapter
from pokecoach_python.engine.provenance import (
    assert_run_engine_compatible,
    provenance_for_worker_compat,
)
from pokecoach_python.engine.seeds import run_base_seed
from pokecoach_python.schemas.analysis_result import Phase
from pokecoach_python.workflow.registry import handler_for, phase_order
from pokecoach_python.workflow.types import PhaseContext

logger = logging.getLogger(__name__)


class _ForbiddenEngine:
    def preflight(self, *_args, **_kwargs):
        raise RuntimeError("synthesis phase must not call engine.preflight")

    def preview(self, *_args, **_kwargs):
        raise RuntimeError("synthesis phase must not call engine.preview")

    def first_turn(self, *_args, **_kwargs):
        raise RuntimeError("synthesis phase must not call engine.first_turn")

    def full_battle(self, *_args, **_kwargs):
        raise RuntimeError("synthesis phase must not call engine.full_battle")

    def close(self) -> None:
        return None


def _phases_to_run(completed: list[str], target: Phase) -> list[Phase]:
    order = list(phase_order())
    target_idx = order.index(target)
    start_idx = len(completed)
    if start_idx > target_idx:
        return []
    return order[start_idx : target_idx + 1]


def _parse_seed(parameters: dict) -> int:
    return run_base_seed(parameters)


def _should_pause_after_phase(
    output_phase: Phase,
    target_phase: Phase,
    remaining_phases: list[Phase],
) -> bool:
    order = list(phase_order())
    out_idx = order.index(output_phase)
    target_idx = order.index(target_phase)
    if remaining_phases and handler_for(remaining_phases[0]) is not None:
        if out_idx < target_idx:
            return False
    return out_idx >= target_idx


def _defer_publish_after_phase(
    output_phase: Phase,
    remaining_phases: list[Phase],
) -> bool:
    """Skip DB publish when the next phase runs immediately in the same worker pass."""
    if not remaining_phases:
        return False
    next_phase = remaining_phases[0]
    if handler_for(next_phase) is None:
        return False
    chain = (("A", "C"), ("C", "B"), ("B", "D"))
    return (output_phase, next_phase) in chain


class WorkflowRunner:
    def __init__(self, repo: AnalysisRepository, settings) -> None:
        self._repo = repo
        self._settings = settings

    def run_claimed(self, claim: ClaimedRun, *, stop_event: Event | None = None) -> None:
        row = claim.context_row
        run_id = row.id
        token = claim.lease_token

        def ensure_active() -> None:
            if stop_event is not None and stop_event.is_set():
                raise RunExecutionStopped("supervisor_stop", run_id=run_id)
            self._repo.ensure_run_active(run_id, token)

        completed = list(row.partial_result.get("completedPhases") or [])
        pending = _phases_to_run(completed, row.target_phase)
        requires_engine = any(phase != "synthesis" for phase in pending)
        engine = None
        try:
            ensure_active()
            if not pending:
                logger.info(
                    "run %s: nothing to do (target=%s completed=%s)",
                    run_id,
                    row.target_phase,
                    completed,
                )
                return
            if requires_engine:
                assert_run_engine_compatible(
                    row.provenance, provenance_for_worker_compat(self._settings)
                )
                engine = build_engine_adapter(self._settings)
            else:
                engine = _ForbiddenEngine()
            logger.info(
                "run %s: phases %s (target=%s profile=%s)",
                run_id,
                pending,
                row.target_phase,
                row.parameters.get("profile", "standard"),
            )
            profile = str(row.parameters.get("profile", "standard"))
            seed = _parse_seed(row.parameters)
            accumulated_partial = dict(row.partial_result)
            run_started = time.perf_counter()

            def progress(phase: str, done: int, total: int) -> None:
                ensure_active()
                if not self._repo.update_progress(
                    run_id, token, phase=phase, completed=done, total=total
                ):
                    raise RunExecutionStopped("lease_lost", run_id=run_id)

            for index, phase in enumerate(pending):
                ensure_active()
                completed = list(accumulated_partial.get("completedPhases") or [])
                remaining = pending[index + 1 :]
                phase_started = time.perf_counter()
                if phase == "synthesis":
                    logger.info(
                        "run %s: phase E start elapsedSinceRunClaimMs=%d",
                        run_id,
                        int((phase_started - run_started) * 1000),
                    )
                handler = handler_for(phase)
                if handler is None:
                    if not completed:
                        raise RuntimeError(f"phase {phase} not implemented")
                    logger.info("run %s: pausing — phase %s not implemented", run_id, phase)
                    ensure_active()
                    self._repo.pause_for_implementation(run_id, token)
                    break
                battle_phase = phase if phase in ("C", "D") else None
                read_battle_phase = "D" if phase == "synthesis" else battle_phase

                def _insert_battle(rec: BattleRecord, key: str, bp=battle_phase) -> str:
                    if bp not in ("C", "D"):
                        raise RuntimeError("battles only supported for phases C and D")
                    ensure_active()
                    return str(
                        self._repo.insert_battle(
                            run_id,
                            token,
                            phase=bp,  # type: ignore[arg-type]
                            sample_key=key,
                            record=rec,
                            expected_opponent_lead=rec.preview.opponent_lead_slots,
                        )
                    )

                def _list_battles(bp=read_battle_phase) -> list[BattleRecord]:
                    if bp not in ("C", "D"):
                        return []
                    return self._repo.list_battles(run_id, phase=bp)  # type: ignore[arg-type]

                def _list_d_battles():
                    return self._repo.list_d_battles(run_id)

                ctx = PhaseContext(
                    run_id=run_id,
                    lease_token=token,
                    matchup_id=row.matchup_id,
                    regulation=row.regulation or self._settings.analysis_regulation_list()[0],
                    target_phase=row.target_phase,
                    profile=profile,
                    seed=seed,
                    our_snapshot=row.our_snapshot,
                    opponent_snapshot=row.opponent_snapshot,
                    partial_result=accumulated_partial,
                    parameters=dict(row.parameters),
                    engine=engine,
                    report_progress=progress,
                    preview_timeout_seconds=float(
                        self._settings.analysis_preview_timeout_seconds
                    ),
                    first_turn_timeout_seconds=float(
                        self._settings.engine_first_turn_timeout_seconds
                    ),
                    full_battle_timeout_seconds=float(
                        self._settings.engine_full_battle_timeout_seconds
                    ),
                    engine_mode=self._settings.engine_mode,
                    insert_battle=_insert_battle if battle_phase in ("C", "D") else None,
                    list_battles=_list_battles if read_battle_phase in ("C", "D") else None,
                    list_d_battles=_list_d_battles if phase == "synthesis" else None,
                    run_provenance=dict(row.provenance),
                    result_revision=row.result_revision,
                    settings=self._settings,
                    analysis_repository=self._repo,
                    ensure_active=ensure_active,
                )
                output = handler(ctx)
                ensure_active()
                phase_duration_ms = int((time.perf_counter() - phase_started) * 1000)
                logger.info(
                    "run %s: phase %s done durationMs=%d (pause=%s defer=%s)",
                    run_id,
                    output.phase,
                    phase_duration_ms,
                    _should_pause_after_phase(output.phase, row.target_phase, remaining),
                    _defer_publish_after_phase(output.phase, remaining),
                )
                if output.phase == "synthesis":
                    logger.info(
                        "run %s: phase E complete runClaimToPhaseECompleteMs=%d phaseEMs=%d",
                        run_id,
                        int((time.perf_counter() - run_started) * 1000),
                        phase_duration_ms,
                    )
                if _defer_publish_after_phase(output.phase, remaining):
                    accumulated_partial = output.result.model_dump(mode="json")
                    continue
                pause = _should_pause_after_phase(output.phase, row.target_phase, remaining)
                payload = output.result.model_dump(mode="json")
                ensure_active()
                if output.phase == "synthesis":
                    metadata_patch = (
                        output.metadata_patch
                        or {"phases": {"synthesis": output.execution_slice}}
                    )
                    self._repo.publish_complete(
                        run_id,
                        token,
                        expected_revision=row.result_revision,
                        result=payload,
                        execution_metadata_patch=metadata_patch,
                    )
                else:
                    self._repo.publish_phase(
                        run_id,
                        token,
                        expected_revision=row.result_revision,
                        partial_result=payload,
                        target_phase=row.target_phase,
                        execution_slice=output.execution_slice,
                        pause=pause,
                    )
                accumulated_partial = payload
                row = self._repo.load_run_row(run_id)
                if row is None:
                    raise RunExecutionStopped("missing_run", run_id=run_id)
                if pause:
                    break
        except RunExecutionStopped as stopped:
            logger.info("run %s execution stopped (%s)", run_id, stopped.reason)
        except Exception as exc:
            logger.exception("run %s failed: %s", run_id, exc)
            self._repo.fail_run(run_id, token, str(exc))
        finally:
            if engine is not None:
                engine.close()
