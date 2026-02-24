"""Database management - engine, session factory, initialization."""

import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class Database:
    """Async database manager with connection pooling."""

    pg_search_available: bool = False

    def __init__(self, url: str, pool_size: int = 10, echo: bool = False):
        self.engine = create_async_engine(url, pool_size=pool_size, echo=echo)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,  # 禁用自动flush，由代码显式控制事务提交时机
        )

    @asynccontextmanager
    async def session(self):
        """Context manager that yields a session with auto-commit/rollback."""
        async with self.session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def init(self) -> None:
        """Create pgvector extension and all tables."""
        from pgvector.sqlalchemy import Vector

        import neuromemory.models as _models
        from neuromemory.models.base import Base
        # Import all models to register them with Base.metadata
        import neuromemory.models.memory  # noqa: F401
        import neuromemory.models.kv  # noqa: F401
        import neuromemory.models.conversation  # noqa: F401
        import neuromemory.models.document  # noqa: F401
        import neuromemory.models.graph  # noqa: F401

        # Fix vector column dimensions: __declare_last__ runs at import time
        # with the default 1024, but _embedding_dims may have been updated
        # by NeuroMemory.__init__() to the actual provider dimensions.
        dims = _models._embedding_dims
        for table in Base.metadata.tables.values():
            for col in table.columns:
                if isinstance(col.type, Vector) and col.type.dim != dims:
                    col.type = Vector(dims)

        async with self.engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

            # Add versioning columns to embeddings (idempotent)
            for col_sql in [
                "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ",
                "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ",
                "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS superseded_by UUID",
            ]:
                await conn.execute(text(col_sql))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_emb_user_valid "
                "ON embeddings (user_id, valid_from, valid_until)"
            ))

        # Try to enable pg_search (graceful degradation)
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
                self.pg_search_available = True
                logger.info("pg_search extension enabled")
        except Exception as e:
            self.pg_search_available = False
            logger.info("pg_search not available, using tsvector fallback: %s", e)

        # Create BM25 index if pg_search is available
        if self.pg_search_available:
            try:
                async with self.engine.begin() as conn:
                    await conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_embeddings_bm25
                        ON embeddings
                        USING bm25 (id, content)
                        WITH (key_field='id')
                    """))
                    logger.info("BM25 index created on embeddings")
            except Exception as e:
                logger.warning("Failed to create BM25 index: %s", e)


    async def close(self) -> None:
        """Dispose engine and release all connections."""
        await self.engine.dispose()
