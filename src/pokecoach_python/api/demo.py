"""Demo seed command route."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from pokecoach_python.core.config import Settings
from pokecoach_python.db.session import get_session
from pokecoach_python.schemas.demo import DemoSeedRequest, DemoSeedResponse
from pokecoach_python.services.demo_seed import reset_demo_seed

router = APIRouter(prefix="/demo", tags=["demo"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/seed", response_model=DemoSeedResponse)
def post_demo_seed(
    request: Request,
    body: DemoSeedRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(_settings),
) -> DemoSeedResponse:
    del body
    if not settings.enable_demo_seed:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "DEMO_DISABLED",
                "message": "La commande de démonstration est désactivée.",
            },
        )
    request_id = getattr(request.state, "request_id", "unknown")
    try:
        return reset_demo_seed(session, request_id=request_id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Base de données indisponible."},
        ) from exc
