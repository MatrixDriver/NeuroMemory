"""Test configuration and fixtures for v2 tests."""

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.app.core.config import get_settings
from server.app.core.security import generate_api_key, hash_api_key
from server.app.db.session import get_db
from server.app.main import app
from server.app.models.base import Base
from server.app.models.tenant import ApiKey, Tenant


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession]:
    """Create a new database session for each test with transaction rollback."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def test_tenant(db_session: AsyncSession) -> tuple[Tenant, str]:
    """Create a test tenant and return (tenant, raw_api_key)."""
    tenant = Tenant(
        name="Test Tenant",
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
    )
    db_session.add(tenant)
    await db_session.flush()

    raw_key = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:8],
        name="test-key",
        permissions="read,write,admin",
    )
    db_session.add(api_key)
    await db_session.commit()
    return tenant, raw_key


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, test_tenant) -> AsyncGenerator[AsyncClient]:
    """HTTP test client with auth."""
    tenant, raw_key = test_tenant

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"Authorization": f"Bearer {raw_key}"},
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauth_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """HTTP test client without auth."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
