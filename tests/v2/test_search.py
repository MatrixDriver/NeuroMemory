"""Tests for memory add and semantic search.

These tests require a running embedding service (SiliconFlow API key).
"""

import pytest


@pytest.mark.slow
@pytest.mark.asyncio
async def test_add_memory(client):
    """Add a memory and verify it returns correctly."""
    resp = await client.post(
        "/v1/memories",
        json={
            "user_id": "u1",
            "content": "I work at ABC Company as a Python developer",
            "memory_type": "general",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "I work at ABC Company as a Python developer"
    assert data["memory_type"] == "general"
    assert "id" in data


@pytest.mark.slow
@pytest.mark.asyncio
async def test_search_memories(client):
    """Add memories and search for them."""
    # Add some memories
    await client.post(
        "/v1/memories",
        json={"user_id": "search_user", "content": "I love Python programming"},
    )
    await client.post(
        "/v1/memories",
        json={"user_id": "search_user", "content": "My favorite food is sushi"},
    )

    # Search
    resp = await client.post(
        "/v1/search",
        json={"user_id": "search_user", "query": "programming language", "limit": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    # First result should be about Python (more relevant)
    assert "Python" in data["results"][0]["content"]


@pytest.mark.asyncio
async def test_user_memories_overview(client):
    """Get user memories overview."""
    resp = await client.get("/v1/users/u1/memories")
    assert resp.status_code == 200
    data = resp.json()
    assert "preference_count" in data
    assert "embedding_count" in data
