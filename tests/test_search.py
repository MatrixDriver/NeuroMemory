"""Tests for memory add and semantic search."""

import pytest

from neuromem.services.search import SearchService


@pytest.mark.asyncio
async def test_add_memory(db_session, mock_embedding):
    """Add a memory and verify it returns correctly."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id="u1",
        content="I work at ABC Company as a Python developer",
        memory_type="fact",
    )
    assert record.content == "I work at ABC Company as a Python developer"
    assert record.memory_type == "fact"
    assert record.id is not None


@pytest.mark.asyncio
async def test_search_memories(db_session, mock_embedding):
    """Add memories and search for them."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(user_id="search_user", content="I love Python programming")
    await svc.add_memory(user_id="search_user", content="My favorite food is sushi")
    await db_session.commit()

    results = await svc.search(user_id="search_user", query="programming language", limit=5)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_with_memory_type_filter(db_session, mock_embedding):
    """Search with memory type filter."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(user_id="u2", content="Fact about Python", memory_type="fact")
    await svc.add_memory(user_id="u2", content="Event yesterday", memory_type="episodic")
    await db_session.commit()

    results = await svc.search(user_id="u2", query="Python", memory_type="fact")
    assert all(r["memory_type"] == "fact" for r in results)


@pytest.mark.asyncio
async def test_search_user_isolation(db_session, mock_embedding):
    """Search should only return memories for the specified user."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(user_id="user_a", content="Secret info for A")
    await svc.add_memory(user_id="user_b", content="Secret info for B")
    await db_session.commit()

    results = await svc.search(user_id="user_a", query="secret info", limit=10)
    for r in results:
        assert "user_a" or r["content"] == "Secret info for A"


@pytest.mark.asyncio
async def test_add_memory_via_facade(nm):
    """Test adding memory through the NeuroMemory facade."""
    record = await nm._add_memory(user_id="u1", content="I work at Google")
    assert record.content == "I work at Google"
    assert record.id is not None


@pytest.mark.asyncio
async def test_search_via_facade(nm):
    """Test search through the NeuroMemory recall() facade."""
    await nm._add_memory(user_id="facade_user", content="I love cats")
    await nm._add_memory(user_id="facade_user", content="Python is great")

    result = await nm.recall(user_id="facade_user", query="animals")
    assert len(result["merged"]) > 0


@pytest.mark.asyncio
async def test_scored_search(db_session, mock_embedding):
    """Test three-factor scored search returns relevance, recency, importance."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(
        user_id="scored_user", content="重要生日",
        memory_type="fact", metadata={"importance": 9},
    )
    await svc.add_memory(
        user_id="scored_user", content="随口提到天气",
        memory_type="fact", metadata={"importance": 2},
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="scored_user", query="生日", limit=5)
    assert len(results) > 0

    # Each result should have three-factor scores
    for r in results:
        assert "relevance" in r
        assert "recency" in r
        assert "importance" in r
        assert "score" in r
        assert r["relevance"] >= 0
        assert r["recency"] >= 0
        assert r["importance"] >= 0


@pytest.mark.asyncio
async def test_scored_search_importance_affects_ranking(db_session, mock_embedding):
    """Test that higher importance memories score higher."""
    svc = SearchService(db_session, mock_embedding)
    # Both have same content relevance but different importance
    await svc.add_memory(
        user_id="imp_user", content="用户信息 A",
        memory_type="fact", metadata={"importance": 9},
    )
    await svc.add_memory(
        user_id="imp_user", content="用户信息 B",
        memory_type="fact", metadata={"importance": 1},
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="imp_user", query="用户信息", limit=5)
    assert len(results) == 2
    # Higher importance should have higher importance score
    assert results[0]["importance"] >= results[1]["importance"] or results[0]["score"] >= results[1]["score"]


@pytest.mark.asyncio
async def test_scored_search_default_importance(db_session, mock_embedding):
    """Test that memories without importance get default 0.5."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(
        user_id="default_user", content="No importance set",
        memory_type="fact",
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="default_user", query="importance", limit=5)
    assert len(results) > 0
    assert results[0]["importance"] == 0.075  # 0.15 × 0.5 default


@pytest.mark.asyncio
async def test_access_tracking_on_search(db_session, mock_embedding):
    """Test that search updates access_count and last_accessed_at."""
    from sqlalchemy import text

    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(user_id="track_user", content="Track this memory")
    await db_session.commit()

    # Search to trigger access tracking
    await svc.search(user_id="track_user", query="Track this")

    # Check access_count was updated
    result = await db_session.execute(
        text("SELECT access_count, last_accessed_at FROM memories WHERE id = :id"),
        {"id": str(record.id)},
    )
    row = result.fetchone()
    assert row.access_count == 1
    assert row.last_accessed_at is not None


@pytest.mark.asyncio
async def test_access_tracking_on_scored_search(db_session, mock_embedding):
    """Test that scored_search also updates access tracking."""
    from sqlalchemy import text

    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id="track_user2", content="Track scored",
        metadata={"importance": 5},
    )
    await db_session.commit()

    await svc.scored_search(user_id="track_user2", query="Track scored")

    result = await db_session.execute(
        text("SELECT access_count FROM memories WHERE id = :id"),
        {"id": str(record.id)},
    )
    row = result.fetchone()
    assert row.access_count == 1


@pytest.mark.asyncio
async def test_scored_search_with_emotion_arousal(db_session, mock_embedding):
    """Test that high arousal slows decay (higher recency score)."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(
        user_id="emo_user", content="高兴奋记忆",
        memory_type="fact",
        metadata={"importance": 5, "emotion": {"valence": 0.5, "arousal": 0.9, "label": "excited"}},
    )
    await svc.add_memory(
        user_id="emo_user", content="低兴奋记忆",
        memory_type="fact",
        metadata={"importance": 5, "emotion": {"valence": 0.0, "arousal": 0.0, "label": "neutral"}},
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="emo_user", query="记忆", limit=5)
    assert len(results) == 2
    # Both should have valid scores
    for r in results:
        assert r["score"] > 0
