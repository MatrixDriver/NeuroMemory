"""NeuroMemory Python SDK client."""

from __future__ import annotations

from datetime import date, datetime

import httpx

from neuromemory_client.conversations import ConversationsClient
from neuromemory_client.graph import GraphClient
from neuromemory_client.memory import MemoryClient
from neuromemory_client.preferences import PreferencesClient
from neuromemory_client.search import SearchClient


class NeuroMemoryClient:
    """Main client for NeuroMemory API.

    Usage:
        client = NeuroMemoryClient(api_key="nm_xxx")
        client.preferences.set(user_id="u1", key="lang", value="zh-CN")
        results = client.search(user_id="u1", query="project updates")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8765",
        timeout: float = 30.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = httpx.Client(
            base_url=f"{self._base_url}/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        self.preferences = PreferencesClient(self._http)
        self.conversations = ConversationsClient(self._http)
        self._search_client = SearchClient(self._http)
        self.memory = MemoryClient(self._http)
        self.graph = GraphClient(self._http)

    def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
    ) -> list[dict]:
        """Semantic search for memories with optional time filtering."""
        return self._search_client.search(
            user_id=user_id,
            query=query,
            limit=limit,
            memory_type=memory_type,
            created_after=created_after,
            created_before=created_before,
        )

    def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "general",
        metadata: dict | None = None,
    ) -> dict:
        """Add a memory with automatic embedding."""
        return self._search_client.add_memory(
            user_id=user_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata,
        )

    def get_user_memories(self, user_id: str) -> dict:
        """Get overview of all memories for a user."""
        resp = self._http.get(f"/users/{user_id}/memories")
        resp.raise_for_status()
        return resp.json()

    def get_recent_memories(
        self, user_id: str, days: int = 7, **kwargs
    ) -> list[dict]:
        """Convenience method: get recent memories."""
        return self.memory.get_recent(user_id, days, **kwargs)

    def get_memory_timeline(
        self, user_id: str, start_date: date, end_date: date | None = None, **kwargs
    ) -> dict:
        """Convenience method: get memory timeline."""
        return self.memory.get_timeline(user_id, start_date, end_date, **kwargs)

    def health(self) -> dict:
        """Check service health."""
        resp = self._http.get("/health")
        resp.raise_for_status()
        return resp.json()

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
