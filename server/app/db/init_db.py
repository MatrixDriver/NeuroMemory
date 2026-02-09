"""Database initialization - create tables and extensions."""

from sqlalchemy import text

from server.app.core.logging import get_logger
from server.app.db.session import engine
from server.app.models.base import Base

# Import all models so they register with Base.metadata
from server.app.models.memory import Embedding, Preference  # noqa: F401
from server.app.models.tenant import ApiKey, Tenant  # noqa: F401

logger = get_logger(__name__)


async def init_db() -> None:
    """Create pgvector extension and all tables."""
    async with engine.begin() as conn:
        # Enable pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        logger.info("pgvector extension enabled")

        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created")
