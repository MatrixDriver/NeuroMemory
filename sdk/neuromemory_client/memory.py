"""Memory client - Time-based queries."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List, Optional

import httpx


class MemoryClient:
    """Client for time-based memory queries."""

    def __init__(self, http: httpx.Client):
        """Initialize with base client.

        Args:
            http: Base httpx Client with auth headers
        """
        self._http = http

    def get_by_time_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        memory_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict:
        """Query memories within a time range.

        Args:
            user_id: User identifier
            start_time: Start time (timezone-aware)
            end_time: End time (defaults to now)
            memory_type: Optional memory type filter
            limit: Maximum results
            offset: Pagination offset

        Returns:
            {"user_id": "...", "total": 10, "memories": [...]}
        """
        if end_time is None:
            end_time = datetime.now(timezone.utc)

        response = self._http.post(
            "/memories/time-range",
            json={
                "user_id": user_id,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "memory_type": memory_type,
                "limit": limit,
                "offset": offset,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_recent(
        self,
        user_id: str,
        days: int = 7,
        memory_types: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict]:
        """Query recent memories (last N days).

        Args:
            user_id: User identifier
            days: Number of days to look back
            memory_types: Optional list of memory types
            limit: Maximum results

        Returns:
            List of memory objects
        """
        response = self._http.post(
            "/memories/recent",
            json={
                "user_id": user_id,
                "days": days,
                "memory_types": memory_types,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json()

    def get_timeline(
        self,
        user_id: str,
        start_date: date,
        end_date: Optional[date] = None,
        granularity: str = "day",
        memory_type: Optional[str] = None,
    ) -> Dict:
        """Query memory timeline with aggregation.

        Args:
            user_id: User identifier
            start_date: Start date
            end_date: End date (defaults to today)
            granularity: "day", "week", or "month"
            memory_type: Optional memory type filter

        Returns:
            {
                "user_id": "...",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "granularity": "day",
                "total_memories": 100,
                "data": [{"date": "2024-01-01", "count": 5, ...}, ...]
            }
        """
        if end_date is None:
            end_date = date.today()

        response = self._http.post(
            "/memories/timeline",
            json={
                "user_id": user_id,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "granularity": granularity,
                "memory_type": memory_type,
            },
        )
        response.raise_for_status()
        return response.json()
