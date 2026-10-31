"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial

from anyio import to_thread
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from pokecoach_python.api.analyses import router as analyses_router
from pokecoach_python.api.demo import router as demo_router
from pokecoach_python.api.health import router as health_router
from pokecoach_python.core.config import Settings, get_settings
from pokecoach_python.db.session import (
    create_db_engine,
    dispose_engine,
    verify_db_connection,
)

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_db_engine(settings)
    app.state.db_engine = engine
    try:
        await to_thread.run_sync(
            partial(
                verify_db_connection,
                engine,
                timeout_seconds=settings.db_connect_timeout_seconds,
            )
        )
    except Exception as exc:
        dispose_engine(engine)
        app.state.db_engine = None
        logger.error("startup database check failed: %s", type(exc).__name__)
        raise
    yield
    dispose_engine(engine)
    app.state.db_engine = None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(title="PokeCoach Python API", lifespan=lifespan)
    app.state.settings = resolved
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health_router)
    app.include_router(analyses_router, prefix="/api-python")
    app.include_router(demo_router, prefix="/api-python")
    return app
