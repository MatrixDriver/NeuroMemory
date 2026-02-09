"""Search sub-client."""

from __future__ import annotations

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
    ) -> list[dict]:
        """Semantic search for memories."""
        payload: dict = {"user_id": user_id, "query": query, "limit": limit}
        if memory_type:
            payload["memory_type"] = memory_type
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
