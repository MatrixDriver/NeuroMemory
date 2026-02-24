"""Tests for reflect() watermark-based incremental processing and background mode."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from neuromemory import NeuroMemory
from neuromemory.providers.llm import LLMProvider

TEST_DATABASE_URL = "postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory"


class MockLLMProvider(LLMProvider):
    """Mock LLM that returns predictable reflection results."""

    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self.call_count += 1
        # Alternate: odd calls = insights, even calls = emotion
        if self.call_count % 2 == 1:
            return '{"insights": [{"content": "insight #%d", "category": "pattern", "source_ids": []}]}' % self.call_count
        else:
            return '{"latest_state": "test state", "dominant_emotions": {}, "emotion_triggers": {}}'


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


# ---------------------------------------------------------------------------
# Watermark tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_watermark_initial(mock_embedding, mock_llm):
    """First reflect() processes all memories and sets watermark."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "watermark_test_1"
        # Add memories
        await nm._add_memory(user, "Fact one", memory_type="fact")
        await nm._add_memory(user, "Fact two", memory_type="fact")
        await nm._add_memory(user, "Episode one", memory_type="episodic")

        result = await nm.reflect(user, batch_size=50)

        assert result["memories_analyzed"] == 3
        assert result["insights_generated"] >= 1

        # Verify watermark was set
        async with nm._db.session() as session:
            row = (await session.execute(
                text("SELECT last_reflected_at FROM emotion_profiles WHERE user_id = :uid"),
                {"uid": user},
            )).first()
            assert row is not None
            assert row.last_reflected_at is not None
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_reflect_watermark_incremental(mock_embedding, mock_llm):
    """Second reflect() only processes new memories after watermark."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "watermark_test_2"
        # Add initial memories and reflect
        await nm._add_memory(user, "Old fact", memory_type="fact")
        result1 = await nm.reflect(user, batch_size=50)
        assert result1["memories_analyzed"] == 1

        # Add new memories
        await nm._add_memory(user, "New fact", memory_type="fact")

        # Reset mock counter
        mock_llm.call_count = 0

        # Second reflect should only process the new memory
        result2 = await nm.reflect(user, batch_size=50)
        assert result2["memories_analyzed"] == 1
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_reflect_watermark_no_new_memories(mock_embedding, mock_llm):
    """Reflect() with no new memories returns early."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "watermark_test_3"
        await nm._add_memory(user, "Some fact", memory_type="fact")
        await nm.reflect(user, batch_size=50)

        # Reset counter
        mock_llm.call_count = 0

        # No new memories → should return immediately
        result = await nm.reflect(user, batch_size=50)
        assert result["memories_analyzed"] == 0
        assert result["insights_generated"] == 0
        assert mock_llm.call_count == 0
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_reflect_batch_pagination(mock_embedding, mock_llm):
    """Reflect() paginates through memories in batches."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "watermark_test_4"
        # Add 5 memories, batch_size=2 → 3 batches
        for i in range(5):
            await nm._add_memory(user, f"Memory number {i}", memory_type="fact")

        result = await nm.reflect(user, batch_size=2)
        assert result["memories_analyzed"] == 5
        # Should have called LLM for insights 3 times (batches) + emotion calls
        assert mock_llm.call_count >= 3
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_reflect_background(mock_embedding, mock_llm):
    """Reflect(background=True) returns immediately with None."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "watermark_test_5"
        await nm._add_memory(user, "Some fact", memory_type="fact")

        result = await nm.reflect(user, batch_size=50, background=True)
        assert result is None

        # Give background task time to complete
        await asyncio.sleep(1)

        # Verify watermark was set by background task
        async with nm._db.session() as session:
            row = (await session.execute(
                text("SELECT last_reflected_at FROM emotion_profiles WHERE user_id = :uid"),
                {"uid": user},
            )).first()
            assert row is not None
            assert row.last_reflected_at is not None
    finally:
        await nm.close()
