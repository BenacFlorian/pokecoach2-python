"""Start analysis commands (minimal socle before worker phases)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.schemas.analysis_commands import (
    AnalysisCapabilitiesResponse,
    AnalysisStartRequest,
    AnalysisStartResponse,
)

logger = logging.getLogger(__name__)

_DEPLOYED_PROFILES = ("standard", "smoke")
_IDEMPOTENCY: dict[uuid.UUID, tuple[str, AnalysisStartResponse]] = {}


@dataclass(frozen=True)
class _MatchupRow:
    id: uuid.UUID
    regulation: str | None
    is_deleted: bool


def analysis_capabilities(settings: Settings) -> AnalysisCapabilitiesResponse:
    phases = settings.analysis_deployed_phase_list()
    regulations = settings.analysis_regulation_list()
    if not phases or not regulations:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ANALYSIS_UNAVAILABLE",
                "message": "Configuration d’analyse indisponible.",
            },
        )
    return AnalysisCapabilitiesResponse(
        phases=phases,
        profiles=list(_DEPLOYED_PROFILES),
        regulations=regulations,
    )


def _request_fingerprint(matchup_id: uuid.UUID, body: AnalysisStartRequest) -> str:
    payload = {
        "matchupId": str(matchup_id),
        "targetPhase": body.target_phase,
        "profile": body.profile,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _load_matchup(session: Session, matchup_id: uuid.UUID) -> _MatchupRow:
    result = session.connection().execute(
        text(
            """
            SELECT id, regulation, is_deleted
            FROM core.matchups
            WHERE id = :id
            """
        ),
        {"id": matchup_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MATCHUP_NOT_FOUND", "message": "Matchup introuvable."},
        )
    return _MatchupRow(id=row[0], regulation=row[1], is_deleted=bool(row[2]))


def _validate_start_request(
    settings: Settings,
    matchup: _MatchupRow,
    body: AnalysisStartRequest,
) -> None:
    if matchup.is_deleted:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MATCHUP_ARCHIVED",
                "message": "Ce matchup est archivé.",
            },
        )
    if not matchup.regulation or not matchup.regulation.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "REGULATION_REQUIRED",
                "message": "Renseignez le format avant de lancer l’analyse.",
            },
        )
    if matchup.regulation not in settings.analysis_regulation_list():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "REGULATION_UNSUPPORTED",
                "message": "Format non pris en charge pour l’analyse.",
            },
        )
    if body.profile not in _DEPLOYED_PROFILES:
        raise HTTPException(
            status_code=422,
            detail={"code": "PROFILE_INVALID", "message": "Profil invalide."},
        )
    if body.target_phase not in settings.analysis_deployed_phase_list():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PHASE_NOT_DEPLOYED",
                "message": "Phase cible non disponible.",
            },
        )


def _active_run_exists(session: Session, matchup_id: uuid.UUID) -> bool:
    result = session.connection().execute(
        text(
            """
            SELECT 1
            FROM core.matchup_runs
            WHERE matchup_id = :matchup_id
              AND status IN ('queued', 'running')
            LIMIT 1
            """
        ),
        {"matchup_id": matchup_id},
    )
    return result.first() is not None


def _insert_queued_run(session: Session, matchup_id: uuid.UUID) -> AnalysisStartResponse:
    try:
        with session.begin():
            inserted = session.connection().execute(
                text(
                    """
                    INSERT INTO core.matchup_runs (matchup_id, source, status)
                    VALUES (:matchup_id, 'simulation', 'queued')
                    RETURNING id, status, process_status::text
                    """
                ),
                {"matchup_id": matchup_id},
            ).one()
    except DBAPIError as exc:
        logger.error("analysis start insert failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Impossible d’enregistrer le run.",
            },
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Base indisponible."},
        ) from exc

    run_id, status, process_status = inserted
    normalized_process = str(process_status).replace(" ", "_")
    return AnalysisStartResponse(
        matchup_id=str(matchup_id),
        run_id=str(run_id),
        source="simulation",
        status=status,
        process_status=normalized_process,
    )


def start_analysis(
    session: Session,
    settings: Settings,
    *,
    matchup_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    body: AnalysisStartRequest,
) -> tuple[AnalysisStartResponse, int]:
    fingerprint = _request_fingerprint(matchup_id, body)
    cached = _IDEMPOTENCY.get(idempotency_key)
    if cached is not None:
        prev_fp, response = cached
        if prev_fp != fingerprint:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "Clé d’idempotence déjà utilisée pour une autre demande.",
                },
            )
        if response.matchup_id != str(matchup_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_MISMATCH",
                    "message": "Cette clé correspond à un autre matchup.",
                },
            )
        http_status = 200 if response.status not in ("queued", "running") else 202
        return response, http_status

    matchup = _load_matchup(session, matchup_id)
    _validate_start_request(settings, matchup, body)

    if _active_run_exists(session, matchup_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_ALREADY_ACTIVE",
                "message": "Une analyse est déjà en cours pour ce matchup.",
            },
        )

    response = _insert_queued_run(session, matchup_id)
    _IDEMPOTENCY[idempotency_key] = (fingerprint, response)
    return response, 202
