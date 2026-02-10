"""Memory time-based query schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field


class TimeRangeMemoryQuery(BaseModel):
    """Query memories within a time range.

    Note: All timestamps are stored and processed in UTC timezone.
    Client-provided timestamps are converted to UTC automatically.
    """

    user_id: str
    start_time: AwareDatetime = Field(description="Start time (ISO 8601 with timezone)")
    end_time: AwareDatetime | None = Field(None, description="End time (defaults to now)")
    memory_type: str | None = Field(None, description="Filter by memory type")
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class RecentMemoriesQuery(BaseModel):
    """Query recent memories (last N days)."""

    user_id: str
    days: int = Field(default=7, ge=1, le=90, description="Number of days to look back")
    memory_types: list[str] | None = Field(None, description="Filter by memory types")
    limit: int = Field(default=50, ge=1, le=500)


class MemoryTimelineQuery(BaseModel):
    """Query memory timeline with aggregation.

    Note: Maximum date range is limited to avoid performance issues.
    For day granularity, maximum 365 days.
    """

    user_id: str
    start_date: date = Field(description="Start date (YYYY-MM-DD)")
    end_date: date | None = Field(None, description="End date (defaults to today)")
    granularity: str = Field(default="day", pattern="^(day|week|month)$")
    memory_type: str | None = None


class DailyMemoryStat(BaseModel):
    """Daily memory statistics."""

    date: date
    count: int
    memory_types: dict[str, int] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class MemoryTimelineResponse(BaseModel):
    """Timeline aggregation response."""

    user_id: str
    start_date: date
    end_date: date
    granularity: str
    total_memories: int
    data: list[DailyMemoryStat]

    model_config = {"from_attributes": True}


class TimeRangeMemoryResponse(BaseModel):
    """Response for time range memory query."""

    user_id: str
    total: int
    limit: int
    offset: int
    time_range: dict[str, str]
    memories: list[Any]  # List of MemoryResponse objects

    model_config = {"from_attributes": True}
