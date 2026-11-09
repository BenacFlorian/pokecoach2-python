from __future__ import annotations

import uuid
from contextlib import contextmanager
from threading import Event
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from pokecoach_python.core.analysis_errors import RunExecutionStopped
from pokecoach_python.core.config import Settings
from pokecoach_python.db.analysis_repository import AnalysisRepository, ClaimedRun, RunRow
from pokecoach_python.llm.client import StrategyClient
from pokecoach_python.workflow.runner import WorkflowRunner
from tests.unit.phase_e_fixtures import make_snapshots


def _settings() -> Settings:
    return Settings(_env_file=None, POSTGRES_PASSWORD="secret", DEEPINFRA_API_KEY="fake-key")


class _Result:
    def __init__(self, row) -> None:
        self._row = row

    def first(self):
        return self._row


def _patch_session(monkeypatch, results: list) -> None:
  connection = MagicMock()
  connection.execute.side_effect = lambda *_a, **_k: _Result(results.pop(0))

  session = MagicMock()
  session.connection.return_value = connection

  @contextmanager
  def fake_session(_engine):
    yield session

  monkeypatch.setattr("pokecoach_python.db.analysis_repository.Session", fake_session)


def test_missing_run_stops_execution(monkeypatch) -> None:
    repo = AnalysisRepository(MagicMock(), _settings())
    _patch_session(monkeypatch, [None, None])
    run_id = uuid.uuid4()
    with pytest.raises(RunExecutionStopped) as exc:
        repo.ensure_run_active(run_id, uuid.uuid4())
    assert exc.value.reason == "missing_run"
    assert exc.value.run_id == run_id


def test_wrong_or_expired_lease_stops_execution(monkeypatch) -> None:
    repo = AnalysisRepository(MagicMock(), _settings())
    _patch_session(monkeypatch, [None, ("running",)])
    with pytest.raises(RunExecutionStopped) as exc:
        repo.ensure_run_active(uuid.uuid4(), uuid.uuid4())
    assert exc.value.reason == "lease_lost"


def test_cancelled_run_stops_execution(monkeypatch) -> None:
    repo = AnalysisRepository(MagicMock(), _settings())
    _patch_session(monkeypatch, [None, ("cancelled",)])
    with pytest.raises(RunExecutionStopped) as exc:
        repo.ensure_run_active(uuid.uuid4(), uuid.uuid4())
    assert exc.value.reason == "cancelled"


def test_running_owned_lease_is_allowed(monkeypatch) -> None:
    repo = AnalysisRepository(MagicMock(), _settings())
    _patch_session(monkeypatch, [(1,)])
    repo.ensure_run_active(uuid.uuid4(), uuid.uuid4())


def test_ensure_run_active_propagates_sql_errors(monkeypatch) -> None:
    connection = MagicMock()
    connection.execute.side_effect = OperationalError("stmt", {}, Exception("down"))
    session = MagicMock()
    session.connection.return_value = connection

    @contextmanager
    def fake_session(_engine):
        yield session

    monkeypatch.setattr("pokecoach_python.db.analysis_repository.Session", fake_session)
    repo = AnalysisRepository(MagicMock(), _settings())
    with pytest.raises(OperationalError):
        repo.ensure_run_active(uuid.uuid4(), uuid.uuid4())


def test_runner_stops_before_engine_when_run_missing(monkeypatch) -> None:
    builds = []

    class FakeRepo:
        def ensure_run_active(self, *_args, **_kwargs):
            raise RunExecutionStopped("missing_run", run_id=uuid.uuid4())

        def fail_run(self, *_args, **_kwargs):
            raise AssertionError("should not fail_run on cooperative stop")

    monkeypatch.setattr(
        "pokecoach_python.workflow.runner.build_engine_adapter",
        lambda *_: builds.append(1),
    )
    row = RunRow(
        id=uuid.uuid4(),
        matchup_id=uuid.uuid4(),
        status="running",
        target_phase="A",
        partial_result={"completedPhases": [], "schemaVersion": 2, "source": "simulation"},
        result_revision=0,
        parameters={"profile": "smoke", "seed": "1", "checkpoint_id": "stub-bc-v1"},
        regulation="M-B",
        our_snapshot=make_snapshots()[0],
        opponent_snapshot=make_snapshots()[1],
        process_status="PENDING_STATS",
        provenance={},
    )
    runner = WorkflowRunner(FakeRepo(), _settings())
    runner.run_claimed(ClaimedRun(context_row=row, lease_token=uuid.uuid4()))
    assert builds == []


