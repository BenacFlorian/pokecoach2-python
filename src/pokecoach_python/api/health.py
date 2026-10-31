"""Health check routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(request: Request, response: Response) -> dict[str, str]:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    engine = request.app.state.db_engine
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.error("health check failed request_id=%s error=%s", request_id, type(exc).__name__)
        response.status_code = 503
        return {"status": "unavailable", "database": "unavailable"}
    return {"status": "ok", "database": "ok"}
