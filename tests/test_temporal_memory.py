"""Tests for temporal (time-related) memory handling.

These tests validate LoCoMo-related issues:
- P1: Time/date information preservation during extraction
- P4: Recency decay behavior for long-term memories
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider


class MockTemporalLLM(LLMProvider):
    """Mock LLM that extracts temporal information."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        # Extract temporal information from conversation
        return """```json
{
  "preferences": [],
  "facts": [
    {"content": "在 Google 工作了 5 年", "category": "work", "confidence": 0.95, "importance": 8}
  ],
  "episodes": [
    {
      "content": "2024 年 1 月入职 Google",
      "timestamp": "2024-01",
      "people": [],
      "location": "北京",
      "confidence": 0.98,
      "importance": 9
    },
    {
      "content": "上周三参加了团队建设活动",
      "timestamp": "last Wednesday",
      "people": ["小王", "小李"],
      "location": "公园",
      "confidence": 0.90,
      "importance": 6
    },
    {
      "content": "明天下午 3 点有面试",
      "timestamp": "tomorrow 3pm",
      "people": [],
      "location": null,
      "confidence": 0.95,
      "importance": 8,
      "emotion": {"valence": 0.3, "arousal": 0.7, "label": "紧张"}
    }
  ],
  "triples": [
    {
      "subject": "user",
      "subject_type": "user",
      "relation": "works_at",
      "object": "Google",
      "object_type": "organization",
      "content": "在 Google 工作了 5 年",
      "confidence": 0.95
    }
  ]
}
```"""


@pytest.mark.asyncio
async def test_episode_timestamp_preservation(mock_embedding):
    """Test that episode timestamps are preserved during extraction."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
        auto_extract=False,  # Manual control for this test
    )
    await nm.init()

    user_id = "temporal_user_1"

    # Add conversation with temporal information
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="我 2024 年 1 月入职 Google，上周三参加了团队建设，明天下午 3 点有面试",
    )

    # Extract memories manually
    messages = await nm.conversations.get_unextracted_messages(user_id)
    await nm._extract_memories(user_id, messages)

    # Verify episodes were extracted with timestamps
    from sqlalchemy import text
    async with nm._db.session() as session:
        result = await session.execute(
            text("SELECT DISTINCT content, metadata FROM memories WHERE user_id = :uid AND memory_type = 'episodic' ORDER BY content"),
            {"uid": user_id},
        )
        episodes = result.fetchall()

    # Should have extracted 3 unique episodes (may have duplicates from multiple calls)
    assert len(episodes) >= 3

    # Find specific episodes by content and check timestamps
    episode_map = {ep.content: ep.metadata for ep in episodes}

    # Check timestamp preservation
    assert "2024 年 1 月入职 Google" in episode_map
    assert episode_map["2024 年 1 月入职 Google"]["timestamp"] == "2024-01"

    assert "上周三参加了团队建设活动" in episode_map
    assert episode_map["上周三参加了团队建设活动"]["timestamp"] == "last Wednesday"

    assert "明天下午 3 点有面试" in episode_map
    assert episode_map["明天下午 3 点有面试"]["timestamp"] == "tomorrow 3pm"

    await nm.close()


@pytest.mark.asyncio
async def test_episode_people_and_location_extraction(mock_embedding):
    """Test that episode people and location are extracted (v0.2.0 feature)."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
        auto_extract=False,
    )
    await nm.init()

    user_id = "temporal_user_2"

    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="上周三我和小王、小李在公园参加了团队建设活动",
    )

    messages = await nm.conversations.get_unextracted_messages(user_id)
    await nm._extract_memories(user_id, messages)

    # Verify people and location
    from sqlalchemy import text
    async with nm._db.session() as session:
        result = await session.execute(
            text("SELECT metadata FROM memories WHERE user_id = :uid AND content = :content"),
            {"uid": user_id, "content": "上周三参加了团队建设活动"},
        )
        rows = result.fetchall()

    # Find row with people and location (v0.2.0 fields)
    row_with_people = None
    for row in rows:
        if "people" in row.metadata:
            row_with_people = row
            break

    assert row_with_people is not None, "No episode with 'people' field found"
    meta = row_with_people.metadata
    assert set(meta["people"]) == {"小王", "小李"}
    assert "location" in meta
    assert meta["location"] == "公园"

    await nm.close()


