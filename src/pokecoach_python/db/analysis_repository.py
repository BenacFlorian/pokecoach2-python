"""PostgreSQL access for analysis commands and worker lifecycle."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.engine.contracts import BattleRecord
from pokecoach_python.engine.factory import build_engine_adapter
from pokecoach_python.llm.battle_sources import StoredDBattle
from pokecoach_python.schemas.analysis_result import Phase
from pokecoach_python.workflow.registry import phase_order
from pokecoach_python.workflow.battle_records import (
    BATTLE_FORMAT_VERSION,
    battle_payload_dict,
    battle_payload_sha256,
    battle_record_from_payload,
    validate_terminal_battle,
)

logger = logging.getLogger(__name__)

Operation = Literal["start", "continue", "cancel"]
LEASE_SECONDS = 60


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if (
            isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _initial_provenance(settings: Settings) -> dict[str, Any]:
    from pokecoach_python.engine.provenance import build_run_provenance

    hello: dict[str, Any] | None = None
    if settings.engine_mode.lower() == "vgc_bench":
        try:
            engine = build_engine_adapter(settings)
            try:
                hello = engine.hello()  # type: ignore[attr-defined]
            finally:
                engine.close()
        except Exception:
            hello = None
    return build_run_provenance(
        engine_mode=settings.engine_mode,
        product_phases=settings.analysis_deployed_phase_list(),
        hello=hello,
        checkpoint_id=settings.analysis_checkpoint_id,
    )


@dataclass(frozen=True)
class StoredCommand:
    run_id: uuid.UUID
    operation: Operation
    request_hash: str


@dataclass(frozen=True)
class RunRow:
    id: uuid.UUID
    matchup_id: uuid.UUID
    status: str
    target_phase: Phase
    partial_result: dict[str, Any]
    result_revision: int
    parameters: dict[str, Any]
    regulation: str
    our_snapshot: dict[str, Any]
    opponent_snapshot: dict[str, Any]
    process_status: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ClaimedRun:
    context_row: RunRow
    lease_token: uuid.UUID


class AnalysisRepository:
    def __init__(self, engine: Engine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    def find_command(self, idempotency_key: uuid.UUID) -> StoredCommand | None:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text(
                    """
                    SELECT run_id, operation, request_hash
                    FROM core.analysis_commands
                    WHERE idempotency_key = :key
                    """
                ),
                {"key": idempotency_key},
            ).first()
            if row is None:
                return None
            return StoredCommand(
                run_id=row[0],
                operation=row[1],
                request_hash=row[2],
            )

    def load_run_response(self, run_id: uuid.UUID) -> dict[str, Any]:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text(
                    """
                    SELECT m.id AS matchup_id,
                           r.id AS run_id,
                           r.source,
                           r.status,
                           r.process_status::text
                    FROM core.matchup_runs r
                    JOIN core.matchups m ON m.id = r.matchup_id
                    WHERE r.id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).one()
        process = str(row[4]).replace(" ", "_")
        return {
            "matchupId": str(row[0]),
            "runId": str(row[1]),
            "source": row[2],
            "status": row[3],
            "processStatus": process,
        }

    def apply_matchup_regulation(self, matchup_id: uuid.UUID, regulation: str) -> None:
        with Session(self._engine) as session:
            with session.begin():
                updated = session.connection().execute(
                    text(
                        """
                        UPDATE core.matchups
                        SET regulation = :regulation
                        WHERE id = :matchup_id
                          AND NOT is_deleted
                        """
                    ),
                    {"matchup_id": matchup_id, "regulation": regulation},
                )
                if updated.rowcount != 1:
                    raise ValueError("matchup not found or archived")

    def load_matchup_snapshots(
        self, matchup_id: uuid.UUID
    ) -> tuple[dict[str, Any], dict[str, Any], str | None]:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text(
                    """
                    SELECT core.team_row_to_snapshot_v1(our_t),
                           core.team_row_to_snapshot_v1(opp_t),
                           m.regulation
                    FROM core.matchups m
                    JOIN core.teams our_t ON our_t.id = m.our_team_id
                    JOIN core.teams opp_t ON opp_t.id = m.opponent_team_id
                    WHERE m.id = :matchup_id
                      AND NOT m.is_deleted
                    """
                ),
                {"matchup_id": matchup_id},
            ).first()
            if row is None:
                raise ValueError("matchup not found")
            return dict(row[0]), dict(row[1]), row[2]

    def record_start_command(
        self,
        *,
        idempotency_key: uuid.UUID,
        request_hash: str,
        matchup_id: uuid.UUID,
        target_phase: Phase,
        profile: str,
        seed: str,
        locale: str = "fr",
    ) -> uuid.UUID:
        empty = json.dumps(
            {
                "schemaVersion": 2,
                "source": "simulation",
                "completedPhases": [],
                "opponentLeads": None,
                "leadPick": None,
                "openings": None,
                "refinement": None,
                "gameplan": None,
                "winCondition": None,
            }
        )
        parameters = json.dumps(
            {
                "profile": profile,
                "seed": seed,
                "checkpoint_id": self._settings.analysis_checkpoint_id,
                "requestedTargetPhase": target_phase,
                "locale": locale if locale in ("fr", "en") else "fr",
            }
        )
        provenance = json.dumps(
            _initial_provenance(self._settings),
        )
        with Session(self._engine) as session:
            with session.begin():
                run_id = session.connection().execute(
                    text(
                        """
                        INSERT INTO core.matchup_runs (
                          matchup_id,
                          source,
                          status,
                          report_version,
                          target_phase,
                          partial_result,
                          parameters,
                          provenance
                        )
                        VALUES (
                          :matchup_id,
                          'simulation',
                          'queued',
                          2,
                          :target_phase,
                          CAST(:partial_result AS jsonb),
                          CAST(:parameters AS jsonb),
                          CAST(:provenance AS jsonb)
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "matchup_id": matchup_id,
                        "target_phase": target_phase,
                        "partial_result": empty,
                        "parameters": parameters,
                        "provenance": provenance,
                    },
                ).scalar_one()
                session.connection().execute(
                    text(
                        """
                        INSERT INTO core.analysis_commands (
                          idempotency_key, operation, request_hash, run_id
                        )
                        VALUES (:key, 'start', :hash, :run_id)
                        """
                    ),
                    {
                        "key": idempotency_key,
                        "hash": request_hash,
                        "run_id": run_id,
                    },
                )
        return run_id

    def record_continue_command(
        self,
        *,
        idempotency_key: uuid.UUID,
        request_hash: str,
        run_id: uuid.UUID,
        target_phase: Phase,
    ) -> None:
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT status, target_phase, partial_result
                        FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                status, old_target, partial = row[0], row[1], row[2]
                if status != "paused":
                    raise ValueError("run not paused")
                completed = partial.get("completedPhases") or []
                if not completed:
                    raise ValueError("nothing completed to continue from")
                order = list(phase_order())
                if target_phase not in order:
                    raise ValueError("invalid target")
                if order.index(target_phase) <= order.index(old_target):
                    raise ValueError("continue target must exceed paused target")
                active = session.connection().execute(
                    text(
                        """
                        SELECT 1 FROM core.matchup_runs r
                        JOIN core.matchup_runs cur ON cur.id = :run_id
                        WHERE r.matchup_id = cur.matchup_id
                          AND r.id <> cur.id
                          AND r.status IN ('queued', 'running')
                        LIMIT 1
                        """
                    ),
                    {"run_id": run_id},
                ).first()
                if active is not None:
                    raise ValueError("another active run exists")
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'queued',
                            target_phase = :target,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "target": target_phase},
                )
                session.connection().execute(
                    text(
                        """
                        INSERT INTO core.analysis_commands (
                          idempotency_key, operation, request_hash, run_id
                        )
                        VALUES (:key, 'continue', :hash, :run_id)
                        """
                    ),
                    {
                        "key": idempotency_key,
                        "hash": request_hash,
                        "run_id": run_id,
                    },
                )

    def record_cancel_command(
        self,
        *,
        idempotency_key: uuid.UUID,
        request_hash: str,
        run_id: uuid.UUID,
    ) -> None:
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT status FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                if row[0] in ("succeeded", "failed", "cancelled"):
                    raise ValueError("run already terminal")
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'cancelled',
                            finished_at = now(),
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            error_message = COALESCE(error_message, 'cancelled by user')
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id},
                )
                session.connection().execute(
                    text(
                        """
                        INSERT INTO core.analysis_commands (
                          idempotency_key, operation, request_hash, run_id
                        )
                        VALUES (:key, 'cancel', :hash, :run_id)
                        ON CONFLICT (idempotency_key) DO NOTHING
                        """
                    ),
                    {
                        "key": idempotency_key,
                        "hash": request_hash,
                        "run_id": run_id,
                    },
                )

    def claim_next(self) -> ClaimedRun | None:
        token = uuid.uuid4()
        expires = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        with Session(self._engine) as session:
            with session.begin():
                picked = session.connection().execute(
                    text(
                        """
                        SELECT id FROM core.matchup_runs
                        WHERE status = 'queued'
                        ORDER BY created_at, id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                        """
                    )
                ).first()
                if picked is None:
                    return None
                run_id = picked[0]
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'running',
                            process_status = 'PENDING STATS',
                            lease_token = :token,
                            lease_expires_at = :expires,
                            heartbeat_at = now(),
                            started_at = COALESCE(started_at, now())
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "token": token, "expires": expires},
                )
        row = self._fetch_run_row(run_id)
        if row is None:
            return None
        return ClaimedRun(context_row=row, lease_token=token)

    def heartbeat(self, run_id: uuid.UUID, token: uuid.UUID) -> bool:
        expires = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        with Session(self._engine) as session:
            with session.begin():
                updated = session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET heartbeat_at = now(),
                            lease_expires_at = :expires
                        WHERE id = :run_id
                          AND lease_token = :token
                          AND status = 'running'
                        """
                    ),
                    {"run_id": run_id, "token": token, "expires": expires},
                )
                return updated.rowcount == 1

    def update_progress(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        phase: Phase,
        completed: int,
        total: int,
    ) -> bool:
        payload = json.dumps({"phase": phase, "completed": completed, "total": total})
        with Session(self._engine) as session:
            with session.begin():
                updated = session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET progress = CAST(:progress AS jsonb)
                        WHERE id = :run_id
                          AND lease_token = :token
                          AND status = 'running'
                          AND lease_expires_at > now()
                        """
                    ),
                    {
                        "run_id": run_id,
                        "token": token,
                        "progress": payload,
                    },
                )
                return updated.rowcount == 1

    def insert_battle(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        phase: Literal["C", "D"],
        sample_key: str,
        record: BattleRecord,
        expected_opponent_lead: tuple[int, int],
    ) -> uuid.UUID:
        validate_terminal_battle(record, expected_opponent_lead=expected_opponent_lead)
        if self._settings.engine_mode.lower() == "vgc_bench":
            from pokecoach_python.workflow.battle_records import validate_real_engine_battle

            validate_real_engine_battle(
                record,
                expected_engine="vgc-bench",
            )
        payload = battle_payload_dict(record)
        digest = battle_payload_sha256(payload)
        payload_json = json.dumps(payload)
        with Session(self._engine) as session:
            with session.begin():
                lease_ok = session.connection().execute(
                    text(
                        """
                        SELECT 1 FROM core.matchup_runs
                        WHERE id = :run_id
                          AND lease_token = :token
                          AND status = 'running'
                          AND lease_expires_at > now()
                        """
                    ),
                    {"run_id": run_id, "token": token},
                ).first()
                if lease_ok is None:
                    raise RuntimeError("lost lease before battle insert")
                existing = session.connection().execute(
                    text(
                        """
                        SELECT sha256, payload
                        FROM core.matchup_run_battles
                        WHERE run_id = :run_id
                          AND phase = :phase
                          AND sample_key = :sample_key
                        """
                    ),
                    {"run_id": run_id, "phase": phase, "sample_key": sample_key},
                ).first()
                if existing is not None:
                    if existing[0] != digest:
                        raise RuntimeError("duplicate battle sample_key with different payload")
                    row_id = session.connection().execute(
                        text(
                            """
                            SELECT id FROM core.matchup_run_battles
                            WHERE run_id = :run_id AND phase = :phase AND sample_key = :sample_key
                            """
                        ),
                        {"run_id": run_id, "phase": phase, "sample_key": sample_key},
                    ).scalar_one()
                    return row_id
                battle_id = session.connection().execute(
                    text(
                        """
                        INSERT INTO core.matchup_run_battles (
                          run_id, phase, sample_key, format_version, outcome, payload, sha256
                        )
                        VALUES (
                          :run_id, :phase, :sample_key, :format_version, :outcome,
                          CAST(:payload AS jsonb), :sha256
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "phase": phase,
                        "sample_key": sample_key,
                        "format_version": BATTLE_FORMAT_VERSION,
                        "outcome": record.outcome,
                        "payload": payload_json,
                        "sha256": digest,
                    },
                ).scalar_one()
        return battle_id

    def list_battles(
        self,
        run_id: uuid.UUID,
        *,
        phase: Literal["C", "D"],
    ) -> list[BattleRecord]:
        with Session(self._engine) as session:
            rows = session.connection().execute(
                text(
                    """
                    SELECT payload
                    FROM core.matchup_run_battles
                    WHERE run_id = :run_id AND phase = :phase
                    ORDER BY sample_key
                    """
                ),
                {"run_id": run_id, "phase": phase},
            ).all()
        records: list[BattleRecord] = []
        for row in rows:
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            records.append(battle_record_from_payload(payload))
        return records

    def list_d_battles(self, run_id: uuid.UUID) -> list[StoredDBattle]:
        with Session(self._engine) as session:
            rows = session.connection().execute(
                text(
                    """
                    SELECT id, sample_key, sha256, payload
                    FROM core.matchup_run_battles
                    WHERE run_id = :run_id AND phase = 'D'
                    ORDER BY sample_key, id
                    """
                ),
                {"run_id": run_id},
            ).all()
        records: list[StoredDBattle] = []
        for row in rows:
            payload = row[3]
            if isinstance(payload, str):
                payload = json.loads(payload)
            records.append(
                StoredDBattle(
                    id=str(row[0]),
                    sample_key=str(row[1]),
                    sha256=str(row[2]),
                    record=battle_record_from_payload(payload),
                )
            )
        return records

    def pause_for_implementation(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
    ) -> None:
        """Pause when the next phase handler is not implemented yet.

        Progress is in ``partial_result.completedPhases``; ``target_phase`` is unchanged.
        """
        with Session(self._engine) as session:
            with session.begin():
                updated = session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'paused',
                            process_status = 'PENDING STATS',
                            progress = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL
                        WHERE id = :run_id
                          AND lease_token = :token
                          AND status = 'running'
                        """
                    ),
                    {
                        "run_id": run_id,
                        "token": token,
                    },
                )
                if updated.rowcount != 1:
                    raise RuntimeError("lost lease before implementation pause")

    def publish_phase(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        expected_revision: int,
        partial_result: dict[str, Any],
        target_phase: Phase,
        execution_slice: dict[str, Any],
        pause: bool,
    ) -> None:
        new_revision = expected_revision + 1
        partial_json = json.dumps(partial_result)
        phase_key = partial_result["completedPhases"][-1]
        process = (
            "PENDING GAME SIMULATIONS"
            if phase_key in ("C", "D")
            else "PENDING STATS"
        )
        if pause:
            status = "paused"
        else:
            status = "running"
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT result_revision, lease_token, status, execution_metadata
                        FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                revision, lease, run_status, execution_metadata = row[0], row[1], row[2], row[3]
                if run_status != "running" or lease != token:
                    raise RuntimeError("lease lost before publish")
                if revision != expected_revision:
                    raise RuntimeError("unexpected result revision")
                merged_meta = _deep_merge(
                    dict(execution_metadata or {}),
                    {"phases": {phase_key: execution_slice}},
                )
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET partial_result = CAST(:partial AS jsonb),
                            result_revision = :revision,
                            execution_metadata = CAST(:meta AS jsonb),
                            progress = NULL,
                            status = :status,
                            process_status = :process,
                            lease_token = CASE WHEN :pause THEN NULL ELSE lease_token END,
                            lease_expires_at = CASE WHEN :pause THEN NULL ELSE lease_expires_at END,
                            heartbeat_at = CASE WHEN :pause THEN NULL ELSE heartbeat_at END
                        WHERE id = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "partial": partial_json,
                        "revision": new_revision,
                        "meta": json.dumps(merged_meta),
                        "status": status,
                        "process": process,
                        "pause": pause,
                    },
                )

    def load_synthesis_sources(self, run_id: uuid.UUID | str) -> dict[str, Any] | None:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text(
                    """
                    SELECT execution_metadata
                    FROM core.matchup_runs
                    WHERE id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).first()
        if row is None:
            raise ValueError("run not found")
        metadata = dict(row[0] or {})
        synthesis = metadata.get("synthesis") or {}
        sources = synthesis.get("sources")
        return dict(sources) if isinstance(sources, dict) else None

    def create_synthesis_sources(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        expected_revision: int,
        sources_payload: dict[str, Any],
    ) -> None:
        self._write_synthesis_sources(
            run_id,
            token,
            expected_revision=expected_revision,
            sources_payload=sources_payload,
            require_existing=False,
        )

    def update_synthesis_sources(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        expected_revision: int,
        sources_payload: dict[str, Any],
    ) -> None:
        self._write_synthesis_sources(
            run_id,
            token,
            expected_revision=expected_revision,
            sources_payload=sources_payload,
            require_existing=True,
        )

    def delete_synthesis_sources(self, run_id: uuid.UUID, token: uuid.UUID) -> None:
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT status, lease_token, execution_metadata
                        FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                status, lease, execution_metadata = row[0], row[1], row[2]
                if status != "running" or lease != token:
                    raise RuntimeError("lease lost before deleting synthesis sources")
                metadata = dict(execution_metadata or {})
                synthesis = dict(metadata.get("synthesis") or {})
                if synthesis.get("invocation") is not None:
                    raise RuntimeError("cannot delete synthesis sources after invocation")
                synthesis.pop("sources", None)
                if synthesis:
                    metadata["synthesis"] = synthesis
                else:
                    metadata.pop("synthesis", None)
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET execution_metadata = CAST(:meta AS jsonb)
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "meta": json.dumps(metadata)},
                )

    def publish_complete(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        expected_revision: int,
        result: dict[str, Any],
        execution_metadata_patch: dict[str, Any],
    ) -> None:
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT result_revision, lease_token, status, execution_metadata, lease_expires_at
                        FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                revision, lease, status, execution_metadata, lease_expires_at = row
                if status != "running" or lease != token:
                    raise RuntimeError("lease lost before final publish")
                if lease_expires_at is None or lease_expires_at <= datetime.now(UTC):
                    raise RuntimeError("lease expired before final publish")
                if revision != expected_revision:
                    raise RuntimeError("unexpected result revision")
                merged_meta = _deep_merge(dict(execution_metadata or {}), execution_metadata_patch)
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET partial_result = CAST(:result AS jsonb),
                            report = CAST(:result AS jsonb),
                            result_revision = :revision,
                            execution_metadata = CAST(:meta AS jsonb),
                            status = 'succeeded',
                            process_status = 'SUCCESS',
                            finished_at = now(),
                            progress = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL
                        WHERE id = :run_id
                        """
                    ),
                    {
                        "run_id": run_id,
                        "result": json.dumps(result),
                        "revision": expected_revision + 1,
                        "meta": json.dumps(merged_meta),
                    },
                )

    def fail_run(self, run_id: uuid.UUID, token: uuid.UUID | None, reason: str) -> None:
        with Session(self._engine) as session:
            with session.begin():
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'failed',
                            finished_at = now(),
                            error_message = :reason,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            progress = NULL
                        WHERE id = :run_id
                          AND (:token IS NULL OR lease_token = :token)
                          AND status IN ('queued', 'running')
                        """
                    ),
                    {"run_id": run_id, "token": token, "reason": reason[:2000]},
                )

    def fail_expired_leases(self) -> int:
        with Session(self._engine) as session:
            with session.begin():
                result = session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET status = 'failed',
                            finished_at = now(),
                            error_message = 'worker lease expired',
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            progress = NULL
                        WHERE status = 'running'
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at < now()
                        """
                    )
                )
                return result.rowcount

    def is_cancelled(self, run_id: uuid.UUID) -> bool:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text("SELECT status FROM core.matchup_runs WHERE id = :id"),
                {"id": run_id},
            ).first()
            return row is not None and row[0] == "cancelled"

    def load_run_row(self, run_id: uuid.UUID) -> RunRow | None:
        return self._fetch_run_row(run_id)

    def _fetch_run_row(self, run_id: uuid.UUID) -> RunRow | None:
        with Session(self._engine) as session:
            row = session.connection().execute(
                text(
                    """
                    SELECT r.id,
                           r.matchup_id,
                           r.status,
                           r.target_phase,
                           r.partial_result,
                           r.result_revision,
                           r.parameters,
                           m.regulation,
                           r.our_team_snapshot,
                           r.opponent_team_snapshot,
                           r.process_status::text,
                           r.provenance
                    FROM core.matchup_runs r
                    JOIN core.matchups m ON m.id = r.matchup_id
                    WHERE r.id = :run_id
                    """
                ),
                {"run_id": run_id},
            ).first()
            if row is None:
                return None
            return RunRow(
                id=row[0],
                matchup_id=row[1],
                status=row[2],
                target_phase=row[3],
                partial_result=row[4],
                result_revision=row[5],
                parameters=row[6],
                regulation=row[7],
                our_snapshot=row[8],
                opponent_snapshot=row[9],
                process_status=row[10],
                provenance=dict(row[11] or {}),
            )

    def _write_synthesis_sources(
        self,
        run_id: uuid.UUID,
        token: uuid.UUID,
        *,
        expected_revision: int,
        sources_payload: dict[str, Any],
        require_existing: bool,
    ) -> None:
        with Session(self._engine) as session:
            with session.begin():
                row = session.connection().execute(
                    text(
                        """
                        SELECT status, lease_token, result_revision, execution_metadata
                        FROM core.matchup_runs
                        WHERE id = :run_id
                        FOR UPDATE
                        """
                    ),
                    {"run_id": run_id},
                ).one()
                status, lease, revision, execution_metadata = row
                if status != "running" or lease != token:
                    raise RuntimeError("lease lost before writing synthesis sources")
                if revision != expected_revision:
                    raise RuntimeError("unexpected result revision")
                metadata = dict(execution_metadata or {})
                synthesis = dict(metadata.get("synthesis") or {})
                if synthesis.get("invocation") is not None:
                    raise RuntimeError("cannot modify synthesis sources after invocation")
                existing = synthesis.get("sources")
                if require_existing and existing is None:
                    raise RuntimeError("synthesis sources do not exist")
                if not require_existing and existing == sources_payload:
                    return
                if not require_existing and existing is not None and existing != sources_payload:
                    raise RuntimeError("synthesis sources already exist; use update")
                synthesis["sources"] = sources_payload
                metadata["synthesis"] = synthesis
                session.connection().execute(
                    text(
                        """
                        UPDATE core.matchup_runs
                        SET execution_metadata = CAST(:meta AS jsonb)
                        WHERE id = :run_id
                        """
                    ),
                    {"run_id": run_id, "meta": json.dumps(metadata)},
                )
