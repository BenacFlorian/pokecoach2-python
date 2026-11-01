"""Worker process entrypoint."""

from __future__ import annotations

import logging
import signal
import time

from pokecoach_python.core.config import get_settings, reset_settings_cache
from pokecoach_python.db.analysis_repository import AnalysisRepository
from pokecoach_python.db.session import create_db_engine
from pokecoach_python.workflow.runner import WorkflowRunner

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 10
POLL_IDLE_SECONDS = 1


class WorkerSupervisor:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._engine = create_db_engine(self._settings)
        self._repo = AnalysisRepository(self._engine, self._settings)
        self._runner = WorkflowRunner(self._repo, self._settings)
        self._stop = False
        self._active: tuple | None = None

    def request_stop(self, *_args) -> None:
        self._stop = True

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        logger.info(
            "worker started (POKECOACH_ENGINE=%s)",
            self._settings.engine_mode,
        )
        while not self._stop:
            expired = self._repo.fail_expired_leases()
            if expired:
                logger.warning("failed %s runs with expired leases", expired)
            claim = self._repo.claim_next()
            if claim is None:
                time.sleep(POLL_IDLE_SECONDS)
                continue
            run_id = claim.context_row.id
            matchup_id = claim.context_row.matchup_id
            target = claim.context_row.target_phase
            logger.info(
                "claimed run %s matchup=%s target=%s completed=%s",
                run_id,
                matchup_id,
                target,
                claim.context_row.partial_result.get("completedPhases") or [],
            )
            reset_settings_cache()
            self._settings = get_settings()
            self._repo = AnalysisRepository(self._engine, self._settings)
            self._runner = WorkflowRunner(self._repo, self._settings)
            logger.info(
                "processing run %s engine=%s checkpoint=%s",
                run_id,
                self._settings.engine_mode,
                self._settings.vgc_checkpoint_path or "(none)",
            )
            token = claim.lease_token
            self._active = (run_id, token)
            last_beat = time.monotonic()
            try:
                import threading

                done = threading.Event()

                def _run() -> None:
                    try:
                        self._runner.run_claimed(claim)
                    finally:
                        done.set()

                worker_thread = threading.Thread(target=_run, daemon=True)
                worker_thread.start()
                while not done.wait(timeout=HEARTBEAT_INTERVAL):
                    if self._stop:
                        break
                    if time.monotonic() - last_beat >= HEARTBEAT_INTERVAL:
                        if not self._repo.heartbeat(run_id, token):
                            logger.error("heartbeat lost for run %s", run_id)
                            break
                        last_beat = time.monotonic()
                worker_thread.join(timeout=5)
                if done.is_set():
                    logger.info("finished run %s", run_id)
            finally:
                self._active = None
        logger.info("worker stopped")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    WorkerSupervisor().run_forever()


if __name__ == "__main__":
    main()
