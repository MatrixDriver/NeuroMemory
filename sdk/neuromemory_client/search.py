"""Search sub-client."""

from __future__ import annotations

from datetime import datetime

import httpx


class SearchClient:
    def __init__(self, http: httpx.Client):
        self._http = http

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[dict]:
        """Semantic search for memories with optional time filtering.

        Args:
            user_id: User identifier
            query: Search query
            limit: Maximum results
            memory_type: Optional memory type filter
            created_after: Optional start time filter
            created_before: Optional end time filter

        Returns:
            List of matching memories
        """
        payload: dict = {"user_id": user_id, "query": query, "limit": limit}
        if memory_type:
            payload["memory_type"] = memory_type
        if created_after:
            payload["created_after"] = created_after.isoformat()
        if created_before:
            payload["created_before"] = created_before.isoformat()

        resp = self._http.post("/search", json=payload)
        resp.raise_for_status()
        return resp.json()["results"]

    def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        metadata: dict | None = None,
    ) -> dict:
        """Add a memory with automatic embedding."""
        resp = self._http.post(
            "/memories",
            json={
                "user_id": user_id,
                "content": content,
                "memory_type": memory_type,
                "metadata": metadata,
            },
        )
        resp.raise_for_status()
        return resp.json()
