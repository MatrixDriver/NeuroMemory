"""Tests for time-based memory queries."""

import pytest
from datetime import datetime, timedelta, timezone, date

from server.app.services.memory import MemoryService
from server.app.models.memory import Embedding

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def memory_service(db_session):
    """Create MemoryService instance."""
    return MemoryService(db_session)


@pytest.fixture
async def test_user_id():
    """Test user ID."""
    return "test_user_123"


@pytest.fixture
async def sample_memories(db_session, test_tenant, test_user_id):
    """Create sample memories with different timestamps."""
    tenant, _ = test_tenant
    now = datetime.now(timezone.utc)
    memories = []

    # Create memories from the last 7 days
    for i in range(7):
        created_at = now - timedelta(days=i)
        memory = Embedding(
            tenant_id=tenant.id,
            user_id=test_user_id,
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
    """Test time range queries."""

    async def test_get_memories_by_time_range(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test querying memories within a time range."""
        tenant, _ = test_tenant
        # Use reference time from newest memory (max created_at, which is day 0)
        newest_memory = max(sample_memories, key=lambda m: m.created_at)
        ref_time = newest_memory.created_at

        # Query range: from 3 days before newest to 1 hour after newest
        start_time = ref_time - timedelta(days=3, hours=1)
        end_time = ref_time + timedelta(hours=1)

        total, memories = await memory_service.get_memories_by_time_range(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_time=start_time,
            end_time=end_time,
        )

        # Should get 4 memories (0, 1, 2, 3 days ago from ref_time)
        assert total == 4
        assert len(memories) == 4

        # Verify all are within range
        for memory in memories:
            assert memory.created_at >= start_time
            assert memory.created_at < end_time

    async def test_time_range_with_memory_type_filter(
        self, memory_service, db_session, test_tenant, test_user_id
    ):
        """Test time range with memory type filter."""
        tenant, _ = test_tenant
        now = datetime.now(timezone.utc)

        # Create mixed memory types
        for i, mem_type in enumerate(["episodic", "fact", "episodic"]):
            memory = Embedding(
                tenant_id=tenant.id,
                user_id=test_user_id,
                content=f"Memory {i}",
                embedding=[0.1] * 1024,
                memory_type=mem_type,
                created_at=now - timedelta(hours=i),
            )
            db_session.add(memory)
        await db_session.commit()

        # Query only episodic
        start_time = now - timedelta(days=1)
        total, memories = await memory_service.get_memories_by_time_range(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_time=start_time,
            end_time=now + timedelta(hours=1),
            memory_type="episodic",
        )

        assert total == 2
        assert all(m.memory_type == "episodic" for m in memories)

    async def test_empty_time_range(self, memory_service, test_tenant, test_user_id):
        """Test querying a time range with no results."""
        tenant, _ = test_tenant
        far_past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent_past = datetime(2020, 1, 2, tzinfo=timezone.utc)

        total, memories = await memory_service.get_memories_by_time_range(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_time=far_past,
            end_time=recent_past,
        )

        assert total == 0
        assert len(memories) == 0


class TestRecentMemories:
    """Test recent memories queries."""

    async def test_get_recent_memories(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test getting recent memories."""
        tenant, _ = test_tenant
        memories = await memory_service.get_recent_memories(
            tenant_id=tenant.id,
            user_id=test_user_id,
            days=4,  # Get last 4 days to include day 0, 1, 2, 3
        )

        # Should get 4 memories (0, 1, 2, 3 days ago)
        assert len(memories) >= 4

        # Verify sorted by created_at desc
        for i in range(len(memories) - 1):
            assert memories[i].created_at >= memories[i + 1].created_at

    async def test_recent_with_limit(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test recent memories with limit."""
        tenant, _ = test_tenant
        memories = await memory_service.get_recent_memories(
            tenant_id=tenant.id,
            user_id=test_user_id,
            days=7,
            limit=3,
        )

        assert len(memories) == 3


class TestMemoryTimeline:
    """Test timeline aggregation."""

    async def test_get_daily_memory_stats(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test daily memory statistics."""
        tenant, _ = test_tenant
        today = date.today()
        start_date = today - timedelta(days=6)

        stats = await memory_service.get_daily_memory_stats(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_date=start_date,
            end_date=today,
        )

        # Should have 7 days of stats
        assert len(stats) == 7

        # Each day should have count >= 1
        for day_stat in stats:
            assert day_stat["count"] >= 1
            assert "date" in day_stat
            assert "memory_types" in day_stat

    async def test_get_memory_timeline_day(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test timeline with day granularity."""
        tenant, _ = test_tenant
        today = date.today()
        start_date = today - timedelta(days=6)

        timeline = await memory_service.get_memory_timeline(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_date=start_date,
            end_date=today,
            granularity="day",
        )

        assert timeline["granularity"] == "day"
        assert timeline["user_id"] == test_user_id
        assert len(timeline["data"]) > 0

    async def test_get_memory_timeline_week(
        self, memory_service, sample_memories, test_tenant, test_user_id
    ):
        """Test timeline with week granularity."""
        tenant, _ = test_tenant
        today = date.today()
        start_date = today - timedelta(days=20)

        timeline = await memory_service.get_memory_timeline(
            tenant_id=tenant.id,
            user_id=test_user_id,
            start_date=start_date,
            end_date=today,
            granularity="week",
        )

        assert timeline["granularity"] == "week"
        # Should have 3-4 weeks depending on date alignment
        assert len(timeline["data"]) >= 2


class TestMemoryAPIEndpoints:
    """Test memory API endpoints."""

    async def test_time_range_endpoint(self, client, test_user_id, sample_memories):
        """Test POST /v1/memories/time-range."""
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/v1/memories/time-range",
            json={
                "user_id": test_user_id,
                "start_time": (now - timedelta(days=3)).isoformat(),
                "end_time": now.isoformat(),
                "limit": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "memories" in data
        assert data["total"] > 0

    async def test_recent_endpoint(self, client, test_user_id, sample_memories):
        """Test POST /v1/memories/recent."""
        response = await client.post(
            "/v1/memories/recent",
            json={
                "user_id": test_user_id,
                "days": 7,
                "limit": 50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_timeline_endpoint(self, client, test_user_id, sample_memories):
        """Test POST /v1/memories/timeline."""
        today = date.today()
        response = await client.post(
            "/v1/memories/timeline",
            json={
                "user_id": test_user_id,
                "start_date": (today - timedelta(days=6)).isoformat(),
                "end_date": today.isoformat(),
                "granularity": "day",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["granularity"] == "day"
        assert data["total_memories"] > 0
        assert len(data["data"]) > 0


class TestTimeFilteredSearch:
    """Test search with time filtering."""

    @pytest.mark.slow
    async def test_search_with_time_filter(self, client, test_user_id):
        """Test POST /v1/search with time parameters."""
        # Add a memory first
        await client.post(
            "/v1/memories",
            json={
                "user_id": test_user_id,
                "content": "I learned machine learning yesterday",
                "memory_type": "episodic",
            },
        )

        # Search with time filter
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/v1/search",
            json={
                "user_id": test_user_id,
                "query": "machine learning",
                "limit": 10,
                "created_after": (now - timedelta(days=1)).isoformat(),
                "created_before": now.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) > 0
