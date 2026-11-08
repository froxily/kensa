"""Application factory."""

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from kensa import __version__
from kensa.agents.handler import make_investigate_handler, on_job_outcome
from kensa.api.github import router as github_router
from kensa.api.health import router as health_router
from kensa.api.investigations import router as investigations_router
from kensa.api.middleware import BodySizeLimitMiddleware, RequireJsonMiddleware
from kensa.core.config import Settings, get_settings
from kensa.core.logging import configure_logging
from kensa.core.telemetry import RequestIdMiddleware, configure_tracing
from kensa.db.session import build_engine
from kensa.investigations.service import INVESTIGATE_JOB, RESUME_JOB
from kensa.jobs.worker import Worker


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    provider = configure_tracing(settings.telemetry_enabled, settings.telemetry_dir)
    engine = build_engine(settings)
    if provider is not None:
        SQLAlchemyInstrumentor().instrument(
            engine=engine, tracer_provider=provider, enable_commenter=False
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = threading.Event()
        thread: threading.Thread | None = None
        if settings.worker_enabled:
            handler = make_investigate_handler(settings)
            worker = Worker(
                engine,
                {INVESTIGATE_JOB: handler, RESUME_JOB: handler},
                lease_seconds=settings.worker_lease_seconds,
                heartbeat_seconds=settings.worker_heartbeat_seconds,
                poll_seconds=settings.worker_poll_seconds,
                on_outcome=on_job_outcome,
            )
            thread = threading.Thread(
                target=worker.run_forever, args=(stop,), name="kensa-worker", daemon=True
            )
            thread.start()
        yield
        stop.set()
        if thread is not None:
            thread.join(timeout=10)
        if provider is not None:
            provider.force_flush()
        engine.dispose()

    app = FastAPI(
        title="Kensa API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
        allow_credentials=False,
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(RequireJsonMiddleware)
    # Added last, so it runs first: refuse unknown Host headers before anything else.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestIdMiddleware)
    if provider is not None:
        # The live event stream is long-lived and health is polled; neither is worth a span.
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="api/health,api/investigations/[^/]+/stream",
        )
    app.include_router(health_router, prefix="/api")
    app.include_router(investigations_router, prefix="/api")
    app.include_router(github_router, prefix="/api")
    return app
