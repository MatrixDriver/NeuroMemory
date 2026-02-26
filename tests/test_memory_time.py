"""Tests for time-based memory queries."""

from datetime import date, datetime, timedelta, timezone

import pytest

from neuromem.models.memory import Embedding
from neuromem.services.memory import MemoryService


@pytest.fixture
async def memory_service(db_session):
    return MemoryService(db_session)


@pytest.fixture
async def sample_memories(db_session):
    """Create sample memories with different timestamps."""
    now = datetime.now(timezone.utc)
    memories = []

    for i in range(7):
        created_at = now - timedelta(days=i)
        memory = Embedding(
            user_id="test_user",
            content=f"Memory from {i} days ago",
            embedding=[0.1] * 1024,
            memory_type="episodic",
            created_at=created_at,
        )
        db_session.add(memory)
        memories.append(memory)

    await db_session.commit()
    return memories


class TestMemoryTimeRange:
    @pytest.mark.asyncio
    async def test_get_memories_by_time_range(
        self, memory_service, sample_memories
    ):
        newest = max(sample_memories, key=lambda m: m.created_at)
        ref_time = newest.created_at

        start_time = ref_time - timedelta(days=3, hours=1)
        end_time = ref_time + timedelta(hours=1)

        total, memories = await memory_service.get_memories_by_time_range(
            user_id="test_user",
            start_time=start_time,
            end_time=end_time,
        )

        assert total == 4
        assert len(memories) == 4

        for memory in memories:
            assert memory.created_at >= start_time
            assert memory.created_at < end_time

    @pytest.mark.asyncio
    async def test_time_range_with_memory_type_filter(
        self, memory_service, db_session
    ):
        now = datetime.now(timezone.utc)

        for i, mem_type in enumerate(["episodic", "fact", "episodic"]):
            memory = Embedding(
                user_id="test_user_filter",
                content=f"Memory {i}",
                embedding=[0.1] * 1024,
                memory_type=mem_type,
                created_at=now - timedelta(hours=i),
            )
            db_session.add(memory)
        await db_session.commit()

        start_time = now - timedelta(days=1)
        total, memories = await memory_service.get_memories_by_time_range(
            user_id="test_user_filter",
            start_time=start_time,
            end_time=now + timedelta(hours=1),
            memory_type="episodic",
        )

        assert total == 2
        assert all(m.memory_type == "episodic" for m in memories)

    @pytest.mark.asyncio
    async def test_empty_time_range(self, memory_service):
        far_past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent_past = datetime(2020, 1, 2, tzinfo=timezone.utc)

        total, memories = await memory_service.get_memories_by_time_range(
            user_id="test_user",
            start_time=far_past,
            end_time=recent_past,
        )

        assert total == 0
        assert len(memories) == 0


class TestRecentMemories:
    @pytest.mark.asyncio
    async def test_get_recent_memories(
        self, memory_service, sample_memories
    ):
        memories = await memory_service.get_recent_memories(
            user_id="test_user",
            days=4,
        )
        assert len(memories) >= 4

        for i in range(len(memories) - 1):
            assert memories[i].created_at >= memories[i + 1].created_at

    @pytest.mark.asyncio
    async def test_recent_with_limit(
        self, memory_service, sample_memories
    ):
        memories = await memory_service.get_recent_memories(
            user_id="test_user",
            days=7,
            limit=3,
        )
        assert len(memories) == 3


class TestMemoryTimeline:
    @pytest.mark.asyncio
    async def test_get_daily_memory_stats(
        self, memory_service, sample_memories
    ):
        today = date.today()
        start_date = today - timedelta(days=6)

        stats = await memory_service.get_daily_memory_stats(
            user_id="test_user",
            start_date=start_date,
            end_date=today,
        )

        assert len(stats) == 7
        for day_stat in stats:
            assert day_stat["count"] >= 1
            assert "date" in day_stat
            assert "memory_types" in day_stat

    @pytest.mark.asyncio
    async def test_get_memory_timeline_day(
        self, memory_service, sample_memories
    ):
        today = date.today()
        start_date = today - timedelta(days=6)

        timeline = await memory_service.get_memory_timeline(
            user_id="test_user",
            start_date=start_date,
            end_date=today,
            granularity="day",
        )

        assert timeline["granularity"] == "day"
        assert timeline["user_id"] == "test_user"
        assert len(timeline["data"]) > 0
