"""Start, continue and cancel analysis commands."""

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

from pokecoach_python.core.analysis_errors import AnalysisTargetNotFound
from pokecoach_python.core.config import Settings
from pokecoach_python.db.analysis_repository import AnalysisRepository
from pokecoach_python.engine.capabilities import (
    engine_supported_phases,
    synthesis_available,
)
from pokecoach_python.engine.factory import build_engine_adapter
from pokecoach_python.schemas.analysis_commands import (
    AnalysisCancelResponse,
    AnalysisCapabilitiesResponse,
    AnalysisContinueRequest,
    AnalysisContinueResponse,
    AnalysisStartRequest,
    AnalysisStartResponse,
)
from pokecoach_python.workflow.registry import phase_order

logger = logging.getLogger(__name__)

_DEPLOYED_PROFILES = ("standard", "smoke")


@dataclass(frozen=True)
class _MatchupRow:
    id: uuid.UUID
    regulation: str | None
    is_deleted: bool


def _repo(session: Session, settings: Settings) -> AnalysisRepository:
    engine = session.get_bind()
    return AnalysisRepository(engine, settings)


def analysis_capabilities(settings: Settings) -> AnalysisCapabilitiesResponse:
    phases_config = settings.analysis_deployed_phase_list()
    regulations = settings.analysis_regulation_list()
    synth_available = synthesis_available(settings)
    if not phases_config or not regulations:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ANALYSIS_UNAVAILABLE",
                "message": "Configuration d’analyse indisponible.",
            },
        )
    if (
        settings.engine_mode.lower() == "vgc_bench"
        and not settings.vgc_engine_configured()
    ):
        if not synth_available:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ENGINE_UNAVAILABLE",
                    "message": "Checkpoint VGC non configuré (VGC_MODEL_PROFILE ou VGC_CHECKPOINT_PATH).",
                },
            )
        return AnalysisCapabilitiesResponse(
            phases=[],
            phase_order=[],
            profiles=list(_DEPLOYED_PROFILES),
            regulations=regulations,
            synthesis_available=True,
        )
    phases: list[str] = []
    engine = None
    try:
        engine = build_engine_adapter(settings)
        engine.hello()
        if settings.engine_mode.lower() == "stub":
            engine.preflight(
                {
                    "regulation": regulations[0],
                    "checkpoint_id": settings.analysis_checkpoint_id,
                },
                ({}, {}),
            )
        phases = engine_supported_phases(engine, settings)
    except Exception as exc:
        logger.error("engine capabilities failed: %s", type(exc).__name__)
        if not synth_available:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "ENGINE_UNAVAILABLE",
                    "message": "Moteur de simulation indisponible.",
                },
            ) from exc
        phases = []
    finally:
        if engine is not None:
            engine.close()
    if not phases and not synth_available:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "ENGINE_UNAVAILABLE",
                "message": "Aucune phase disponible avec le moteur configuré.",
            },
        )
    execution_order = [p for p in phase_order() if p != "synthesis"]
    return AnalysisCapabilitiesResponse(
        phases=phases,
        phase_order=[p for p in execution_order if p in phases],
        profiles=list(_DEPLOYED_PROFILES),
        regulations=regulations,
        synthesis_available=synth_available,
    )


