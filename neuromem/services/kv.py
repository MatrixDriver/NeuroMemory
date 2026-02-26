"""KV storage service - CRUD for key-value pairs with JSONB values."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.kv import KeyValue


class KVService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def set(
        self,
        namespace: str,
        scope_id: str,
        key: str,
        value: Any,
    ) -> KeyValue:
        """Set a KV pair (upsert)."""
        stmt = (
            insert(KeyValue)
            .values(
                namespace=namespace,
                scope_id=scope_id,
                key=key,
                value=value,
            )
            .on_conflict_do_update(
                index_elements=["namespace", "scope_id", "key"],
                set_={"value": value},
            )
            .returning(KeyValue)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get(
        self,
        namespace: str,
        scope_id: str,
        key: str,
    ) -> KeyValue | None:
        """Get a single KV pair."""
        result = await self.db.execute(
            select(KeyValue).where(
                KeyValue.namespace == namespace,
                KeyValue.scope_id == scope_id,
                KeyValue.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        namespace: str,
        scope_id: str,
        prefix: str | None = None,
        limit: int = 100,
    ) -> list[KeyValue]:
        """List KV pairs, optionally filtered by key prefix."""
        stmt = select(KeyValue).where(
            KeyValue.namespace == namespace,
            KeyValue.scope_id == scope_id,
        )
        if prefix:
            stmt = stmt.where(KeyValue.key.startswith(prefix))
        stmt = stmt.order_by(KeyValue.key).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete(
        self,
        namespace: str,
        scope_id: str,
        key: str,
    ) -> bool:
        """Delete a KV pair. Returns True if deleted."""
        result = await self.db.execute(
            delete(KeyValue).where(
                KeyValue.namespace == namespace,
                KeyValue.scope_id == scope_id,
                KeyValue.key == key,
            )
        )
        return result.rowcount > 0

    async def batch_set(
        self,
        namespace: str,
        scope_id: str,
        items: dict[str, Any],
    ) -> list[KeyValue]:
        """Batch upsert multiple KV pairs."""
        results = []
        for key, value in items.items():
            kv = await self.set(namespace, scope_id, key, value)
            results.append(kv)
        return results
