"""Concurrency and cascade behaviour when an owned team is deleted during analysis."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlmodel import Session

from pokecoach_python.core.analysis_errors import AnalysisTargetNotFound, RunExecutionStopped
from pokecoach_python.core.config import Settings, reset_settings_cache
from pokecoach_python.db.analysis_repository import AnalysisRepository
from pokecoach_python.db.session import create_db_engine
from pokecoach_python.schemas.analysis_commands import AnalysisStartRequest
from pokecoach_python.services.analysis_commands import start_analysis
from pokecoach_python.worker import WorkerSupervisor


def _require_test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    if not re.search(r"(_test|/pokecoach2_test\b)", url):
        pytest.fail("TEST_DATABASE_URL must target an explicit test database")
    return url


def _worker_settings() -> Settings:
    db_name = os.environ.get("POSTGRES_TEST_DB", "pokecoach2_test")
    return Settings(
        _env_file=None,
        POSTGRES_PASSWORD=SecretStr(os.environ.get("WORKER_DB_PASSWORD", "test-worker-password")),
        POSTGRES_HOST=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        POSTGRES_PORT=int(os.environ.get("POSTGRES_PORT", "5442")),
        POSTGRES_DB=db_name,
        POSTGRES_USER="pokecoach_worker",
        POKECOACH_ENGINE="stub",
        DEEPINFRA_API_KEY=SecretStr("fake-key"),
    )


def _admin_engine():
    db_name = os.environ.get("POSTGRES_TEST_DB", "pokecoach2_test")
    settings = Settings(
        _env_file=None,
        POSTGRES_PASSWORD=SecretStr(
            os.environ.get(
                "ADMIN_DB_PASSWORD",
                os.environ.get("POSTGRES_PASSWORD", "test"),
            )
        ),
        POSTGRES_HOST=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        POSTGRES_PORT=int(os.environ.get("POSTGRES_PORT", "5442")),
        POSTGRES_DB=db_name,
        POSTGRES_USER=os.environ.get("POSTGRES_ADMIN_USER", "pokecoach_admin"),
    )
    return create_db_engine(settings)


@pytest.fixture(scope="module")
def worker_engine():
    _require_test_database_url()
    eng = create_db_engine(_worker_settings())
    yield eng
    eng.dispose()


def _reset_demo(worker_engine) -> dict[str, Any]:
    with Session(worker_engine) as session:
        row = session.connection().execute(text("SELECT core.reset_demo_dataset()")).scalar_one()
        session.commit()
    if isinstance(row, str):
        return json.loads(row)
    if isinstance(row, dict):
        return row
    return {}


def test_insert_battle_after_run_deleted_raises_stop(worker_engine) -> None:
    reset_settings_cache()
    repo = AnalysisRepository(worker_engine, _worker_settings())
    payload = _reset_demo(worker_engine)
    run_id = uuid.UUID(str(payload.get("runId") or payload.get("run_id")))
    token = uuid.uuid4()
    with Session(worker_engine) as session:
        session.connection().execute(
            text(
                """
                UPDATE core.matchup_runs
                SET status = 'running',
                    lease_token = :token,
                    lease_expires_at = now() + interval '10 minutes'
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id, "token": token},
        )
        session.commit()
    with Session(worker_engine) as session:
        team_id = session.connection().execute(
            text(
                """
                SELECT our_team_id FROM core.matchups m
                JOIN core.matchup_runs r ON r.matchup_id = m.id
                WHERE r.id = :run_id
                """
            ),
            {"run_id": run_id},
        ).scalar_one()
    admin = _admin_engine()
    try:
        with Session(admin) as session:
            session.connection().execute(
                text("SELECT core.delete_owned_team(:team_id)"),
                {"team_id": team_id},
            )
            session.commit()
    finally:
        admin.dispose()
    from pokecoach_python.engine.contracts import SimulationRequest
    from pokecoach_python.engine.stub_adapter import StubEngineAdapter
    from tests.integration.sample_teams import SAMPLE_SNAPSHOT

    adapter = StubEngineAdapter()
    record = adapter.full_battle(
        SimulationRequest(
            our_snapshot=SAMPLE_SNAPSHOT[0],
            opponent_snapshot=SAMPLE_SNAPSHOT[1],
            regulation="M-B",
            checkpoint_id="stub-bc-v1",
            seed=1,
            timeout_seconds=30.0,
            opponent_lead=(0, 1),
            our_selection=[0, 1, 2, 3],
            our_lead_slots=[0, 1],
            opponent_back_pair=[2, 3],
        )
    )
    with pytest.raises(RunExecutionStopped):
        repo.insert_battle(
            run_id,
            token,
            phase="D",
            sample_key="refinement:0000",
            record=record,
            expected_opponent_lead=record.preview.opponent_lead_slots,
        )


