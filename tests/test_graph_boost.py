"""Tests for graph-boosted recall ranking.

Verifies that graph triples boost vector result scores and participate
in unified merged ranking.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from neuromemory import NeuroMemory
from neuromemory.models.graph import NodeType
from neuromemory.services.graph_memory import GraphMemoryService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory"


@pytest_asyncio.fixture
async def nm_graph(mock_embedding, mock_llm):
    """NeuroMemory instance with graph_enabled=True."""
    instance = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=mock_llm,
        graph_enabled=True,
    )
    await instance.init()
    yield instance
    await instance.close()


async def _store_triple(nm, user_id, subject, relation, obj, confidence=0.98):
    """Store a graph triple using GraphMemoryService directly."""
    async with nm._db.session() as session:
        svc = GraphMemoryService(session)
        await svc.store_triples(user_id, [{
            "subject": subject,
            "subject_type": "user" if subject == "user" else "entity",
            "relation": relation,
            "object": obj,
            "object_type": "organization",
            "content": f"{subject} {relation} {obj}",
            "confidence": confidence,
        }])


class TestGraphBoost:
    """Test graph triple coverage boost on vector results."""

    @pytest.mark.asyncio
    async def test_graph_boost_dual_hit(self, nm_graph):
        """Memory containing both subject and object of a triple gets higher boost."""
        user_id = "boost_dual"
        await nm_graph._add_memory(
            user_id=user_id,
            content="张三在 Google 工作了3年",
            memory_type="fact",
        )
        await nm_graph._add_memory(
            user_id=user_id,
            content="今天天气很好适合出游",
            memory_type="episodic",
        )
        await _store_triple(nm_graph, user_id, "张三", "works_at", "google")

        result = await nm_graph.recall(user_id=user_id, query="张三 google")

        # Find the boosted memory
        boosted = [m for m in result["merged"] if "Google" in m["content"] and m["source"] == "vector"]
        assert len(boosted) > 0
        assert boosted[0].get("graph_boost", 0.0) > 0.0

    @pytest.mark.asyncio
    async def test_graph_boost_single_hit(self, nm_graph):
        """Memory containing only one entity of a triple gets a smaller boost."""
        user_id = "boost_single"
        await nm_graph._add_memory(
            user_id=user_id,
            content="Google 发布了新产品",
            memory_type="fact",
        )
        await _store_triple(nm_graph, user_id, "张三", "works_at", "google")

        result = await nm_graph.recall(user_id=user_id, query="张三 google")

        boosted = [m for m in result["merged"] if "Google" in m["content"] and m["source"] == "vector"]
        assert len(boosted) > 0
        boost_val = boosted[0].get("graph_boost", 0.0)
        # Single hit: boost should be > 0 but less than dual hit (0.10)
        assert boost_val > 0.0
        assert boost_val <= 0.04

    @pytest.mark.asyncio
    async def test_graph_boost_no_graph(self, nm):
        """Without graph enabled, no graph_boost field appears."""
        user_id = "boost_none"
        await nm._add_memory(user_id=user_id, content="no graph test memory")
        result = await nm.recall(user_id=user_id, query="no graph test memory")

        assert len(result["merged"]) > 0
        for item in result["merged"]:
            # No graph_boost when graph is disabled (graph_results is empty)
            assert "graph_boost" not in item or item["graph_boost"] == 0.0

    @pytest.mark.asyncio
    async def test_graph_results_in_merged(self, nm_graph):
        """Graph triples should appear in merged with source='graph'."""
        user_id = "graph_merged"
        await nm_graph._add_memory(user_id=user_id, content="测试记忆内容")
        await _store_triple(nm_graph, user_id, "user", "lives_in", "北京")

        result = await nm_graph.recall(user_id=user_id, query="北京")

        graph_in_merged = [m for m in result["merged"] if m.get("source") == "graph"]
        assert len(graph_in_merged) > 0
        assert graph_in_merged[0]["memory_type"] == "graph_fact"
        assert "→" in graph_in_merged[0]["content"]

    @pytest.mark.asyncio
    async def test_merged_sorted_by_score(self, nm_graph):
        """Merged results should be sorted by score descending."""
        user_id = "sort_test"
        for i in range(5):
            await nm_graph._add_memory(
                user_id=user_id,
                content=f"memory item number {i} about sorting",
                memory_type="fact",
            )
        await _store_triple(nm_graph, user_id, "user", "has_skill", "sorting")

        result = await nm_graph.recall(user_id=user_id, query="sorting")

        scores = [m.get("score", 0) for m in result["merged"]]
        assert scores == sorted(scores, reverse=True), "merged should be sorted by score descending"

    @pytest.mark.asyncio
    async def test_graph_boost_cap(self, nm_graph):
        """Graph boost should be capped at 2.0 even with many matching triples."""
        user_id = "boost_cap"
        # Memory that mentions both alice and bob
        await nm_graph._add_memory(
            user_id=user_id,
            content="alice and bob went to google together with charlie",
            memory_type="episodic",
        )
        # Multiple triples that all match the memory
        await _store_triple(nm_graph, user_id, "alice", "knows", "bob")
        await _store_triple(nm_graph, user_id, "alice", "works_at", "google")
        await _store_triple(nm_graph, user_id, "bob", "works_at", "google")
        await _store_triple(nm_graph, user_id, "charlie", "knows", "alice")

        result = await nm_graph.recall(user_id=user_id, query="alice bob google charlie")

        boosted = [m for m in result["merged"] if m["source"] == "vector" and "graph_boost" in m]
        for item in boosted:
            assert item["graph_boost"] <= 0.20, f"boost should be capped at 0.20, got {item['graph_boost']}"
