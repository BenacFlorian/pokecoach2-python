"""Analysis command routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.db.session import get_session
from pokecoach_python.schemas.analysis_commands import (
    AnalysisCapabilitiesResponse,
    AnalysisStartRequest,
    AnalysisStartResponse,
)
from pokecoach_python.services.analysis_commands import (
    analysis_capabilities,
    start_analysis,
)

router = APIRouter(tags=["analyses"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/analysis-capabilities", response_model=AnalysisCapabilitiesResponse)
def get_analysis_capabilities(settings: Settings = Depends(_settings)) -> AnalysisCapabilitiesResponse:
    return analysis_capabilities(settings)


@router.post(
    "/matchups/{matchup_id}/analyses",
    response_model=AnalysisStartResponse,
    status_code=202,
)
def post_start_analysis(
    matchup_id: uuid.UUID,
    body: AnalysisStartRequest,
    response: Response,
    idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(_settings),
) -> AnalysisStartResponse:
    try:
        result, http_status = start_analysis(
            session,
            settings,
            matchup_id=matchup_id,
            idempotency_key=idempotency_key,
            body=body,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Base indisponible."},
        ) from exc
    response.status_code = http_status
    return result