def test_start_after_matchup_deleted_returns_not_found(worker_engine) -> None:
    reset_settings_cache()
    settings = _worker_settings()
    repo = AnalysisRepository(worker_engine, settings)
    payload = _reset_demo(worker_engine)
    matchup_id = uuid.UUID(str(payload.get("matchupId") or payload.get("matchup_id")))
    team_id = uuid.UUID("a1111111-1111-4111-8111-111111111101")
    admin = _admin_engine()
    try:
        with Session(admin) as session:
            session.connection().execute(
                text("SELECT core.delete_owned_team(:team_id)"),
                {"team_id": team_id},
            )
            session.commit()
    finally:
        admin.dispose()
    with pytest.raises(AnalysisTargetNotFound):
        repo.record_start_command(
            idempotency_key=uuid.uuid4(),
            request_hash="hash",
            matchup_id=matchup_id,
            target_phase="A",
            profile="smoke",
            seed=str(uuid.uuid4()),
        )


def test_start_analysis_http_404_when_matchup_disappears(worker_engine, monkeypatch) -> None:
    reset_settings_cache()
    settings = _worker_settings()
    payload = _reset_demo(worker_engine)
    matchup_id = uuid.UUID(str(payload.get("matchupId") or payload.get("matchup_id")))

    class Repo(AnalysisRepository):
        def record_start_command(self, **kwargs):
            raise AnalysisTargetNotFound("matchup", kwargs["matchup_id"])

    monkeypatch.setattr(
        "pokecoach_python.services.analysis_commands._repo",
        lambda session, _settings: Repo(worker_engine, settings),
    )
    with Session(worker_engine) as session:
        with pytest.raises(Exception) as exc:
            start_analysis(
                session,
                settings,
                matchup_id=matchup_id,
                idempotency_key=uuid.uuid4(),
                body=AnalysisStartRequest(target_phase="A", profile="smoke", locale="fr"),
            )
    from fastapi import HTTPException

    assert isinstance(exc.value, HTTPException)
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "MATCHUP_NOT_FOUND"


