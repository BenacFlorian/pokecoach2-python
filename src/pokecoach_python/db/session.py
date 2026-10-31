"""SQLAlchemy engine and per-request sessions."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from pokecoach_python.core.config import Settings, build_database_url

logger = logging.getLogger(__name__)

POOL_SIZE = 5
MAX_OVERFLOW = 0
POOL_TIMEOUT = 5


def create_db_engine(settings: Settings) -> Engine:
    return create_engine(
        build_database_url(settings),
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_pre_ping=True,
    )


def verify_db_connection(engine: Engine, *, timeout_seconds: int) -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1").execution_options(timeout=timeout_seconds))


def get_session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.db_engine
    session = Session(engine)
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine(engine: Engine | None) -> None:
    if engine is not None:
        engine.dispose()


def log_db_error(request_id: str, message: str, exc: BaseException) -> None:
    logger.error("%s database error: %s (%s)", request_id, message, type(exc).__name__)