@pytest.mark.asyncio
async def test_long_term_memory_recall_without_excessive_decay(mock_embedding):
    """Test that long-term memories (months old) can still be recalled.

    This addresses LoCoMo P4: 30-day decay is too aggressive for multi-month conversations.
    """
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
    )
    await nm.init()

    user_id = "temporal_user_3"

    # Add old memory (6 months ago)
    old_memory = await nm._add_memory(
        user_id=user_id,
        content="6 个月前我在微软工作",
        memory_type="episodic",
        metadata={"importance": 8},
    )
    old_memory_id = str(old_memory.id)  # Convert to string

    # Add recent memory (1 day ago)
    recent_memory = await nm._add_memory(
        user_id=user_id,
        content="昨天我面试了 Google",
        memory_type="episodic",
        metadata={"importance": 8},
    )
    recent_memory_id = str(recent_memory.id)  # Convert to string

    # Update timestamps manually to simulate time passing
    from sqlalchemy import text
    async with nm._db.session() as session:
        six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
        one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)

        await session.execute(
            text("UPDATE memories SET created_at = :ts WHERE id = :id"),
            {"ts": six_months_ago, "id": old_memory_id},
        )
        await session.execute(
            text("UPDATE memories SET created_at = :ts WHERE id = :id"),
            {"ts": one_day_ago, "id": recent_memory_id},
        )
        await session.commit()

    # Recall with default 30-day decay (too aggressive)
    result_default = await nm.recall(user_id=user_id, query="工作", limit=10)

    # Recall with 1-year decay (more appropriate for LoCoMo)
    result_long = await nm.recall(
        user_id=user_id,
        query="工作",
        limit=10,
        decay_rate=86400 * 365,  # 365 days
    )

    # With default decay, 6-month-old memory should have very low recency bonus
    default_scores = {r["id"]: r for r in result_default["vector_results"]}
    if old_memory_id in default_scores:
        assert default_scores[old_memory_id]["recency"] < 0.01  # Nearly decayed

    # With 1-year decay, 6-month-old memory should still have meaningful recency bonus
    long_scores = {r["id"]: r for r in result_long["vector_results"]}
    assert old_memory_id in long_scores
    # 0.15 × e^(-180/365) ≈ 0.15 × 0.61 ≈ 0.092
    assert long_scores[old_memory_id]["recency"] > 0.05

    await nm.close()


@pytest.mark.asyncio
async def test_relative_time_expressions_in_episodes(mock_embedding):
    """Test handling of relative time expressions (yesterday, last week, next month)."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
        auto_extract=False,
    )
    await nm.init()

    user_id = "temporal_user_4"

    # Conversation with various relative time expressions
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="明天下午 3 点有面试",
    )

    messages = await nm.conversations.get_unextracted_messages(user_id)
    await nm._extract_memories(user_id, messages)

    # Verify relative time is preserved (not converted yet)
    from sqlalchemy import text
    async with nm._db.session() as session:
        result = await session.execute(
            text("SELECT content, metadata FROM memories WHERE user_id = :uid AND content LIKE '%面试%'"),
            {"uid": user_id},
        )
        row = result.fetchone()

    assert row is not None
    meta = row.metadata
    assert "timestamp" in meta
    # Relative time should be preserved as-is for now
    assert "tomorrow" in meta["timestamp"] or "3pm" in meta["timestamp"]

    await nm.close()


@pytest.mark.asyncio
async def test_temporal_context_in_recall(mock_embedding):
    """Test that temporal context is included in recall results.

    This supports LoCoMo scenarios where temporal ordering matters.
    """
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
    )
    await nm.init()

    user_id = "temporal_user_5"

    # Add memories with temporal sequence
    await nm._add_memory(
        user_id=user_id,
        content="2020 年在微软实习",
        memory_type="episodic",
        metadata={"importance": 7},
    )
    await nm._add_memory(
        user_id=user_id,
        content="2022 年入职 Google",
        memory_type="episodic",
        metadata={"importance": 8},
    )
    await nm._add_memory(
        user_id=user_id,
        content="2024 年晋升为 Senior Engineer",
        memory_type="episodic",
        metadata={"importance": 9},
    )

    # Recall work history
    result = await nm.recall(user_id=user_id, query="工作经历", limit=10)

    # All memories should be recalled
    assert len(result["merged"]) == 3

    # Verify temporal information is preserved in content
    contents = [m["content"] for m in result["merged"]]
    assert any("2020" in c for c in contents)
    assert any("2022" in c for c in contents)
    assert any("2024" in c for c in contents)

    await nm.close()


@pytest.mark.asyncio
async def test_multi_month_conversation_recall(mock_embedding):
    """Simulate LoCoMo scenario: multi-month conversation history with temporal queries.

    This is the core LoCoMo use case that revealed decay issues.
    """
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockTemporalLLM(),
    )
    await nm.init()

    user_id = "locomo_user"

    # Simulate 6-month conversation history
    memories = [
        ("6 个月前开始学习 Python", 180),
        ("5 个月前完成了第一个项目", 150),
        ("3 个月前面试了 Google", 90),
        ("2 个月前入职 Google", 60),
        ("1 个月前开始做后端开发", 30),
        ("上周参加了代码审查", 7),
        ("昨天修复了一个 bug", 1),
    ]

    memory_ids = []
    for content, days_ago in memories:
        mem = await nm._add_memory(
            user_id=user_id,
            content=content,
            memory_type="episodic",
            metadata={"importance": 7},
        )
        memory_ids.append((str(mem.id), days_ago))  # Convert to string

    # Update timestamps
    from sqlalchemy import text
    async with nm._db.session() as session:
        for mem_id, days_ago in memory_ids:
            ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
            await session.execute(
                text("UPDATE memories SET created_at = :ts WHERE id = :id"),
                {"ts": ts, "id": mem_id},
            )
        await session.commit()

    # Query: "用户的学习和工作经历"
    # With long decay rate (suitable for LoCoMo)
    result = await nm.recall(
        user_id=user_id,
        query="学习和工作经历",
        limit=10,
        decay_rate=86400 * 180,  # 6 months
    )

    # Should recall most/all memories despite age
    assert len(result["merged"]) >= 5  # At least 5 out of 7

    # Verify oldest memory (6 months) is still present
    contents = [m["content"] for m in result["merged"]]
    assert any("Python" in c for c in contents)

    await nm.close()
