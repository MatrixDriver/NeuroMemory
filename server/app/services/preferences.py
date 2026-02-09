"""Preferences service - CRUD for user preferences."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.memory import Preference


async def set_preference(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
    key: str,
    value: str,
    metadata: dict | None = None,
) -> Preference:
    """Set a preference (upsert)."""
    stmt = (
        insert(Preference)
        .values(
            tenant_id=tenant_id,
            user_id=user_id,
            key=key,
            value=value,
            metadata_=metadata,
        )
        .on_conflict_do_update(
            index_elements=["tenant_id", "user_id", "key"],
            set_={"value": value, "metadata": metadata},
        )
        .returning(Preference)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_preference(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
    key: str,
) -> Preference | None:
    """Get a single preference by key."""
    result = await db.execute(
        select(Preference).where(
            Preference.tenant_id == tenant_id,
            Preference.user_id == user_id,
            Preference.key == key,
        )
    )
    return result.scalar_one_or_none()


async def list_preferences(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
) -> list[Preference]:
    """List all preferences for a user."""
    result = await db.execute(
        select(Preference).where(
            Preference.tenant_id == tenant_id,
            Preference.user_id == user_id,
        )
    )
    return list(result.scalars().all())


async def delete_preference(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
    key: str,
) -> bool:
    """Delete a preference. Returns True if deleted."""
    result = await db.execute(
        delete(Preference).where(
            Preference.tenant_id == tenant_id,
            Preference.user_id == user_id,
            Preference.key == key,
        )
    )
    return result.rowcount > 0
