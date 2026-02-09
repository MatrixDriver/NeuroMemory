"""Health check endpoint."""

from fastapi import APIRouter
from sqlalchemy import text

from server.app.api.v1.schemas import HealthResponse
from server.app.db.session import async_session_factory

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health():
    """Check service health including database connectivity."""
    db_status = "healthy"
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    status = "healthy" if db_status == "healthy" else "degraded"
    return HealthResponse(status=status, database=db_status)
