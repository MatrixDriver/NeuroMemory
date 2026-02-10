"""Memory service - Time-based queries and aggregations."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from server.app.models.memory import Embedding

logger = logging.getLogger(__name__)


class MemoryService:
    """Service for time-based memory queries and aggregations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_memories_by_time_range(
        self,
        tenant_id: UUID,
        user_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, List[Embedding]]:
        """Query memories within a time range.

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            start_time: Start of time range (inclusive)
            end_time: End of time range (exclusive), defaults to now
            memory_type: Optional memory type filter
            limit: Maximum results
            offset: Pagination offset

        Returns:
            (total_count, memories)
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        # Validate time range
        if start_time >= end_time:
            raise ValueError("start_time must be before end_time")

        logger.info(
            f"Querying memories for user {user_id} "
            f"from {start_time.isoformat()} to {end_time.isoformat()}"
        )

        # Build conditions
        conditions = [
            Embedding.tenant_id == tenant_id,
            Embedding.user_id == user_id,
            Embedding.created_at >= start_time,
            Embedding.created_at < end_time,
        ]

        if memory_type:
            conditions.append(Embedding.memory_type == memory_type)

        # Count total
        count_stmt = select(func.count()).select_from(Embedding).where(and_(*conditions))
        total = await self.db.scalar(count_stmt) or 0

        # Query memories
        stmt = (
            select(Embedding)
            .where(and_(*conditions))
            .order_by(desc(Embedding.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        memories = list(result.scalars().all())

        logger.debug(f"Found {len(memories)} memories (total: {total})")
        return total, memories

    async def get_recent_memories(
        self,
        tenant_id: UUID,
        user_id: str,
        days: int = 7,
        memory_types: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Embedding]:
        """Query memories from the last N days.

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            days: Number of days to look back
            memory_types: Optional list of memory types
            limit: Maximum results

        Returns:
            List of memories
        """
        start_time = datetime.now(timezone.utc) - timedelta(days=days)

        logger.info(f"Querying last {days} days of memories for user {user_id}")

        conditions = [
            Embedding.tenant_id == tenant_id,
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
        memories = list(result.scalars().all())

        logger.debug(f"Found {len(memories)} recent memories")
        return memories

    async def get_daily_memory_stats(
        self,
        tenant_id: UUID,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
    ) -> List[Dict]:
        """Get daily memory statistics.

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            start_date: Start date
            end_date: End date (defaults to today)

        Returns:
            List of daily stats: [{"date": "2024-01-01", "count": 10, ...}, ...]
        """
        if end_date is None:
            end_date = date.today()

        # Validate date range
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        # Convert dates to datetime for comparison
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        logger.info(f"Getting daily stats for user {user_id} from {start_date} to {end_date}")

        # Query daily counts and memory type distribution
        daily_stats = await self.db.execute(
            select(
                cast(Embedding.created_at, Date).label("date"),
                func.count(Embedding.id).label("count"),
                Embedding.memory_type,
            )
            .where(
                and_(
                    Embedding.tenant_id == tenant_id,
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

        # Aggregate by date
        result = {}
        for row in daily_stats:
            date_key = row.date.isoformat()
            if date_key not in result:
                result[date_key] = {"date": row.date, "count": 0, "memory_types": {}}
            result[date_key]["count"] += row.count
            result[date_key]["memory_types"][row.memory_type] = row.count

        logger.debug(f"Generated stats for {len(result)} days")
        return list(result.values())

    async def get_memory_timeline(
        self,
        tenant_id: UUID,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        granularity: str = "day",
        memory_type: Optional[str] = None,
    ) -> Dict:
        """Get memory timeline with aggregation.

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            start_date: Start date
            end_date: End date (defaults to today)
            granularity: "day", "week", or "month"
            memory_type: Optional memory type filter

        Returns:
            Timeline data with aggregated stats
        """
        if end_date is None:
            end_date = date.today()

        # Validate date range
        if start_date > end_date:
            raise ValueError("start_date must be before or equal to end_date")

        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

        logger.info(
            f"Getting {granularity} timeline for user {user_id} "
            f"from {start_date} to {end_date}"
        )

        # Select appropriate truncation function
        trunc_func = func.date_trunc(granularity, Embedding.created_at)

        conditions = [
            Embedding.tenant_id == tenant_id,
            Embedding.user_id == user_id,
            Embedding.created_at >= start_dt,
            Embedding.created_at <= end_dt,
        ]

        if memory_type:
            conditions.append(Embedding.memory_type == memory_type)

        # Query aggregated data
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

        logger.debug(f"Generated timeline with {len(data)} periods")

        return {
            "user_id": user_id,
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity,
            "total_periods": len(data),
            "data": data,
        }
