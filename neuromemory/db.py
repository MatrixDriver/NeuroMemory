"""Database management - engine, session factory, initialization."""

from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class Database:
    """Async database manager with connection pooling."""

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
        from neuromemory.models.base import Base
        # Import all models to register them with Base.metadata
        import neuromemory.models.memory  # noqa: F401
        import neuromemory.models.kv  # noqa: F401
        import neuromemory.models.conversation  # noqa: F401
        import neuromemory.models.document  # noqa: F401
        import neuromemory.models.graph  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose engine and release all connections."""
        await self.engine.dispose()
