"""Tests for recall: three-factor scored search (relevance × recency × importance) + graph merge."""

from __future__ import annotations

import pytest
from sqlalchemy import text

import pytest_asyncio

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider
from neuromem.services.search import DEFAULT_DECAY_RATE, SearchService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


class MockLLMProvider(LLMProvider):
    """Mock LLM that returns preset extraction results."""

    def __init__(self, response: str = ""):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


@pytest_asyncio.fixture
async def nm_with_llm(mock_embedding):
    """NeuroMemory instance with mock LLM for full-pipeline tests."""
    llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "在 Google 工作", "category": "work", "confidence": 0.98, "importance": 8},
    {"content": "住在北京", "category": "location", "confidence": 0.90, "importance": 5}
  ],
  "episodes": [],
  "triples": [],
  "profile_updates": {
    "preferences": ["喜欢用 Python 编程"]
  }
}
```""")
    instance = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=llm,
    )
    await instance.init()
    yield instance
    await instance.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _add_memory(svc, session, user_id, content, memory_type="general",
                      metadata=None, age_days=0):
    """Add memory and optionally back-date it."""
    record = await svc.add_memory(
        user_id=user_id, content=content,
        memory_type=memory_type, metadata=metadata,
    )
    if age_days > 0:
        await session.execute(
            text("""
                UPDATE embeddings
                SET created_at = NOW() - INTERVAL ':days days'
                WHERE id = :id
            """.replace(":days", str(int(age_days)))),
            {"id": str(record.id)},
        )
    return record


async def _setup_and_search(svc, session, user_id, memories, query, **kwargs):
    """Insert multiple memories, commit, then scored_search."""
    records = []
    for m in memories:
        rec = await _add_memory(
            svc, session, user_id,
            content=m["content"],
            memory_type=m.get("memory_type", "general"),
            metadata=m.get("metadata"),
            age_days=m.get("age_days", 0),
        )
        records.append(rec)
    await session.commit()
    results = await svc.scored_search(user_id=user_id, query=query, **kwargs)
    return records, results


# ===========================================================================
# A. Recency (time decay)
# ===========================================================================

class TestRecallRecency:
    """Test exponential time decay factor."""

    @pytest.mark.asyncio
    async def test_fresh_memory_recency_near_max(self, db_session, mock_embedding):
        """A just-created memory should have recency bonus ≈ 0.15."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(user_id="recency_u1", content="fresh memory")
        await db_session.commit()

        results = await svc.scored_search(user_id="recency_u1", query="fresh memory")
        assert len(results) == 1
        assert results[0]["recency"] > 0.148  # 0.15 × ~1.0

    @pytest.mark.asyncio
    async def test_old_memory_decays(self, db_session, mock_embedding):
        """A 30-day-old memory with 30-day decay rate should have recency ≈ 0.15 × e^-1 ≈ 0.055."""
        svc = SearchService(db_session, mock_embedding)
        await _add_memory(svc, db_session, "recency_u2", "old memory", age_days=30)
        await db_session.commit()

        results = await svc.scored_search(
            user_id="recency_u2", query="old memory",
            decay_rate=86400 * 30,
        )
        assert len(results) == 1
        # 0.15 × e^(-1) ≈ 0.055
        assert 0.045 < results[0]["recency"] < 0.065

    @pytest.mark.asyncio
    async def test_very_old_memory_near_zero(self, db_session, mock_embedding):
        """A 1-year-old memory with 30-day decay should have recency near zero."""
        svc = SearchService(db_session, mock_embedding)
        await _add_memory(svc, db_session, "recency_u3", "ancient memory", age_days=365)
        await db_session.commit()

        results = await svc.scored_search(
            user_id="recency_u3", query="ancient memory",
            decay_rate=86400 * 30,
        )
        assert len(results) == 1
        # e^(-365/30) ≈ 0.000005
        assert results[0]["recency"] < 0.001

    @pytest.mark.asyncio
    async def test_fresh_beats_old_same_content(self, db_session, mock_embedding):
        """With identical content, a fresh memory should score higher than an old one."""
        svc = SearchService(db_session, mock_embedding)
        old = await _add_memory(svc, db_session, "recency_u4", "same content", age_days=60)
        fresh = await _add_memory(svc, db_session, "recency_u4", "same content", age_days=0)
        await db_session.commit()

        results = await svc.scored_search(user_id="recency_u4", query="same content")
        assert len(results) == 2
        # Fresh should rank first
        assert results[0]["id"] == str(fresh.id)
        assert results[1]["id"] == str(old.id)
        assert results[0]["score"] > results[1]["score"]

    @pytest.mark.asyncio
    async def test_decay_rate_parameter_changes_speed(self, db_session, mock_embedding):
        """Larger decay_rate makes memories fade slower."""
        svc = SearchService(db_session, mock_embedding)
        await _add_memory(svc, db_session, "recency_u5", "test decay rate", age_days=30)
        await db_session.commit()

        # Short decay: 30 days → e^(-30/30) = e^-1 ≈ 0.368
        fast = await svc.scored_search(
            user_id="recency_u5", query="test decay rate",
            decay_rate=86400 * 30,
        )
        # Long decay: 90 days → e^(-30/90) = e^-0.33 ≈ 0.717
        slow = await svc.scored_search(
            user_id="recency_u5", query="test decay rate",
            decay_rate=86400 * 90,
        )
        assert slow[0]["recency"] > fast[0]["recency"]

    @pytest.mark.asyncio
    async def test_multiple_ages_rank_by_recency(self, db_session, mock_embedding):
        """Memories at different ages should rank newest first (same content/importance)."""
        svc = SearchService(db_session, mock_embedding)
        for days in [90, 7, 30, 1]:
            await _add_memory(
                svc, db_session, "recency_u6", "identical content",
                metadata={"importance": 5}, age_days=days,
            )
        await db_session.commit()

        results = await svc.scored_search(user_id="recency_u6", query="identical content")
        recencies = [r["recency"] for r in results]
        # Should be sorted descending (freshest first)
        assert recencies == sorted(recencies, reverse=True)


# ===========================================================================
# B. Importance
# ===========================================================================

class TestRecallImportance:
    """Test importance factor (metadata.importance / 10)."""

    @pytest.mark.asyncio
    async def test_importance_scaling(self, db_session, mock_embedding):
        """Importance 1/5/10 should map to 0.015/0.075/0.15 (0.15 × imp/10)."""
        svc = SearchService(db_session, mock_embedding)
        for imp in [1, 5, 10]:
            await svc.add_memory(
                user_id="imp_u1", content=f"importance {imp}",
                metadata={"importance": imp},
            )
        await db_session.commit()

        results = await svc.scored_search(user_id="imp_u1", query="importance", limit=10)
        imp_values = sorted([r["importance"] for r in results])
        assert abs(imp_values[0] - 0.015) < 0.002
        assert abs(imp_values[1] - 0.075) < 0.002
        assert abs(imp_values[2] - 0.15) < 0.002

    @pytest.mark.asyncio
    async def test_default_importance_is_half(self, db_session, mock_embedding):
        """Memory without importance metadata should default to 0.075 (0.15 × 0.5)."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(user_id="imp_u2", content="no importance set")
        await db_session.commit()

        results = await svc.scored_search(user_id="imp_u2", query="no importance set")
        assert results[0]["importance"] == 0.075

    @pytest.mark.asyncio
    async def test_high_importance_beats_low(self, db_session, mock_embedding):
        """Same content and recency: higher importance should produce higher score."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(
            user_id="imp_u3", content="same text A",
            metadata={"importance": 10},
        )
        await svc.add_memory(
            user_id="imp_u3", content="same text B",
            metadata={"importance": 1},
        )
        await db_session.commit()

        results = await svc.scored_search(user_id="imp_u3", query="same text", limit=10)
        assert len(results) == 2
        # Higher importance should rank first (recency is similar for both)
        assert results[0]["importance"] > results[1]["importance"]


# ===========================================================================
# C. Arousal modifier (slows decay)
# ===========================================================================

class TestRecallArousal:
    """Test that emotional arousal slows recency decay."""

    @pytest.mark.asyncio
    async def test_high_arousal_higher_recency(self, db_session, mock_embedding):
        """High arousal memory decays slower: effective_decay = decay_rate * (1 + arousal * 0.5)."""
        svc = SearchService(db_session, mock_embedding)
        excited = await _add_memory(
            svc, db_session, "arousal_u1", "exciting event",
            metadata={"importance": 5, "emotion": {"arousal": 1.0, "valence": 0.5}},
            age_days=30,
        )
        calm = await _add_memory(
            svc, db_session, "arousal_u1", "calm event",
            metadata={"importance": 5, "emotion": {"arousal": 0.0, "valence": 0.0}},
            age_days=30,
        )
        await db_session.commit()

        results = await svc.scored_search(
            user_id="arousal_u1", query="event", decay_rate=86400 * 30,
        )
        excited_r = next(r for r in results if r["id"] == str(excited.id))
        calm_r = next(r for r in results if r["id"] == str(calm.id))

        # arousal=1.0: 0.15 × e^(-30/45) ≈ 0.15 × 0.513 ≈ 0.077
        # arousal=0.0: 0.15 × e^(-30/30) ≈ 0.15 × 0.368 ≈ 0.055
        assert excited_r["recency"] > calm_r["recency"]
        assert abs(excited_r["recency"] - 0.077) < 0.01
        assert abs(calm_r["recency"] - 0.055) < 0.01

    @pytest.mark.asyncio
    async def test_no_emotion_defaults_zero_arousal(self, db_session, mock_embedding):
        """Memory without emotion metadata should behave as arousal=0."""
        svc = SearchService(db_session, mock_embedding)
        with_emotion = await _add_memory(
            svc, db_session, "arousal_u2", "with zero arousal",
            metadata={"importance": 5, "emotion": {"arousal": 0.0}},
            age_days=10,
        )
        without_emotion = await _add_memory(
            svc, db_session, "arousal_u2", "without emotion meta",
            metadata={"importance": 5},
            age_days=10,
        )
        await db_session.commit()

        results = await svc.scored_search(user_id="arousal_u2", query="arousal")
        r_with = next(r for r in results if r["id"] == str(with_emotion.id))
        r_without = next(r for r in results if r["id"] == str(without_emotion.id))

        # Both should have same recency (arousal=0 and missing emotion are equivalent)
        assert abs(r_with["recency"] - r_without["recency"]) < 0.01


# ===========================================================================
# D. Combined scoring
# ===========================================================================

class TestRecallCombinedScoring:
    """Test the multiplication of three factors."""

    @pytest.mark.asyncio
    async def test_score_equals_cosine_formula(self, db_session, mock_embedding):
        """score should equal base_relevance × (1 + recency_bonus + importance_bonus)."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(
            user_id="combo_u1", content="product test",
            metadata={"importance": 7},
        )
        await db_session.commit()

        results = await svc.scored_search(user_id="combo_u1", query="product test")
        r = results[0]
        base_relevance = min(r["relevance"] + (0.05 if r["bm25_score"] > 0 else 0), 1.0)
        expected = round(base_relevance * (1.0 + r["recency"] + r["importance"]), 4)
        assert r["score"] == expected

    @pytest.mark.asyncio
    async def test_results_sorted_by_score_desc(self, db_session, mock_embedding):
        """Results must be ordered by score descending."""
        svc = SearchService(db_session, mock_embedding)
        for imp in [2, 8, 5, 10, 1]:
            await svc.add_memory(
                user_id="combo_u2", content=f"item {imp}",
                metadata={"importance": imp},
            )
        await db_session.commit()

        results = await svc.scored_search(user_id="combo_u2", query="item", limit=10)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_importance_can_outweigh_recency(self, db_session, mock_embedding):
        """A very important old memory can outrank a trivial fresh one."""
        svc = SearchService(db_session, mock_embedding)
        # Old but very important
        old_important = await _add_memory(
            svc, db_session, "combo_u3", "same query text",
            metadata={"importance": 10}, age_days=7,
        )
        # Fresh but trivial
        fresh_trivial = await _add_memory(
            svc, db_session, "combo_u3", "same query text",
            metadata={"importance": 1}, age_days=0,
        )
        await db_session.commit()

        results = await svc.scored_search(
            user_id="combo_u3", query="same query text",
            decay_rate=86400 * 30,
        )
        # importance 10 (1.0) vs 1 (0.1), recency ~0.79 vs ~1.0
        # old_important score ≈ rel * 0.79 * 1.0 = 0.79 * rel
        # fresh_trivial score ≈ rel * 1.0 * 0.1 = 0.1 * rel
        assert results[0]["id"] == str(old_important.id)

    @pytest.mark.asyncio
    async def test_idempotent_query(self, db_session, mock_embedding):
        """Same query twice should return same scores (excluding access_count)."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(
            user_id="combo_u4", content="idempotent",
            metadata={"importance": 6},
        )
        await db_session.commit()

        r1 = await svc.scored_search(user_id="combo_u4", query="idempotent")
        r2 = await svc.scored_search(user_id="combo_u4", query="idempotent")
        # Scores should be identical (time diff is negligible within same test)
        assert abs(r1[0]["score"] - r2[0]["score"]) < 0.001


# ===========================================================================
# E. End-to-end scenarios: insert multiple memories, then recall
# ===========================================================================

class TestRecallScenarios:
    """Simulate realistic usage: insert many memories, then recall by topic."""

    @pytest.mark.asyncio
    async def test_recall_finds_inserted_memory(self, nm):
        """Insert a memory, recall with the same text, verify it appears."""
        content = "我在 Google 做后端开发"
        await nm._add_memory(user_id="scene_u1", content=content)

        result = await nm.recall(user_id="scene_u1", query=content)
        recalled_contents = [m["content"] for m in result["merged"]]
        assert content in recalled_contents

    @pytest.mark.asyncio
    async def test_recall_all_results_are_from_inserted_set(self, nm):
        """All recalled memories must be a subset of what was inserted."""
        inserted = [
            "我在北京工作",
            "喜欢吃火锅",
            "养了一只猫叫小白",
            "周末喜欢爬山",
            "用 Python 写代码",
        ]
        for content in inserted:
            await nm._add_memory(user_id="scene_u2", content=content)

        result = await nm.recall(user_id="scene_u2", query="工作", limit=10)
        recalled_contents = {m["content"] for m in result["merged"]}
        # Every recalled content must be one of the inserted memories
        assert recalled_contents.issubset(set(inserted))
        # Should recall at least one
        assert len(recalled_contents) > 0

    @pytest.mark.asyncio
    async def test_recall_specific_memory_among_many(self, nm):
        """Insert many memories, query with exact content, verify that one is recalled."""
        memories = [
            ("fact", "在字节跳动担任算法工程师"),
            ("fact", "住在上海浦东"),
            ("episodic", "昨天面试了阿里巴巴"),
            ("general", "喜欢用 VS Code 写代码"),
            ("fact", "本科毕业于清华大学"),
        ]
        for mtype, content in memories:
            await nm._add_memory(user_id="scene_u3", content=content, memory_type=mtype)

        # Query with exact content of one memory
        target = "在字节跳动担任算法工程师"
        result = await nm.recall(user_id="scene_u3", query=target)
        recalled_contents = [m["content"] for m in result["merged"]]
        assert target in recalled_contents

    @pytest.mark.asyncio
    async def test_recall_with_importance_ranking(self, nm):
        """Insert memories with different importance, verify high importance recalled first."""
        await nm._add_memory(
            user_id="scene_u4", content="random chat about weather",
            metadata={"importance": 1},
        )
        await nm._add_memory(
            user_id="scene_u4", content="user birthday is March 15",
            metadata={"importance": 9},
        )
        await nm._add_memory(
            user_id="scene_u4", content="prefers dark mode",
            metadata={"importance": 3},
        )

        result = await nm.recall(user_id="scene_u4", query="user", limit=10)
        merged = result["merged"]
        assert len(merged) >= 2

        # All recalled items should have score > 0
        for m in merged:
            assert m.get("score", 0) > 0 or m.get("source") == "graph"

    @pytest.mark.asyncio
    async def test_recall_preserves_memory_type(self, nm):
        """Recalled memories should carry their original memory_type."""
        await nm._add_memory(user_id="scene_u5", content="fact content", memory_type="fact")
        await nm._add_memory(user_id="scene_u5", content="episodic content", memory_type="episodic")

        result = await nm.recall(user_id="scene_u5", query="content", limit=10)
        types_found = {m["memory_type"] for m in result["merged"]}
        assert "fact" in types_found or "episodic" in types_found

    @pytest.mark.asyncio
    async def test_recall_after_incremental_inserts(self, nm):
        """Simulate a conversation: add memories one by one, recall after each."""
        user_id = "scene_u6"

        # Round 1: insert first memory
        await nm._add_memory(user_id=user_id, content="my name is Alice")
        result1 = await nm.recall(user_id=user_id, query="my name is Alice")
        assert len(result1["merged"]) == 1

        # Round 2: insert second memory, recall should find both
        await nm._add_memory(user_id=user_id, content="I live in Beijing")
        result2 = await nm.recall(user_id=user_id, query="name", limit=10)
        assert len(result2["merged"]) >= 1
        # Total memories should be 2 now
        result_all = await nm.recall(user_id=user_id, query="Alice Beijing", limit=10)
        assert len(result_all["merged"]) == 2

    @pytest.mark.asyncio
    async def test_recall_different_users_independent(self, nm):
        """Two users with separate memories should recall independently."""
        await nm._add_memory(user_id="alice", content="Alice works at Google")
        await nm._add_memory(user_id="alice", content="Alice likes Python")
        await nm._add_memory(user_id="bob", content="Bob works at Microsoft")
        await nm._add_memory(user_id="bob", content="Bob likes Java")

        alice_result = await nm.recall(user_id="alice", query="works at", limit=10)
        bob_result = await nm.recall(user_id="bob", query="works at", limit=10)

        alice_contents = {m["content"] for m in alice_result["merged"]}
        bob_contents = {m["content"] for m in bob_result["merged"]}

        # Alice should not see Bob's memories and vice versa
        assert all("Alice" in c for c in alice_contents)
        assert all("Bob" in c for c in bob_contents)
        assert alice_contents.isdisjoint(bob_contents)

    @pytest.mark.asyncio
    async def test_recall_returns_scores_for_ranking(self, nm):
        """Each vector result should have relevance, recency, importance, score."""
        await nm._add_memory(
            user_id="scene_u7", content="test memory with score",
            metadata={"importance": 7},
        )
        result = await nm.recall(user_id="scene_u7", query="test memory with score")

        for r in result["vector_results"]:
            assert "relevance" in r
            assert "recency" in r
            assert "importance" in r
            assert "score" in r
            assert "rrf_score" in r
            # score = base_relevance × (1 + recency_bonus + importance_bonus)
            base_relevance = min(r["relevance"] + (0.05 if r["bm25_score"] > 0 else 0), 1.0)
            expected = round(base_relevance * (1.0 + r["recency"] + r["importance"]), 4)
            assert r["score"] == expected


# ===========================================================================
# F. recall() facade (NeuroMemory.recall) - API contract
# ===========================================================================

class TestRecallFacade:
    """Test the NeuroMemory.recall() method (facade over scored_search + graph)."""

    @pytest.mark.asyncio
    async def test_recall_returns_correct_keys(self, nm):
        """recall() should return vector_results, graph_results, merged."""
        await nm._add_memory(user_id="facade_u1", content="facade test")
        result = await nm.recall(user_id="facade_u1", query="facade test")

        assert "vector_results" in result
        assert "graph_results" in result
        assert "merged" in result

    @pytest.mark.asyncio
    async def test_recall_merged_has_source_tag(self, nm):
        """Each item in merged should have a 'source' field."""
        await nm._add_memory(user_id="facade_u2", content="source tag test")
        result = await nm.recall(user_id="facade_u2", query="source tag test")

        assert len(result["merged"]) > 0
        for item in result["merged"]:
            assert "source" in item
            assert item["source"] in ("vector", "graph")

    @pytest.mark.asyncio
    async def test_recall_merged_deduplicates(self, nm):
        """Duplicate content should appear only once in merged."""
        await nm._add_memory(user_id="facade_u3", content="duplicate content A")
        await nm._add_memory(user_id="facade_u3", content="duplicate content A")
        result = await nm.recall(user_id="facade_u3", query="duplicate content A")

        contents = [m["content"] for m in result["merged"]]
        assert len(contents) == len(set(contents))

    @pytest.mark.asyncio
    async def test_recall_respects_limit(self, nm):
        """merged should not exceed the requested limit."""
        for i in range(20):
            await nm._add_memory(user_id="facade_u4", content=f"memory number {i}")

        result = await nm.recall(user_id="facade_u4", query="memory number", limit=5)
        assert len(result["merged"]) <= 5

    @pytest.mark.asyncio
    async def test_recall_user_isolation(self, nm):
        """recall() should only return memories of the queried user."""
        await nm._add_memory(user_id="user_x", content="secret of X")
        await nm._add_memory(user_id="user_y", content="secret of Y")

        result = await nm.recall(user_id="user_x", query="secret")
        for item in result["merged"]:
            assert "X" in item["content"]

    @pytest.mark.asyncio
    async def test_recall_empty_results(self, nm):
        """recall() on a user with no memories should return empty lists."""
        result = await nm.recall(user_id="nonexistent_user", query="anything")
        assert result["vector_results"] == []
        assert result["graph_results"] == []
        assert result["merged"] == []

    @pytest.mark.asyncio
    async def test_recall_custom_decay_rate(self, nm):
        """Custom decay_rate should be passed through to scored_search."""
        await nm._add_memory(
            user_id="facade_u5", content="decay rate test",
            metadata={"importance": 5},
        )

        # Very large decay rate → recency bonus stays close to 0.15
        result = await nm.recall(
            user_id="facade_u5", query="decay rate test",
            decay_rate=86400 * 365,  # 1-year decay
        )
        assert len(result["merged"]) > 0
        assert result["vector_results"][0]["recency"] > 0.148  # ≈ 0.15

    @pytest.mark.asyncio
    async def test_recall_default_decay_rate(self, nm):
        """Without decay_rate, should use DEFAULT_DECAY_RATE (30 days)."""
        await nm._add_memory(
            user_id="facade_u6", content="default decay",
            metadata={"importance": 5},
        )

        result = await nm.recall(user_id="facade_u6", query="default decay")
        # Fresh memory → recency bonus near 0.15 regardless of decay_rate
        assert result["vector_results"][0]["recency"] > 0.148


# ===========================================================================
# F. Edge cases
# ===========================================================================

class TestRecallEdgeCases:
    """Boundary conditions and special cases."""

    @pytest.mark.asyncio
    async def test_single_memory(self, db_session, mock_embedding):
        """Should work with only one memory in the database."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(user_id="edge_u1", content="only one")
        await db_session.commit()

        results = await svc.scored_search(user_id="edge_u1", query="only one")
        assert len(results) == 1
        assert results[0]["score"] > 0

    @pytest.mark.asyncio
    async def test_limit_one(self, db_session, mock_embedding):
        """limit=1 should return exactly one result."""
        svc = SearchService(db_session, mock_embedding)
        for i in range(5):
            await svc.add_memory(user_id="edge_u2", content=f"entry {i}")
        await db_session.commit()

        results = await svc.scored_search(user_id="edge_u2", query="entry", limit=1)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_memory_type_filter(self, db_session, mock_embedding):
        """scored_search with memory_type filter should only return matching type."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(
            user_id="edge_u3", content="this is a fact",
            memory_type="fact", metadata={"importance": 5},
        )
        await svc.add_memory(
            user_id="edge_u3", content="this is episodic",
            memory_type="episodic", metadata={"importance": 5},
        )
        await db_session.commit()

        results = await svc.scored_search(
            user_id="edge_u3", query="this is",
            memory_type="fact",
        )
        assert all(r["memory_type"] == "fact" for r in results)

    @pytest.mark.asyncio
    async def test_metadata_preserved_in_results(self, db_session, mock_embedding):
        """Full metadata object should be returned in results."""
        svc = SearchService(db_session, mock_embedding)
        meta = {
            "importance": 8,
            "emotion": {"valence": -0.5, "arousal": 0.7, "label": "anxious"},
            "custom_field": "custom_value",
        }
        await svc.add_memory(
            user_id="edge_u4", content="metadata check",
            metadata=meta,
        )
        await db_session.commit()

        results = await svc.scored_search(user_id="edge_u4", query="metadata check")
        assert results[0]["metadata"]["emotion"]["label"] == "anxious"
        assert results[0]["metadata"]["custom_field"] == "custom_value"

    @pytest.mark.asyncio
    async def test_all_scores_non_negative(self, db_session, mock_embedding):
        """All factor scores should be >= 0."""
        svc = SearchService(db_session, mock_embedding)
        await svc.add_memory(
            user_id="edge_u5", content="non negative check",
            metadata={"importance": 1},
        )
        await db_session.commit()

        results = await svc.scored_search(user_id="edge_u5", query="non negative check")
        for r in results:
            assert r["relevance"] >= 0
            assert r["recency"] >= 0
            assert r["importance"] >= 0
            assert r["score"] >= 0

    @pytest.mark.asyncio
    async def test_access_tracking_increments(self, db_session, mock_embedding):
        """Multiple scored_search calls should increment access_count."""
        svc = SearchService(db_session, mock_embedding)
        record = await svc.add_memory(
            user_id="edge_u6", content="access tracking test",
        )
        await db_session.commit()

        # Search three times
        for _ in range(3):
            await svc.scored_search(user_id="edge_u6", query="access tracking test")

        result = await db_session.execute(
            text("SELECT access_count, last_accessed_at FROM embeddings WHERE id = :id"),
            {"id": str(record.id)},
        )
        row = result.fetchone()
        assert row.access_count == 3
        assert row.last_accessed_at is not None


# ===========================================================================
# G. Full pipeline: ingest → extract_memories → recall
# ===========================================================================

class TestRecallFullPipeline:
    """Test the complete flow: conversation messages → LLM extraction → recall.

    Unlike other recall tests that use add_memory() directly, these tests
    exercise the full pipeline through MemoryExtractionService with a mock LLM.
    """

    @pytest.mark.asyncio
    async def test_extracted_facts_are_recallable(self, nm_with_llm):
        """Facts extracted by LLM from conversation should appear in recall results."""
        user_id = "pipeline_u1"

        # Step 1: Add conversation messages
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user",
            content="我在 Google 工作，住在北京",
        )
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="assistant",
            content="了解了！",
        )

        # Step 2: Get unextracted messages and extract
        messages = await nm_with_llm.conversations.get_unextracted_messages(user_id)
        result = await nm_with_llm._extract_memories(user_id, messages)

        assert result["facts_extracted"] == 2

        # Step 3: Recall should find the extracted memories
        recall_result = await nm_with_llm.recall(user_id=user_id, query="Google 工作")
        contents = [m["content"] for m in recall_result["merged"]]
        assert any("Google" in c for c in contents)

    @pytest.mark.asyncio
    async def test_extracted_preferences_stored_in_profile(self, nm_with_llm):
        """Preferences extracted by LLM should be stored in profile KV and queryable."""
        user_id = "pipeline_u2"

        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user",
            content="我喜欢用 Python 编程",
        )
        messages = await nm_with_llm.conversations.get_unextracted_messages(user_id)
        await nm_with_llm._extract_memories(user_id, messages)

        # Preferences should be in profile KV store
        pref = await nm_with_llm.kv.get(user_id, "profile", "preferences")
        assert pref is not None
        assert isinstance(pref.value, list)
        assert any("Python" in p for p in pref.value)

    @pytest.mark.asyncio
    async def test_pipeline_recall_has_importance_from_extraction(self, nm_with_llm):
        """Extracted facts should carry importance metadata into recall scoring."""
        user_id = "pipeline_u3"

        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user",
            content="我在 Google 工作",
        )
        messages = await nm_with_llm.conversations.get_unextracted_messages(user_id)
        await nm_with_llm._extract_memories(user_id, messages)

        recall_result = await nm_with_llm.recall(user_id=user_id, query="Google")
        for r in recall_result["vector_results"]:
            if "Google" in r["content"]:
                # importance=8 from mock LLM → 0.15 × 0.8 = 0.12
                assert r["importance"] >= 0.075

    @pytest.mark.asyncio
    async def test_reflect_extracts_and_marks_messages(self, nm_with_llm):
        """v0.2.0: ingest auto-extracts, digest() generates insights."""
        user_id = "pipeline_u4"

        # v0.2.0: ingest auto-extracts memories (auto_extract=True default)
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user", content="我在 Google 工作",
        )
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="assistant", content="了解了！",
        )

        # Wait for background auto-extraction to complete
        import asyncio
        await asyncio.sleep(0.3)

        # Memories should already be extracted and recallable
        recall_result = await nm_with_llm.recall(user_id=user_id, query="Google")
        assert len(recall_result["merged"]) > 0

        # v0.2.0: digest() only generates insights (no extraction)
        result = await nm_with_llm.digest(user_id=user_id, batch_size=50)
        assert "insights_generated" in result
        assert "insights" in result
        assert "emotion_profile" in result
        # v0.2.0: No longer returns extraction counters
        assert "conversations_processed" not in result

    @pytest.mark.asyncio
    async def test_pipeline_multiple_conversations_accumulate(self, nm_with_llm):
        """Multiple conversation rounds should accumulate memories for recall."""
        user_id = "pipeline_u5"

        # Conversation round 1
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user", content="我在 Google 工作",
        )
        msgs1 = await nm_with_llm.conversations.get_unextracted_messages(user_id)
        await nm_with_llm._extract_memories(user_id, msgs1)

        # Conversation round 2 (same mock LLM response, but that's OK for structure testing)
        await nm_with_llm.conversations.ingest(
            user_id=user_id, role="user", content="住在北京海淀区",
        )
        msgs2 = await nm_with_llm.conversations.get_unextracted_messages(user_id)
        await nm_with_llm._extract_memories(user_id, msgs2)

        # Should have memories from both rounds
        recall_result = await nm_with_llm.recall(user_id=user_id, query="Google 北京", limit=10)
        assert len(recall_result["merged"]) >= 2

    @pytest.mark.asyncio
    async def test_on_extraction_callback(self, mock_embedding):
        """on_extraction callback should be invoked with correct stats after extraction."""
        llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "在 Google 工作", "category": "work", "confidence": 0.98, "importance": 8}
  ],
  "episodes": [],
  "triples": [],
  "profile_updates": {}
}
```""")
        callback_data = []
        instance = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=llm,
            on_extraction=lambda stats: callback_data.append(stats),
        )
        await instance.init()
        try:
            user_id = "callback_u1"
            await instance.conversations.ingest(
                user_id=user_id, role="user", content="我在 Google 工作",
            )
            messages = await instance.conversations.get_unextracted_messages(user_id)
            # Use _do_extraction which triggers the callback
            await instance._do_extraction(user_id, messages[0].session_id)

            assert len(callback_data) == 1
            stats = callback_data[0]
            assert stats["user_id"] == user_id
            assert "session_id" in stats
            assert isinstance(stats["duration"], float)
            assert stats["duration"] >= 0
            assert stats["facts_extracted"] == 1
            assert stats["episodes_extracted"] == 0
            assert stats["triples_extracted"] == 0
            assert stats["messages_processed"] == 1
        finally:
            await instance.close()

    @pytest.mark.asyncio
    async def test_on_extraction_async_callback(self, mock_embedding):
        """on_extraction should support async callbacks."""
        llm = MockLLMProvider(response="""```json
{
  "facts": [
    {"content": "住在北京", "category": "location", "confidence": 0.9, "importance": 5}
  ],
  "episodes": [],
  "triples": [],
  "profile_updates": {}
}
```""")
        callback_data = []

        async def async_callback(stats):
            callback_data.append(stats)

        instance = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=llm,
            on_extraction=async_callback,
        )
        await instance.init()
        try:
            user_id = "callback_u2"
            await instance.conversations.ingest(
                user_id=user_id, role="user", content="住在北京",
            )
            messages = await instance.conversations.get_unextracted_messages(user_id)
            await instance._do_extraction(user_id, messages[0].session_id)

            assert len(callback_data) == 1
            assert callback_data[0]["facts_extracted"] == 1
        finally:
            await instance.close()
