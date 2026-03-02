"""Tests for memory analytics APIs: stats(), cold_memories(), entity_profile()."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.services.graph_memory import GraphMemoryService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


@pytest_asyncio.fixture
async def nm_graph(mock_embedding, mock_llm):
    """NeuroMemory instance with graph enabled."""
    instance = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        graph_enabled=True,
    )
    await instance.init()
    yield instance
    await instance.close()


class TestStats:
    """Test stats() analytics API."""

    @pytest.mark.asyncio
    async def test_stats_returns_structure(self, nm):
        """stats() should return expected keys."""
        user_id = "stats_u1"
        await nm._add_memory(user_id=user_id, content="test fact", memory_type="fact")
        await nm._add_memory(user_id=user_id, content="test episode", memory_type="episodic")

        result = await nm.stats(user_id)

        assert "total" in result
        assert "by_type" in result
        assert "by_week" in result
        assert "active_entities" in result
        assert "profile_summary" in result

        assert result["total"] >= 2
        assert "fact" in result["by_type"]
        assert "episodic" in result["by_type"]

    @pytest.mark.asyncio
    async def test_stats_empty_user(self, nm):
        """stats() for a user with no data should return zeros."""
        result = await nm.stats("nonexistent_stats_user")

        assert result["total"] == 0
        assert result["by_type"] == {}
        assert result["by_week"] == []
        assert result["active_entities"] == 0
        assert result["profile_summary"]["trait_count"] == 0
        assert result["profile_summary"]["recent_mood"] is None

    @pytest.mark.asyncio
    async def test_stats_counts_entities(self, nm_graph):
        """stats() should count graph entities."""
        import uuid
        suffix = uuid.uuid4().hex[:8]
        user_id = f"stats_graph_{suffix}"
        from neuromem.models.graph import NodeType
        await nm_graph.graph.create_node(NodeType.PERSON, f"alice_{suffix}", user_id=user_id)
        await nm_graph.graph.create_node(NodeType.ORGANIZATION, f"google_{suffix}", user_id=user_id)

        result = await nm_graph.stats(user_id)
        assert result["active_entities"] >= 2


class TestColdMemories:
    """Test cold_memories() API."""

    @pytest.mark.asyncio
    async def test_cold_memories_finds_old(self, nm):
        """cold_memories() should find memories older than threshold."""
        user_id = "cold_u1"
        await nm._add_memory(user_id=user_id, content="old memory")

        # Backdate the memory
        async with nm._db.session() as session:
            await session.execute(
                text(
                    "UPDATE memories SET created_at = NOW() - INTERVAL '100 days', "
                    "last_accessed_at = NULL "
                    "WHERE user_id = :uid"
                ),
                {"uid": user_id},
            )
            await session.commit()

        result = await nm.cold_memories(user_id, threshold_days=90)
        assert len(result) >= 1
        assert result[0]["content"] == "old memory"

    @pytest.mark.asyncio
    async def test_cold_memories_excludes_recent(self, nm):
        """cold_memories() should not return recently accessed memories."""
        user_id = "cold_recent_u1"
        await nm._add_memory(user_id=user_id, content="fresh memory")

        result = await nm.cold_memories(user_id, threshold_days=90)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_cold_memories_empty_user(self, nm):
        """cold_memories() for a user with no data should return empty list."""
        result = await nm.cold_memories("nonexistent_cold_user")
        assert result == []


class TestEntityProfile:
    """Test entity_profile() API."""

    @pytest.mark.asyncio
    async def test_entity_profile_finds_facts(self, nm):
        """entity_profile() should find memories mentioning the entity."""
        user_id = "entity_u1"
        await nm._add_memory(user_id=user_id, content="Alice works at Google", memory_type="fact")
        await nm._add_memory(user_id=user_id, content="Bob likes pizza", memory_type="fact")

        result = await nm.entity_profile(user_id, "Alice")

        assert result["entity"] == "Alice"
        assert len(result["facts"]) >= 1
        assert any("Alice" in f["content"] for f in result["facts"])
        # Bob's memory should not be in facts
        assert not any("Bob" in f["content"] for f in result["facts"])

    @pytest.mark.asyncio
    async def test_entity_profile_includes_graph(self, nm_graph):
        """entity_profile() should include graph relations."""
        user_id = "entity_graph_u1"
        await nm_graph._add_memory(user_id=user_id, content="Alice works at Google")

        async with nm_graph._db.session() as session:
            svc = GraphMemoryService(session)
            await svc.store_triples(user_id, [{
                "subject": "user",
                "subject_type": "user",
                "relation": "works_at",
                "object": "Google",
                "object_type": "organization",
                "content": "在 Google 工作",
                "confidence": 0.98,
            }])

        result = await nm_graph.entity_profile(user_id, "Google")

        assert len(result["graph_relations"]) >= 1

    @pytest.mark.asyncio
    async def test_entity_profile_includes_conversations(self, nm):
        """entity_profile() should find conversations mentioning the entity."""
        user_id = "entity_conv_u1"
        await nm.conversations.ingest(
            user_id=user_id, role="user",
            content="I met Alice at the conference",
        )

        result = await nm.entity_profile(user_id, "Alice")
        assert len(result["conversations"]) >= 1

    @pytest.mark.asyncio
    async def test_entity_profile_timeline(self, nm):
        """entity_profile() should build a chronological timeline."""
        user_id = "entity_timeline_u1"
        await nm._add_memory(user_id=user_id, content="Alice joined in 2020")
        await nm.conversations.ingest(
            user_id=user_id, role="user", content="Alice got promoted",
        )

        result = await nm.entity_profile(user_id, "Alice")
        assert len(result["timeline"]) >= 1
        # Timeline should have type field
        for item in result["timeline"]:
            assert item["type"] in ("memory", "conversation")

    @pytest.mark.asyncio
    async def test_entity_profile_empty(self, nm):
        """entity_profile() for nonexistent entity should return empty collections."""
        result = await nm.entity_profile("nonexistent_user", "nonexistent_entity")

        assert result["entity"] == "nonexistent_entity"
        assert result["facts"] == []
        assert result["graph_relations"] == []
        assert result["conversations"] == []
        assert result["timeline"] == []
