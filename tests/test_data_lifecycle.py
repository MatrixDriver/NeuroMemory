"""Tests for data lifecycle APIs: delete_user_data() and export_user_data()."""

from __future__ import annotations

import pytest
import pytest_asyncio

from neuromem import NeuroMemory
from neuromem.models.graph import EdgeType, NodeType

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


class TestDeleteUserData:
    """Test delete_user_data() atomic deletion."""

    @pytest.mark.asyncio
    async def test_delete_user_data_removes_all(self, nm_graph):
        """delete_user_data should remove all data for a user."""
        user_id = "delete_all_u1"

        # Add various data types
        await nm_graph._add_memory(user_id=user_id, content="test memory", memory_type="fact")
        await nm_graph.conversations.ingest(user_id=user_id, role="user", content="hello")
        await nm_graph.kv.set(user_id, "profile", "name", "Test User")
        await nm_graph.graph.create_node(NodeType.PERSON, "test_person", user_id=user_id)

        # Delete all
        result = await nm_graph.delete_user_data(user_id)

        assert "deleted" in result
        assert result["deleted"]["memories"] >= 1
        assert result["deleted"]["conversations"] >= 1
        assert result["deleted"]["key_values"] >= 1
        assert result["deleted"]["graph_nodes"] >= 1

        # Verify nothing remains
        recall_result = await nm_graph.recall(user_id=user_id, query="test")
        assert len(recall_result["merged"]) == 0

    @pytest.mark.asyncio
    async def test_delete_user_data_isolation(self, nm_graph):
        """Deleting one user's data should not affect another user."""
        u1, u2 = "delete_iso_u1", "delete_iso_u2"

        await nm_graph._add_memory(user_id=u1, content="u1 memory")
        await nm_graph._add_memory(user_id=u2, content="u2 memory")

        await nm_graph.delete_user_data(u1)

        # u2's data should be intact
        result = await nm_graph.recall(user_id=u2, query="u2 memory")
        assert len(result["merged"]) > 0

        # u1's data should be gone
        result = await nm_graph.recall(user_id=u1, query="u1 memory")
        assert len(result["merged"]) == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, nm):
        """Deleting a user with no data should succeed with zero counts."""
        result = await nm.delete_user_data("nonexistent_user_xyz")
        assert "deleted" in result
        for count in result["deleted"].values():
            assert count == 0


class TestExportUserData:
    """Test export_user_data() complete data export."""

    @pytest.mark.asyncio
    async def test_export_returns_all_types(self, nm):
        """export_user_data should include memories, conversations, kv, etc."""
        user_id = "export_u1"

        await nm._add_memory(user_id=user_id, content="export test memory", memory_type="fact")
        await nm.conversations.ingest(user_id=user_id, role="user", content="export hello")
        await nm.kv.set(user_id, "profile", "lang", "en")

        result = await nm.export_user_data(user_id)

        assert "memories" in result
        assert "conversations" in result
        assert "graph" in result
        assert "kv" in result
        assert "profile" in result
        assert "documents" in result

        assert len(result["memories"]) >= 1
        assert len(result["conversations"]) >= 1
        assert len(result["kv"]) >= 1

        # Check memory structure
        mem = result["memories"][0]
        assert "id" in mem
        assert "content" in mem
        assert "memory_type" in mem

    @pytest.mark.asyncio
    async def test_export_empty_user(self, nm):
        """Exporting a user with no data should return empty collections."""
        result = await nm.export_user_data("nonexistent_export_user")

        assert result["memories"] == []
        assert result["conversations"] == []
        assert result["graph"]["nodes"] == []
        assert result["graph"]["edges"] == []
        assert result["kv"] == []
        assert result["profile"]["facts"] == {}
        assert result["profile"]["traits"] == []
        assert result["profile"]["recent_mood"] is None
        assert result["documents"] == []

    @pytest.mark.asyncio
    async def test_export_includes_graph(self, nm_graph):
        """export_user_data should include graph nodes and edges."""
        import uuid
        suffix = uuid.uuid4().hex[:8]
        user_id = f"export_graph_{suffix}"

        await nm_graph.graph.create_node(NodeType.PERSON, f"alice_{suffix}", user_id=user_id)
        await nm_graph.graph.create_node(NodeType.ORGANIZATION, f"google_{suffix}", user_id=user_id)
        await nm_graph.graph.create_edge(
            NodeType.PERSON, f"alice_{suffix}", EdgeType.WORKS_AT,
            NodeType.ORGANIZATION, f"google_{suffix}",
            user_id=user_id,
        )

        result = await nm_graph.export_user_data(user_id)

        assert len(result["graph"]["nodes"]) >= 2
        assert len(result["graph"]["edges"]) >= 1
