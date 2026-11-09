"""Worker process entrypoint."""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from pokecoach_python.core.config import get_settings, reset_settings_cache
from pokecoach_python.db.analysis_repository import AnalysisRepository, ClaimedRun
from pokecoach_python.db.session import create_db_engine
from pokecoach_python.workflow.runner import WorkflowRunner

logger = logging.getLogger(__name__)

# Verrou Postgres session : un seul worker par base (évite double claim / heartbeats fantômes).
_WORKER_SINGLETON_LOCK_KEY = 884_242

HEARTBEAT_INTERVAL = 10
POLL_IDLE_SECONDS = 1
THREAD_JOIN_POLL_SECONDS = 0.25
# In-flight engine/LLM calls may run until their configured timeout, then teardown.
_WORKER_JOIN_GRACE_AFTER_TIMEOUT_SECONDS = 30


def _try_acquire_worker_singleton_lock(engine: Engine) -> Connection | None:
    conn = engine.connect()
    acquired = conn.execute(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": _WORKER_SINGLETON_LOCK_KEY},
    ).scalar()
    if acquired:
        return conn
    conn.close()
    return None


def _release_worker_singleton_lock(conn: Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": _WORKER_SINGLETON_LOCK_KEY},
        )
    finally:
        conn.close()


class WorkerSupervisor:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._engine = create_db_engine(self._settings)
        self._repo = AnalysisRepository(self._engine, self._settings)
        self._runner = WorkflowRunner(self._repo, self._settings)
        self._stop = False
        self._active: tuple | None = None
        self._singleton_lock_conn: Connection | None = None

    def request_stop(self, *_args) -> None:
        self._stop = True

    def _process_claim(
        self,
        claim: ClaimedRun,
        *,
        repo: AnalysisRepository,
        runner: WorkflowRunner,
    ) -> None:
        run_id = claim.context_row.id
        token = claim.lease_token
        stop_event = threading.Event()
        if self._stop:
            stop_event.set()
        done = threading.Event()
        run_started = time.perf_counter()

        def _run() -> None:
            try:
                runner.run_claimed(claim, stop_event=stop_event)
            finally:
                done.set()

        worker_thread = threading.Thread(target=_run, daemon=True)
        worker_thread.start()
        last_beat = time.monotonic()

        while not done.is_set():
            if self._stop:
                stop_event.set()
            if done.wait(timeout=HEARTBEAT_INTERVAL):
                break
            if time.monotonic() - last_beat < HEARTBEAT_INTERVAL:
                continue
            try:
                heartbeat_ok = repo.heartbeat(run_id, token)
            except Exception:
                logger.exception("heartbeat error for run %s", run_id)
                heartbeat_ok = False
            if not heartbeat_ok:
                if worker_thread.is_alive():
                    logger.error("heartbeat lost for run %s", run_id)
                    stop_event.set()
                last_beat = time.monotonic()
                continue
            last_beat = time.monotonic()

        while worker_thread.is_alive():
            if self._stop and not stop_event.is_set():
                stop_event.set()
            worker_thread.join(timeout=THREAD_JOIN_POLL_SECONDS)

        if worker_thread.is_alive():
            logger.warning(
                "run %s worker thread still active after cooperative stop; "
                "remaining work is bounded by engine/LLM timeouts plus %ss cleanup",
                run_id,
                _WORKER_JOIN_GRACE_AFTER_TIMEOUT_SECONDS,
            )
            while worker_thread.is_alive():
                worker_thread.join(timeout=THREAD_JOIN_POLL_SECONDS)

        if done.is_set():
            logger.info(
                "finished run %s durationMs=%d",
                run_id,
                int((time.perf_counter() - run_started) * 1000),
            )

    def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self._singleton_lock_conn = _try_acquire_worker_singleton_lock(self._engine)
        if self._singleton_lock_conn is None:
            logger.error(
                "un autre worker PokeCoach tourne déjà sur cette base "
                "(verrou singleton %s) — arrêtez l’ancien processus avant de relancer",
                _WORKER_SINGLETON_LOCK_KEY,
            )
            sys.exit(2)
        logger.info(
            "worker started (POKECOACH_ENGINE=%s)",
            self._settings.engine_mode,
        )
        try:
            self._run_poll_loop()
        finally:
            _release_worker_singleton_lock(self._singleton_lock_conn)
            self._singleton_lock_conn = None
            logger.info("worker stopped")

    def _run_poll_loop(self) -> None:
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
            self._active = (run_id, claim.lease_token)
            try:
                repo = self._repo
                runner = self._runner
                self._process_claim(claim, repo=repo, runner=runner)
            finally:
                self._active = None


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    WorkerSupervisor().run_forever()


if __name__ == "__main__":
    main()
