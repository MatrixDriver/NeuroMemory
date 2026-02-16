"""Memory service - Time-based queries and aggregations."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from neuromemory.models.memory import Embedding
from neuromemory.providers.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for time-based memory queries and aggregations."""

    def __init__(self, db: AsyncSession, embedding: Optional[EmbeddingProvider] = None):
        self.db = db
        self._embedding = embedding

    async def get_memories_by_time_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[Embedding]]:
        """Query memories within a time range."""
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        if start_time >= end_time:
            raise ValueError("start_time must be before end_time")

        conditions = [
            Embedding.user_id == user_id,
            Embedding.created_at >= start_time,
            Embedding.created_at < end_time,
        ]

        if memory_type:
            conditions.append(Embedding.memory_type == memory_type)

        count_stmt = select(func.count()).select_from(Embedding).where(and_(*conditions))
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(Embedding)
            .where(and_(*conditions))
            .order_by(desc(Embedding.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        memories = list(result.scalars().all())

        return total, memories

    async def get_recent_memories(
        self,
        user_id: str,
        days: int = 7,
        memory_types: Optional[list[str]] = None,
        limit: int = 50,
    ) -> list[Embedding]:
        """Query memories from the last N days."""
        start_time = datetime.now(timezone.utc) - timedelta(days=days)

        conditions = [
            Embedding.user_id == user_id,
            Embedding.created_at >= start_time,
        ]

        if memory_types:
            conditions.append(Embedding.memory_type.in_(memory_types))

        stmt = (
            select(Embedding)
            .where(and_(*conditions))
            .order_by(desc(Embedding.created_at))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_daily_memory_stats(
        self,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> list[dict]:
        """Get daily memory statistics."""
        if end_date is None:
            end_date = date.today()

        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        daily_stats = await self.db.execute(
            select(
                cast(Embedding.created_at, Date).label("date"),
                func.count(Embedding.id).label("count"),
                Embedding.memory_type,
            )
            .where(
                and_(
                    Embedding.user_id == user_id,
                    Embedding.created_at >= start_dt,
                    Embedding.created_at <= end_dt,
                )
            )
            .group_by(
                cast(Embedding.created_at, Date),
                Embedding.memory_type,
            )
            .order_by(cast(Embedding.created_at, Date))
        )

        result = {}
        for row in daily_stats:
            date_key = row.date.isoformat()
            if date_key not in result:
                result[date_key] = {"date": row.date, "count": 0, "memory_types": {}}
            result[date_key]["count"] += row.count
            result[date_key]["memory_types"][row.memory_type] = row.count

        return list(result.values())

    async def get_memory_timeline(
        self,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        granularity: str = "day",
        memory_type: Optional[str] = None,
    ) -> dict:
        """Get memory timeline with aggregation."""
        if end_date is None:
            end_date = date.today()

        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        trunc_func = func.date_trunc(granularity, Embedding.created_at)

        conditions = [
            Embedding.user_id == user_id,
            Embedding.created_at >= start_dt,
            Embedding.created_at <= end_dt,
        ]

        if memory_type:
            conditions.append(Embedding.memory_type == memory_type)

        timeline_data = await self.db.execute(
            select(
                trunc_func.label("period"),
                func.count(Embedding.id).label("count"),
            )
            .where(and_(*conditions))
            .group_by(trunc_func)
            .order_by(trunc_func)
        )

        data = [
            {
                "period": row.period.isoformat() if row.period else None,
                "count": row.count,
            }
            for row in timeline_data
        ]

        return {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity,
            "total_periods": len(data),
            "data": data,
        }

    async def list_all_memories(
        self,
        user_id: str,
        memory_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[Embedding]]:
        """List all memories with optional filtering and pagination.

        Returns:
            Tuple of (total_count, list_of_memories)
        """
        conditions = [Embedding.user_id == user_id]

        if memory_type:
            conditions.append(Embedding.memory_type == memory_type)

        # Get total count
        count_stmt = select(func.count()).select_from(Embedding).where(and_(*conditions))
        total = await self.db.scalar(count_stmt) or 0

        # Get paginated results
        stmt = (
            select(Embedding)
            .where(and_(*conditions))
            .order_by(desc(Embedding.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        memories = list(result.scalars().all())

        return total, memories

    async def get_memory_by_id(
        self,
        memory_id: str | uuid.UUID,
        user_id: str,
    ) -> Optional[Embedding]:
        """Get a single memory by ID with ownership check."""
        if isinstance(memory_id, str):
            memory_id = uuid.UUID(memory_id)

        stmt = select(Embedding).where(
            and_(Embedding.id == memory_id, Embedding.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_memory(
        self,
        memory_id: str | uuid.UUID,
        user_id: str,
        content: Optional[str] = None,
        memory_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[Embedding]:
        """Update a memory's content, type, or metadata.

        If content is changed, the embedding vector will be regenerated.

        Args:
            memory_id: UUID of the memory to update
            user_id: User ID (for access control)
            content: New content (triggers embedding regeneration)
            memory_type: New memory type
            metadata: New metadata (replaces existing)

        Returns:
            Updated Embedding object or None if not found
        """
        # Fetch existing memory
        memory = await self.get_memory_by_id(memory_id, user_id)
        if not memory:
            return None

        # Update fields
        content_changed = False
        if content is not None and content != memory.content:
            memory.content = content
            content_changed = True

        if memory_type is not None:
            memory.memory_type = memory_type

        if metadata is not None:
            memory.metadata_ = metadata

        # Regenerate embedding if content changed
        if content_changed and self._embedding:
            vector = await self._embedding.embed(content)
            memory.embedding = vector
        elif content_changed and not self._embedding:
            logger.warning(
                "Content changed but no embedding provider available. "
                "Embedding vector not updated."
            )

        await self.db.flush()
        return memory

    async def delete_memory(
        self,
        memory_id: str | uuid.UUID,
        user_id: str,
    ) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: UUID of the memory to delete
            user_id: User ID (for access control)

        Returns:
            True if deleted, False if not found
        """
        memory = await self.get_memory_by_id(memory_id, user_id)
        if not memory:
            return False

        await self.db.delete(memory)
        await self.db.flush()
        return True
