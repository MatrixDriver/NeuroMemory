"""FastAPI application entry point."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from server.app.api.v1 import graph, health, preferences, search, tenants, users
from server.app.core.config import get_settings
from server.app.core.logging import (
    generate_trace_id,
    get_logger,
    setup_logging,
    tenant_id_var,
    trace_id_var,
    user_id_var,
)
from server.app.db.init_db import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info("Starting NeuroMemory v2...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down NeuroMemory v2")


app = FastAPI(
    title="NeuroMemory",
    description="Memory-as-a-Service for AI Agents",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    """Add trace_id to every request and log request/response."""
    trace_id = request.headers.get("X-Trace-ID", generate_trace_id())
    trace_id_var.set(trace_id)
    tenant_id_var.set("")
    user_id_var.set("")

    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled exception", extra={"action": "request_error"})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    duration_ms = round((time.monotonic() - start) * 1000, 1)
    response.headers["X-Trace-ID"] = trace_id

    logger.info(
        "%s %s %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Mount v1 routers
app.include_router(health.router, prefix="/v1")
app.include_router(tenants.router, prefix="/v1")
app.include_router(preferences.router, prefix="/v1")
app.include_router(search.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(graph.router, prefix="/v1")


@app.get("/")
async def root():
    """Alive probe."""
    return {"service": "NeuroMemory", "version": "2.0.0"}
