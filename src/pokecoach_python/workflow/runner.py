"""Sequential phase execution for one claimed run."""

from __future__ import annotations

import logging

from pokecoach_python.db.analysis_repository import AnalysisRepository, ClaimedRun
from pokecoach_python.engine.factory import build_engine_adapter
from pokecoach_python.schemas.analysis_result import Phase
from pokecoach_python.workflow.registry import handler_for, phase_order
from pokecoach_python.workflow.types import PhaseContext

logger = logging.getLogger(__name__)


def _phases_to_run(completed: list[str], target: Phase) -> list[Phase]:
    order = list(phase_order())
    target_idx = order.index(target)
    start_idx = len(completed)
    if start_idx > target_idx:
        return []
    return order[start_idx : target_idx + 1]


def _parse_seed(parameters: dict) -> int:
    raw = parameters.get("seed", "0")
    try:
        return int(str(raw), 16) if len(str(raw)) > 8 else int(str(raw))
    except ValueError:
        return abs(hash(str(raw))) % (2**31)


class WorkflowRunner:
    def __init__(self, repo: AnalysisRepository, settings) -> None:
        self._repo = repo
        self._settings = settings

    def run_claimed(self, claim: ClaimedRun) -> None:
        row = claim.context_row
        run_id = row.id
        token = claim.lease_token
        engine = build_engine_adapter(self._settings)
        try:
            completed = list(row.partial_result.get("completedPhases") or [])
            pending = _phases_to_run(completed, row.target_phase)
            if not pending:
                return
            profile = str(row.parameters.get("profile", "standard"))
            seed = _parse_seed(row.parameters)

            def progress(phase: str, done: int, total: int) -> None:
                if not self._repo.update_progress(
                    run_id, token, phase=phase, completed=done, total=total
                ):
                    raise RuntimeError("lost lease during progress")
                if self._repo.is_cancelled(run_id):
                    raise RuntimeError("run cancelled")

            for phase in pending:
                completed = list(row.partial_result.get("completedPhases") or [])
                handler = handler_for(phase)
                if handler is None:
                    if not completed:
                        raise RuntimeError(f"phase {phase} not implemented")
                    self._repo.pause_for_implementation(run_id, token)
                    break
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
                    partial_result=dict(row.partial_result),
                    parameters=dict(row.parameters),
                    engine=engine,
                    report_progress=progress,
                    preview_timeout_seconds=float(
                        self._settings.analysis_preview_timeout_seconds
                    ),
                )
                output = handler(ctx)
                order = list(phase_order())
                pause = order.index(output.phase) >= order.index(row.target_phase)
                payload = output.result.model_dump(mode="json")
                self._repo.publish_phase(
                    run_id,
                    token,
                    expected_revision=row.result_revision,
                    partial_result=payload,
                    target_phase=row.target_phase,
                    execution_slice=output.execution_slice,
                    pause=pause,
                )
                row = self._repo.load_run_row(run_id)
                if row is None:
                    raise RuntimeError("run missing after publish")
                if pause:
                    break
        except Exception as exc:
            logger.exception("run %s failed: %s", run_id, exc)
            self._repo.fail_run(run_id, token, str(exc))
        finally:
            engine.close()
