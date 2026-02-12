"""Tests for the reflection service."""

from __future__ import annotations

import pytest

from neuromemory.providers.llm import LLMProvider
from neuromemory.services.reflection import ReflectionService


class MockLLMProvider(LLMProvider):
    """Mock LLM that returns predictable reflection results."""

    def __init__(self, insight_response: str = "", emotion_response: str = ""):
        self._insight_response = insight_response
        self._emotion_response = emotion_response
        self._call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self._call_count += 1
        # First call: insight generation, second call: emotion summary
        if self._call_count == 1:
            return self._insight_response
        else:
            return self._emotion_response


@pytest.mark.asyncio
async def test_reflect_generates_insights(db_session, mock_embedding):
    """Test that reflection generates pattern and summary insights."""
    recent_memories = [
        {"content": "在 Google 工作", "memory_type": "fact", "metadata": {}},
        {"content": "主要做后端开发", "memory_type": "fact", "metadata": {}},
        {"content": "最近项目压力很大", "memory_type": "episodic",
         "metadata": {"emotion": {"valence": -0.6, "arousal": 0.7, "label": "焦虑"}}},
    ]

    mock_llm = MockLLMProvider(
        insight_response="""```json
{
  "insights": [
    {
      "content": "用户是一名后端工程师，近期工作压力较大",
      "category": "summary",
      "source_ids": []
    },
    {
      "content": "用户在技术领域工作，可能关注效率和代码质量",
      "category": "pattern",
      "source_ids": []
    }
  ]
}
```""",
        emotion_response="""```json
{
  "latest_state": "近期工作压力大，情绪偏焦虑",
  "dominant_emotions": {"焦虑": 0.7, "压力": 0.3},
  "emotion_triggers": {"工作": {"valence": -0.6}}
}
```""",
    )

    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("reflect_user", recent_memories)

    assert "insights" in result
    assert "emotion_profile" in result
    assert len(result["insights"]) == 2
    assert result["insights"][0]["category"] == "summary"
    assert result["insights"][1]["category"] == "pattern"


@pytest.mark.asyncio
async def test_reflect_with_no_memories(db_session, mock_embedding):
    """Test reflection with empty memories returns empty result."""
    mock_llm = MockLLMProvider()
    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("empty_user", [])
    assert result["insights"] == []
    assert result["emotion_profile"] is None


@pytest.mark.asyncio
async def test_reflect_stores_as_insight_type(db_session, mock_embedding):
    """Test that insights are stored with memory_type='insight'."""
    from sqlalchemy import text

    mock_llm = MockLLMProvider(
        insight_response="""```json
{
  "insights": [
    {
      "content": "用户喜欢编程和技术",
      "category": "pattern",
      "source_ids": []
    }
  ]
}
```""",
        emotion_response="""{}""",
    )

    memories = [{"content": "I love Python", "memory_type": "fact", "metadata": {}}]
    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("store_user", memories)

    assert len(result["insights"]) == 1

    # Verify stored in DB with memory_type='insight'
    rows = await db_session.execute(
        text("SELECT content, memory_type, metadata FROM embeddings WHERE user_id = :uid AND memory_type = 'insight'"),
        {"uid": "store_user"},
    )
    stored = rows.fetchall()
    assert len(stored) == 1
    assert stored[0].memory_type == "insight"
    assert stored[0].metadata["category"] == "pattern"
    assert stored[0].metadata["importance"] == 8


@pytest.mark.asyncio
async def test_reflect_updates_emotion_profile(db_session, mock_embedding):
    """Test that reflection updates emotion_profiles table."""
    import uuid
    from sqlalchemy import text

    mem_id_1 = uuid.uuid4()
    mem_id_2 = uuid.uuid4()

    recent_memories = [
        {
            "id": str(mem_id_1),
            "content": "今天加班到很晚，感觉很累",
            "memory_type": "episodic",
            "metadata": {"emotion": {"valence": -0.5, "arousal": 0.3, "label": "疲惫"}},
        },
        {
            "id": str(mem_id_2),
            "content": "项目延期了，压力很大",
            "memory_type": "episodic",
            "metadata": {"emotion": {"valence": -0.7, "arousal": 0.8, "label": "焦虑"}},
        },
    ]

    mock_llm = MockLLMProvider(
        insight_response="""{"insights": []}""",
        emotion_response="""```json
{
  "latest_state": "近期工作压力大，情绪低落",
  "dominant_emotions": {"焦虑": 0.6, "疲惫": 0.4},
  "emotion_triggers": {"工作": {"valence": -0.6}}
}
```""",
    )

    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("emotion_user", recent_memories)

    assert result["emotion_profile"] is not None
    assert result["emotion_profile"]["latest_state"] == "近期工作压力大，情绪低落"
    assert result["emotion_profile"]["latest_state_valence"] is not None

    # Verify emotion_profiles table
    rows = await db_session.execute(
        text("SELECT user_id, latest_state, latest_state_valence, dominant_emotions FROM emotion_profiles WHERE user_id = :uid"),
        {"uid": "emotion_user"},
    )
    stored = rows.fetchone()
    assert stored is not None
    assert stored.user_id == "emotion_user"
    assert stored.latest_state == "近期工作压力大，情绪低落"
    assert stored.latest_state_valence < 0  # Negative valence
    assert "焦虑" in stored.dominant_emotions


@pytest.mark.asyncio
async def test_reflect_with_no_emotions_skips_profile_update(db_session, mock_embedding):
    """Test that reflection without emotion data skips emotion profile update."""
    recent_memories = [
        {"content": "在 Google 工作", "memory_type": "fact", "metadata": {}},
    ]

    mock_llm = MockLLMProvider(
        insight_response="""{"insights": [{"content": "test", "category": "pattern"}]}""",
    )

    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("no_emotion_user", recent_memories)

    assert result["insights"] is not None
    assert result["emotion_profile"] is None  # No emotion data, no profile update


@pytest.mark.asyncio
async def test_parse_insight_result_handles_invalid_json(db_session, mock_embedding):
    """Test that reflection handles invalid LLM JSON gracefully."""
    mock_llm = MockLLMProvider(
        insight_response="This is not valid JSON",
        emotion_response="{}",
    )

    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect("invalid_user", [{"content": "test", "memory_type": "fact", "metadata": {}}])

    assert result["insights"] == []  # Empty due to parse failure


@pytest.mark.asyncio
async def test_reflect_facade_method(db_session, mock_embedding):
    """Test the NeuroMemory.reflect() facade method."""
    from neuromemory import NeuroMemory
    from neuromemory.services.search import SearchService

    # Create NeuroMemory with LLM
    mock_llm = MockLLMProvider(
        insight_response='{"insights": [{"content": "test insight", "category": "pattern"}]}',
        emotion_response='{"latest_state": "test state", "dominant_emotions": {}, "emotion_triggers": {}}',
    )

    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
        embedding=mock_embedding,
        llm=mock_llm,
    )
    await nm.init()

    # Add some test memories first
    await nm.add_memory(
        user_id="facade_user",
        content="I work at OpenAI on LLMs",
        metadata={"emotion": {"valence": 0.3, "arousal": 0.5, "label": "satisfied"}},
    )
    await nm.add_memory(
        user_id="facade_user",
        content="Yesterday was stressful",
        metadata={"emotion": {"valence": -0.6, "arousal": 0.7, "label": "stressed"}},
    )

    result = await nm.reflect("facade_user", limit=10)

    assert "insights_generated" in result
    assert "insights" in result
    assert "emotion_profile" in result

    await nm.close()
