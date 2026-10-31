"""Demo dataset reset via PostgreSQL."""

from __future__ import annotations

import json
import logging

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlmodel import Session

from pokecoach_python.schemas.demo import DemoSeedResponse

logger = logging.getLogger(__name__)

_DEMO_SQLSTATE_BUSY = "PDC02"
_DEMO_SQLSTATE_REFERENCED = "PDC01"


def _map_demo_db_error(exc: DBAPIError) -> HTTPException | None:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == _DEMO_SQLSTATE_BUSY:
        return HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_BUSY",
                "message": "Une réinstallation de démonstration est déjà en cours.",
            },
        )
    if sqlstate == _DEMO_SQLSTATE_REFERENCED:
        return HTTPException(
            status_code=409,
            detail={
                "code": "DEMO_REFERENCED",
                "message": "Une équipe de démonstration est référencée par un autre matchup.",
            },
        )
    return None


def reset_demo_seed(session: Session, *, request_id: str) -> DemoSeedResponse:
    try:
        with session.begin():
            result = session.connection().execute(text("SELECT core.reset_demo_dataset()"))
            payload = result.scalar_one()
    except DBAPIError as exc:
        mapped = _map_demo_db_error(exc)
        if mapped:
            raise mapped from exc
        logger.error("demo reset failed request_id=%s db_error=%s", request_id, type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DEMO_RESET_FAILED",
                "message": "La réinstallation de démonstration a échoué.",
            },
        ) from exc
    except SQLAlchemyError as exc:
        logger.error("demo reset failed request_id=%s error=%s", request_id, type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"code": "DATABASE_UNAVAILABLE", "message": "Base de données indisponible."},
        ) from exc

    if isinstance(payload, str):
        data = json.loads(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        data = dict(payload)

    try:
        response = DemoSeedResponse.model_validate(data)
    except Exception as exc:
        logger.error("demo reset invalid payload request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DEMO_RESET_FAILED",
                "message": "Réponse de réinitialisation invalide.",
            },
        ) from exc
    return response