def test_runner_phase_a_propagates_execution_stop(monkeypatch) -> None:
    previews = {"n": 0}

    class CountingEngine:
        def preview(self, _req):
            previews["n"] += 1
            raise RunExecutionStopped("missing_run", run_id=uuid.uuid4())

        def close(self) -> None:
            return None

    class FakeRepo:
        def ensure_run_active(self, *_args, **_kwargs):
            return None

        def update_progress(self, *_args, **_kwargs):
            return True

        def fail_run(self, *_args, **_kwargs):
            raise AssertionError("unexpected fail_run")

    runner_pkg = "pokecoach_python.workflow.runner"
    monkeypatch.setattr(f"{runner_pkg}.assert_run_engine_compatible", lambda *_: None)
    monkeypatch.setattr(f"{runner_pkg}.provenance_for_worker_compat", lambda *_: {})
    monkeypatch.setattr(f"{runner_pkg}.build_engine_adapter", lambda *_: CountingEngine())
    row = RunRow(
        id=uuid.uuid4(),
        matchup_id=uuid.uuid4(),
        status="running",
        target_phase="A",
        partial_result={"completedPhases": [], "schemaVersion": 2, "source": "simulation"},
        result_revision=0,
        parameters={"profile": "smoke", "seed": "1", "checkpoint_id": "stub-bc-v1"},
        regulation="M-B",
        our_snapshot=make_snapshots()[0],
        opponent_snapshot=make_snapshots()[1],
        process_status="PENDING_STATS",
        provenance={},
    )
    WorkflowRunner(FakeRepo(), _settings()).run_claimed(
        ClaimedRun(context_row=row, lease_token=uuid.uuid4())
    )
    assert previews["n"] == 1


def test_strategy_client_skips_retry_when_stopped() -> None:
    attempts = {"n": 0}
    guard = {"n": 0}

    class FlakyLlm:
        def invoke(self, _messages):
            attempts["n"] += 1
            raise TimeoutError("transient")

    def chat_factory(**_kwargs):
        class Wrapper:
            def with_structured_output(self, *_args, **_kwargs):
                return FlakyLlm()

        return Wrapper()

    def ensure_active() -> None:
        guard["n"] += 1
        if guard["n"] > 1:
            raise RunExecutionStopped("missing_run", run_id=uuid.uuid4())

    client = StrategyClient(
        _settings(),
        chat_factory=chat_factory,
        ensure_active=ensure_active,
    )
    with pytest.raises(RunExecutionStopped):
        client.generate(MagicMock(), [])
    assert attempts["n"] == 1


def test_supervisor_stop_event_stops_runner() -> None:
    class FakeRepo:
        def ensure_run_active(self, *_args, **_kwargs):
            return None

        def update_progress(self, *_args, **_kwargs):
            return True

        def fail_run(self, *_args, **_kwargs):
            raise AssertionError("unexpected fail_run")

    stop = Event()
    stop.set()
    row = RunRow(
        id=uuid.uuid4(),
        matchup_id=uuid.uuid4(),
        status="running",
        target_phase="A",
        partial_result={"completedPhases": [], "schemaVersion": 2, "source": "simulation"},
        result_revision=0,
        parameters={"profile": "smoke", "seed": "1", "checkpoint_id": "stub-bc-v1"},
        regulation="M-B",
        our_snapshot=make_snapshots()[0],
        opponent_snapshot=make_snapshots()[1],
        process_status="PENDING STATS",
        provenance={},
    )
    WorkflowRunner(FakeRepo(), _settings()).run_claimed(
        ClaimedRun(context_row=row, lease_token=uuid.uuid4()),
        stop_event=stop,
    )
