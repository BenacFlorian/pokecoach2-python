from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

from pokecoach_python.core.config import Settings
from pokecoach_python.db.analysis_repository import ClaimedRun, RunRow
from pokecoach_python.worker import WorkerSupervisor


def _row(run_id: uuid.UUID | None = None) -> RunRow:
    rid = run_id or uuid.uuid4()
    return RunRow(
        id=rid,
        matchup_id=uuid.uuid4(),
        status="running",
        target_phase="A",
        partial_result={"completedPhases": [], "schemaVersion": 2, "source": "simulation"},
        result_revision=0,
        parameters={"profile": "smoke", "seed": "1"},
        regulation="M-B",
        our_snapshot={"pokemon": []},
        opponent_snapshot={"pokemon": []},
        process_status="PENDING STATS",
        provenance={},
    )


@dataclass
class _FakeClaim:
    context_row: RunRow
    lease_token: uuid.UUID


def test_process_claim_waits_for_thread_before_return(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()
    claimed_b = threading.Event()
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")

    class FakeRepo:
        def heartbeat(self, *_args, **_kwargs):
            return False

    class FakeRunner:
        def __init__(self) -> None:
            self.claims: list[uuid.UUID] = []

        def run_claimed(self, claim, *, stop_event=None) -> None:
            self.claims.append(claim.context_row.id)
            started.set()
            release.wait(timeout=5)

    class UnderTest(WorkerSupervisor):
        def __init__(self) -> None:
            self._settings = settings
            self._engine = object()
            self._repo = FakeRepo()
            self._runner = FakeRunner()
            self._stop = False
            self._active = None

    supervisor = UnderTest()
    run_a = _row()
    run_b = _row()

    def run_a_thread() -> None:
        supervisor._process_claim(
            ClaimedRun(context_row=run_a, lease_token=uuid.uuid4()),
            repo=supervisor._repo,
            runner=supervisor._runner,
        )
        supervisor._process_claim(
            ClaimedRun(context_row=run_b, lease_token=uuid.uuid4()),
            repo=supervisor._repo,
            runner=supervisor._runner,
        )
        claimed_b.set()

    worker = threading.Thread(target=run_a_thread, daemon=True)
    worker.start()
    assert started.wait(timeout=2)
    assert not claimed_b.is_set()
    release.set()
    assert claimed_b.wait(timeout=5)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert supervisor._runner.claims == [run_a.id, run_b.id]


def test_process_claim_completes_when_runner_returns_immediately() -> None:
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")

    class FakeRepo:
        def heartbeat(self, *_args, **_kwargs):
            return False

    class FakeRunner:
        def run_claimed(self, _claim, *, stop_event=None) -> None:
            return None

    class UnderTest(WorkerSupervisor):
        def __init__(self) -> None:
            self._settings = settings
            self._engine = object()
            self._repo = FakeRepo()
            self._runner = FakeRunner()
            self._stop = False
            self._active = None

    supervisor = UnderTest()
    supervisor._process_claim(
        ClaimedRun(context_row=_row(), lease_token=uuid.uuid4()),
        repo=supervisor._repo,
        runner=supervisor._runner,
    )


def test_supervisor_stop_sets_stop_event(monkeypatch) -> None:
    settings = Settings(_env_file=None, POSTGRES_PASSWORD="secret")
    seen: list[bool] = []

    class FakeRepo:
        def heartbeat(self, *_args, **_kwargs):
            return False

    class FakeRunner:
        def run_claimed(self, _claim, *, stop_event=None) -> None:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if stop_event is not None and stop_event.is_set():
                    seen.append(True)
                    return
                time.sleep(0.01)
            seen.append(stop_event.is_set() if stop_event is not None else False)

    class UnderTest(WorkerSupervisor):
        def __init__(self) -> None:
            self._settings = settings
            self._engine = object()
            self._repo = FakeRepo()
            self._runner = FakeRunner()
            self._stop = True
            self._active = None

    UnderTest()._process_claim(
        ClaimedRun(context_row=_row(), lease_token=uuid.uuid4()),
        repo=FakeRepo(),
        runner=FakeRunner(),
    )
    assert seen == [True]
