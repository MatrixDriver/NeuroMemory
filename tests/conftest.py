"""Test configuration and fixtures for NeuroMemory framework tests."""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from neuromem import NeuroMemory
from neuromem.models.base import Base
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider

# Default test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


class MockEmbeddingProvider(EmbeddingProvider):
    """Mock embedding provider for testing (no external API calls)."""

    def __init__(self, dims: int = 1024):
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        """Return a deterministic fake vector based on text hash."""
        h = hash(text) % (2**32)
        base = [float(((h * (i + 1)) % 1000) / 1000.0) for i in range(self._dims)]
        return base

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for testing (no external API calls)."""

    async def chat(self, messages: list[dict], temperature: float = 0.1, max_tokens: int = 2048) -> str:
        return '{"facts": [], "episodes": [], "relations": []}'


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create async engine for tests."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession]:
    """Create a database session for each test with table setup."""
    import neuromem.models as _models
    _models._embedding_dims = 1024

    import neuromem.models.memory  # noqa: F401
    import neuromem.models.kv  # noqa: F401
    import neuromem.models.conversation  # noqa: F401
    import neuromem.models.document  # noqa: F401
    import neuromem.models.graph  # noqa: F401

    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_embedding() -> MockEmbeddingProvider:
    """Create a mock embedding provider."""
    return MockEmbeddingProvider(dims=1024)


@pytest.fixture
def mock_llm() -> MockLLMProvider:
    """Create a mock LLM provider."""
    return MockLLMProvider()


@pytest_asyncio.fixture
async def nm(mock_embedding, mock_llm) -> AsyncGenerator[NeuroMemory]:
    """Create a NeuroMemory instance for testing."""
    instance = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
    )
    await instance.init()
    yield instance
    await instance.close()
