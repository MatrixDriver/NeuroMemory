"""Memory time-based query API endpoints."""

import logging
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas import MemoryResponse
from server.app.api.v1.schemas_memory import (
    DailyMemoryStat,
    MemoryTimelineQuery,
    MemoryTimelineResponse,
    RecentMemoriesQuery,
    TimeRangeMemoryQuery,
    TimeRangeMemoryResponse,
)
from server.app.db.session import get_db
from server.app.services.auth import get_current_tenant
from server.app.services.memory import MemoryService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["memories"])


@router.post("/memories/time-range", response_model=TimeRangeMemoryResponse)
async def query_memories_by_time_range(
    query: TimeRangeMemoryQuery,
    tenant_id: UUID = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Query memories within a specific time range.

    Example:
        POST /v1/memories/time-range
        {
            "user_id": "alice",
            "start_time": "2024-01-01T00:00:00Z",
            "end_time": "2024-01-31T23:59:59Z",
            "memory_type": "episodic",
            "limit": 50
        }
    """
    try:
        service = MemoryService(db)
        total, memories = await service.get_memories_by_time_range(
            tenant_id=tenant_id,
            user_id=query.user_id,
            start_time=query.start_time,
            end_time=query.end_time,
            memory_type=query.memory_type,
            limit=query.limit,
            offset=query.offset,
        )

        logger.info(
            f"Time range query completed: {total} results",
            extra={
                "user_id": query.user_id,
                "time_range": f"{query.start_time.isoformat()} to {query.end_time.isoformat() if query.end_time else 'now'}",
            },
        )

        return TimeRangeMemoryResponse(
            user_id=query.user_id,
            total=total,
            limit=query.limit,
            offset=query.offset,
            time_range={
                "start": query.start_time.isoformat(),
                "end": (
                    query.end_time.isoformat()
                    if query.end_time
                    else datetime.now(timezone.utc).isoformat()
                ),
            },
            memories=[
                MemoryResponse(
                    id=str(m.id),
                    user_id=m.user_id,
                    content=m.content,
                    memory_type=m.memory_type,
                    metadata=m.metadata_,
                    created_at=m.created_at,
                )
                for m in memories
            ],
        )
    except ValueError as e:
        logger.error(
            f"Invalid time range: {str(e)}", extra={"user_id": query.user_id}
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to query memories by time range: {str(e)}",
            extra={"user_id": query.user_id},
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/memories/recent", response_model=List[MemoryResponse])
async def query_recent_memories(
    query: RecentMemoriesQuery,
    tenant_id: UUID = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Query recent memories (last N days).

    Example:
        POST /v1/memories/recent
        {
            "user_id": "alice",
            "days": 7,
            "memory_types": ["episodic", "fact"],
            "limit": 50
        }
    """
    try:
        service = MemoryService(db)
        memories = await service.get_recent_memories(
            tenant_id=tenant_id,
            user_id=query.user_id,
            days=query.days,
            memory_types=query.memory_types,
            limit=query.limit,
        )

        logger.info(
            f"Recent memories query completed: {len(memories)} results",
            extra={"user_id": query.user_id, "days": query.days},
        )

        return [
            MemoryResponse(
                id=str(m.id),
                user_id=m.user_id,
                content=m.content,
                memory_type=m.memory_type,
                metadata=m.metadata_,
                created_at=m.created_at,
            )
            for m in memories
        ]
    except Exception as e:
        logger.error(
            f"Failed to query recent memories: {str(e)}",
            extra={"user_id": query.user_id},
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.post("/memories/timeline", response_model=MemoryTimelineResponse)
async def query_memory_timeline(
    query: MemoryTimelineQuery,
    tenant_id: UUID = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Query memory timeline with daily/weekly/monthly aggregation.

    Example:
        POST /v1/memories/timeline
        {
            "user_id": "alice",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "granularity": "day"
        }
    """
    try:
        service = MemoryService(db)

        if query.granularity == "day":
            # Use daily stats for day granularity
            stats = await service.get_daily_memory_stats(
                tenant_id=tenant_id,
                user_id=query.user_id,
                start_date=query.start_date,
                end_date=query.end_date,
            )

            response = MemoryTimelineResponse(
                user_id=query.user_id,
                start_date=query.start_date,
                end_date=query.end_date or datetime.now(timezone.utc).date(),
                granularity=query.granularity,
                total_memories=sum(s["count"] for s in stats),
                data=[
                    DailyMemoryStat(
                        date=s["date"],
                        count=s["count"],
                        memory_types=s.get("memory_types", {}),
                    )
                    for s in stats
                ],
            )
        else:
            # Use timeline aggregation for week/month
            timeline = await service.get_memory_timeline(
                tenant_id=tenant_id,
                user_id=query.user_id,
                start_date=query.start_date,
                end_date=query.end_date,
                granularity=query.granularity,
                memory_type=query.memory_type,
            )

            response = MemoryTimelineResponse(
                user_id=timeline["user_id"],
                start_date=timeline["start_date"],
                end_date=timeline["end_date"],
                granularity=timeline["granularity"],
                total_memories=sum(d["count"] for d in timeline["data"]),
                data=[
                    DailyMemoryStat(
                        date=(
                            datetime.fromisoformat(d["period"]).date()
                            if d["period"]
                            else query.start_date
                        ),
                        count=d["count"],
                        memory_types={},
                    )
                    for d in timeline["data"]
                ],
            )

        logger.info(
            f"Timeline query completed: {response.total_memories} total memories",
            extra={
                "user_id": query.user_id,
                "granularity": query.granularity,
                "date_range": f"{query.start_date} to {query.end_date or 'today'}",
            },
        )

        return response

    except ValueError as e:
        logger.error(f"Invalid date range: {str(e)}", extra={"user_id": query.user_id})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(
            f"Failed to query memory timeline: {str(e)}",
            extra={"user_id": query.user_id},
        )
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")