def test_delete_while_insert_battle_holds_lock(worker_engine) -> None:
    payload = _reset_demo(worker_engine)
    run_id = uuid.UUID(str(payload.get("runId") or payload.get("run_id")))
    token = uuid.uuid4()
    matchup_id = uuid.UUID(str(payload.get("matchupId") or payload.get("matchup_id")))
    team_id = uuid.UUID("a1111111-1111-4111-8111-111111111101")
    insert_started = threading.Event()
    insert_ready = threading.Event()
    delete_done = threading.Event()

    def worker_insert() -> None:
        eng = create_db_engine(_worker_settings())
        try:
            with Session(eng) as session:
                conn = session.connection()
                trans = conn.begin()
                locked = conn.execute(
                    text(
                        """
                        SELECT 1 FROM core.matchup_runs
                        WHERE id = :run_id
                          AND lease_token = :token
                          AND status = 'running'
                          AND lease_expires_at > now()
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id, "token": token},
                ).first()
                if locked is None:
                    trans.rollback()
                    return
                insert_started.set()
                insert_ready.wait(timeout=5)
                trans.rollback()
        finally:
            eng.dispose()

    with Session(worker_engine) as session:
        session.connection().execute(
            text(
                """
                UPDATE core.matchup_runs
                SET status = 'running',
                    lease_token = :token,
                    lease_expires_at = now() + interval '10 minutes'
                WHERE id = :run_id
                """
            ),
            {"run_id": run_id, "token": token},
        )
        session.commit()

    t = threading.Thread(target=worker_insert, daemon=True)
    t.start()
    assert insert_started.wait(timeout=5)
    admin = _admin_engine()
    try:
        with Session(admin) as session:
            session.connection().execute(
                text("SELECT core.delete_owned_team(:team_id)"),
                {"team_id": team_id},
            )
            session.commit()
    finally:
        admin.dispose()
    delete_done.set()
    insert_ready.set()
    t.join(timeout=10)
    with Session(worker_engine) as session:
        remaining = session.connection().execute(
            text("SELECT COUNT(*) FROM core.matchup_runs WHERE matchup_id = :mid"),
            {"mid": matchup_id},
        ).scalar_one()
        assert remaining == 0


def test_worker_end_to_end_after_team_delete(worker_engine, monkeypatch) -> None:
    """Claim run A, block in stub engine, delete team, resume, then process run B."""
    reset_settings_cache()
    settings = _worker_settings()
    first = _reset_demo(worker_engine)
    run_a = uuid.UUID(str(first.get("runId") or first.get("run_id")))
    team_id = uuid.UUID(str(first.get("teamIds", ["00000000-0000-0000-0000-000000000001"])[0]))
    with Session(worker_engine) as session:
        session.connection().execute(
            text(
                """
                UPDATE core.matchup_runs
                SET status = 'queued', lease_token = NULL, lease_expires_at = NULL
                WHERE id = :run_id
                """
            ),
            {"run_id": run_a},
        )
        session.commit()

    release = threading.Event()

    from pokecoach_python.engine.stub_adapter import StubEngineAdapter

    class BlockingStub(StubEngineAdapter):
        def preview(self, req):
            release.wait(timeout=2)
            return super().preview(req)

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "pokecoach_python.workflow.runner.build_engine_adapter",
        lambda *_args, **_kwargs: BlockingStub(),
    )
    monkeypatch.setattr(
        "pokecoach_python.workflow.runner.assert_run_engine_compatible",
        lambda *_args, **_kwargs: None,
    )

    class UnderTest(WorkerSupervisor):
        def __init__(self, eng) -> None:
            self._settings = settings
            self._engine = eng
            self._repo = AnalysisRepository(eng, settings)
            self._runner = __import__(
                "pokecoach_python.workflow.runner", fromlist=["WorkflowRunner"]
            ).WorkflowRunner(self._repo, settings)
            self._stop = False
            self._active = None

        def run_one(self) -> None:
            claim = self._repo.claim_next()
            if claim is None:
                return
            self._process_claim(claim, repo=self._repo, runner=self._runner)

    supervisor = UnderTest(worker_engine)
    started = threading.Event()

    def run_supervisor() -> None:
        started.set()
        supervisor.run_one()

    thread = threading.Thread(target=run_supervisor, daemon=True)
    thread.start()
    assert started.wait(timeout=5)
    time.sleep(0.2)
    admin = _admin_engine()
    try:
        with Session(admin) as session:
            session.connection().execute(
                text("SELECT core.delete_owned_team(:team_id)"),
                {"team_id": team_id},
            )
            session.commit()
    finally:
        admin.dispose()
    release.set()
    thread.join(timeout=30)
    assert not thread.is_alive()
    second = _reset_demo(worker_engine)
    run_b = uuid.UUID(str(second.get("runId") or second.get("run_id")))
    claim_b = AnalysisRepository(worker_engine, settings).claim_next()
    assert claim_b is not None
    assert claim_b.context_row.id == run_b