def _request_fingerprint(matchup_id: uuid.UUID, body: AnalysisStartRequest) -> str:
    payload = {
        "matchupId": str(matchup_id),
        "targetPhase": body.target_phase,
        "profile": body.profile,
        "locale": body.locale,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _continue_fingerprint(run_id: uuid.UUID, body: AnalysisContinueRequest) -> str:
    payload = {"runId": str(run_id), "targetPhase": body.target_phase}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _cancel_fingerprint(run_id: uuid.UUID) -> str:
    return hashlib.sha256(json.dumps({"runId": str(run_id)}).encode()).hexdigest()


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


def _http_status_for_run(status: str) -> int:
    return 202 if status in ("queued", "running") else 200


def _not_found_http(exc: AnalysisTargetNotFound) -> HTTPException:
    if exc.resource == "matchup":
        return HTTPException(
            status_code=404,
            detail={"code": "MATCHUP_NOT_FOUND", "message": "Matchup introuvable."},
        )
    return HTTPException(
        status_code=404,
        detail={"code": "RUN_NOT_FOUND", "message": "Analyse introuvable."},
    )


def _response_from_repo(
    repo: AnalysisRepository, run_id: uuid.UUID
) -> AnalysisStartResponse:
    try:
        payload = repo.load_run_response(run_id)
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
    return AnalysisStartResponse.model_validate(payload)


def start_analysis(
    session: Session,
    settings: Settings,
    *,
    matchup_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    body: AnalysisStartRequest,
) -> tuple[AnalysisStartResponse, int]:
    repo = _repo(session, settings)
    fingerprint = _request_fingerprint(matchup_id, body)
    existing = repo.find_command(idempotency_key)
    if existing is not None:
        if existing.request_hash != fingerprint:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": "Clé d’idempotence déjà utilisée pour une autre demande.",
                },
            )
        try:
            response = _response_from_repo(repo, existing.run_id)
        except HTTPException:
            raise
        if response.matchup_id != str(matchup_id):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "IDEMPOTENCY_MISMATCH",
                    "message": "Cette clé correspond à un autre matchup.",
                },
            )
        return response, _http_status_for_run(response.status)

    matchup = _load_matchup(session, matchup_id)
    try:
        repo.resolve_matchup_regulation_for_analysis(
            matchup_id,
            allowed_regulations=settings.analysis_regulation_list(),
            default_regulation=settings.analysis_regulation_default(),
        )
    except ValueError as exc:
        message = str(exc)
        if "regulation not allowed" in message:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REGULATION_NOT_SUPPORTED",
                    "message": "Réglementation du matchup non supportée par le moteur.",
                },
            ) from exc
        raise HTTPException(
            status_code=404,
            detail={"code": "MATCHUP_NOT_FOUND", "message": "Matchup introuvable."},
        ) from exc
    matchup = _load_matchup(session, matchup_id)
    _validate_start_request(settings, matchup, body)

    if settings.engine_mode.lower() == "vgc_bench":
        try:
            our_snap, opp_snap, _reg = repo.load_matchup_snapshots(matchup_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=404,
                detail={"code": "MATCHUP_NOT_FOUND", "message": "Matchup introuvable."},
            ) from exc
        regulation = matchup.regulation or settings.analysis_regulation_default()
        engine = build_engine_adapter(settings)
        try:
            engine.preflight(
                {
                    "regulation": regulation,
                    "checkpoint_id": settings.analysis_checkpoint_id,
                },
                (our_snap, opp_snap),
            )
        except Exception as exc:
            logger.error("vgc preflight at start failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "ENGINE_PREFLIGHT_FAILED",
                    "message": "Équipes ou réglementation incompatibles avec le moteur.",
                },
            ) from exc
        finally:
            engine.close()

    if _active_run_exists(session, matchup_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_ALREADY_ACTIVE",
                "message": "Une analyse est déjà en cours pour ce matchup.",
            },
        )

    seed = str(uuid.uuid4())
    try:
        run_id = repo.record_start_command(
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            matchup_id=matchup_id,
            target_phase=body.target_phase,  # type: ignore[arg-type]
            profile=body.profile,
            seed=seed,
            locale=body.locale,
        )
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
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

    response = _response_from_repo(repo, run_id)
    return response, 202


def continue_analysis(
    session: Session,
    settings: Settings,
    *,
    run_id: uuid.UUID,
    idempotency_key: uuid.UUID,
    body: AnalysisContinueRequest,
) -> tuple[AnalysisContinueResponse, int]:
    repo = _repo(session, settings)
    fingerprint = _continue_fingerprint(run_id, body)
    existing = repo.find_command(idempotency_key)
    if existing is not None:
        if existing.request_hash != fingerprint or existing.run_id != run_id:
            raise HTTPException(
                status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"}
            )
        try:
            response = AnalysisContinueResponse.model_validate(
                repo.load_run_response(run_id)
            )
        except AnalysisTargetNotFound as exc:
            raise _not_found_http(exc) from exc
        return response, _http_status_for_run(response.status)

    if body.target_phase not in settings.analysis_deployed_phase_list():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "PHASE_NOT_DEPLOYED",
                "message": "Phase cible non disponible.",
            },
        )
    try:
        repo.record_continue_command(
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            run_id=run_id,
            target_phase=body.target_phase,  # type: ignore[arg-type]
        )
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CONTINUE_REJECTED", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "DATABASE_UNAVAILABLE"}
        ) from exc

    try:
        response = AnalysisContinueResponse.model_validate(repo.load_run_response(run_id))
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
    return response, 202


def cancel_analysis(
    session: Session,
    settings: Settings,
    *,
    run_id: uuid.UUID,
    idempotency_key: uuid.UUID,
) -> AnalysisCancelResponse:
    repo = _repo(session, settings)
    fingerprint = _cancel_fingerprint(run_id)
    existing = repo.find_command(idempotency_key)
    if existing is not None:
        if existing.request_hash != fingerprint or existing.run_id != run_id:
            raise HTTPException(
                status_code=409, detail={"code": "IDEMPOTENCY_CONFLICT"}
            )
        try:
            return AnalysisCancelResponse.model_validate(repo.load_run_response(run_id))
        except AnalysisTargetNotFound as exc:
            raise _not_found_http(exc) from exc
    try:
        repo.record_cancel_command(
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            run_id=run_id,
        )
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "CANCEL_REJECTED", "message": str(exc)},
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503, detail={"code": "DATABASE_UNAVAILABLE"}
        ) from exc
    try:
        return AnalysisCancelResponse.model_validate(repo.load_run_response(run_id))
    except AnalysisTargetNotFound as exc:
        raise _not_found_http(exc) from exc
