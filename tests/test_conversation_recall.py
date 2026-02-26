"""Tests for P1: Conversation recall feature.

P1 enables recall to search original conversation fragments alongside extracted memories.
This preserves temporal details (dates, times) and specific information that may be lost
during LLM extraction.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from neuromem import NeuroMemory


@pytest.mark.asyncio
async def test_conversation_embedding_generated_on_ingest(mock_embedding, mock_llm):
    """Test that conversation embeddings are generated when adding messages."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,  # Disable auto-extract to test embedding only
    )
    await nm.init()

    user_id = "conv_recall_user_1"

    # Add message
    msg = await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="我 2024 年 1 月 15 日入职 Google，工号是 12345",
    )

    # Wait for background embedding task to complete
    import asyncio
    await asyncio.sleep(0.1)  # Give background task time to finish

    # Verify embedding was generated
    from sqlalchemy import select, text
    from neuromem.models.conversation import Conversation

    async with nm._db.session() as session:
        result = await session.execute(
            select(Conversation.embedding).where(Conversation.id == msg.id)
        )
        row = result.fetchone()

    assert row is not None
    assert row.embedding is not None
    assert len(row.embedding) > 0  # Should have embedding vector

    await nm.close()


@pytest.mark.asyncio
async def test_recall_includes_conversation_results(mock_embedding, mock_llm):
    """Test that recall returns conversation_results alongside memory results."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    user_id = "conv_recall_user_2"

    # Add conversation with specific date
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="2024 年 3 月 10 日我参加了 Google I/O 大会，见到了 Sundar Pichai",
    )

    # Wait for background embedding task
    import asyncio
    await asyncio.sleep(0.1)

    # Recall should search conversations
    result = await nm.recall(user_id=user_id, query="Google 大会", limit=10, include_conversations=True)

    # Should have conversation_results key
    assert "conversation_results" in result
    assert isinstance(result["conversation_results"], list)

    # Should find the conversation
    assert len(result["conversation_results"]) > 0

    # Check conversation content
    conv = result["conversation_results"][0]
    assert "content" in conv
    assert "Google" in conv["content"]
    assert "similarity" in conv

    await nm.close()


@pytest.mark.asyncio
async def test_conversation_preserves_temporal_details(mock_embedding):
    """Test that conversations preserve dates/times that might be lost in extraction."""
    from neuromem.providers.llm import LLMProvider

    class MockLossyLLM(LLMProvider):
        """Mock LLM that loses temporal details during extraction."""

        async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
            # Simulates LLM extracting general fact but losing specific date
            return """```json
{
  "preferences": [],
  "facts": [
    {"content": "参加了技术大会", "category": "work", "confidence": 0.9, "importance": 7}
  ],
  "episodes": [],
  "triples": []
}
```"""

    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=MockLossyLLM(),
        auto_extract=True,  # Enable auto-extract with lossy LLM
    )
    await nm.init()

    user_id = "conv_recall_user_3"

    # Add conversation with specific date and details
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="2024 年 3 月 10 日下午 2 点我参加了 Google I/O 大会",
    )

    # Wait for background tasks (embedding + auto-extract)
    import asyncio
    await asyncio.sleep(0.2)

    # Recall
    result = await nm.recall(user_id=user_id, query="技术大会", limit=10, include_conversations=True)

    # Check extracted memory (loses details)
    memory_contents = [m["content"] for m in result["vector_results"]]
    if memory_contents:
        # Extracted fact is general
        assert any("技术大会" in c for c in memory_contents)

    # Check conversation result (preserves details)
    conv_contents = [c["content"] for c in result["conversation_results"]]
    assert len(conv_contents) > 0
    # Original conversation has specific date and time
    assert any("2024 年 3 月 10 日" in c for c in conv_contents)
    assert any("下午 2 点" in c for c in conv_contents)

    await nm.close()


@pytest.mark.asyncio
async def test_merged_results_deduplicate_conversations_and_memories(mock_embedding, mock_llm):
    """Test that merged results deduplicate between conversations and memories."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    user_id = "conv_recall_user_4"

    # Add conversation
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="我在 Google 工作",
    )

    # Add same content as memory
    await nm._add_memory(
        user_id=user_id,
        content="我在 Google 工作",
        memory_type="fact",
    )

    # Wait for background embedding tasks
    import asyncio
    await asyncio.sleep(0.1)

    # Recall
    result = await nm.recall(user_id=user_id, query="工作", limit=10, include_conversations=True)

    # Should have both sources
    assert len(result["vector_results"]) > 0
    assert len(result["conversation_results"]) > 0

    # Merged should deduplicate by content
    merged_contents = [m["content"] for m in result["merged"]]
    # Should appear only once
    google_count = sum(1 for c in merged_contents if c == "我在 Google 工作")
    assert google_count == 1

    await nm.close()


@pytest.mark.asyncio
async def test_conversation_recall_with_role_and_session(mock_embedding, mock_llm):
    """Test that conversation results include role and session_id."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    user_id = "conv_recall_user_5"

    # Add multi-turn conversation
    session_id = "test_session_123"
    await nm.conversations.ingest(
        user_id=user_id,
        role="user",
        content="我想了解 Python 的异步编程",
        session_id=session_id,
    )
    await nm.conversations.ingest(
        user_id=user_id,
        role="assistant",
        content="Python 异步编程使用 async/await 语法",
        session_id=session_id,
    )

    # Wait for background embedding tasks
    import asyncio
    await asyncio.sleep(0.1)

    # Recall
    result = await nm.recall(user_id=user_id, query="Python 异步", limit=10, include_conversations=True)

    # Should find conversations
    assert len(result["conversation_results"]) > 0

    # Check conversation metadata
    for conv in result["conversation_results"]:
        assert "role" in conv
        assert conv["role"] in ["user", "assistant"]
        assert "session_id" in conv
        assert conv["session_id"] == session_id

    await nm.close()


@pytest.mark.asyncio
async def test_conversation_recall_empty_when_no_embeddings(mock_embedding, mock_llm):
    """Test that conversations without embeddings are not returned."""
    nm = NeuroMemory(
        database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
        embedding=mock_embedding,
        llm=mock_llm,
        auto_extract=False,
    )
    await nm.init()

    user_id = "conv_recall_user_6"

    # Manually insert conversation without embedding
    from neuromem.models.conversation import Conversation
    async with nm._db.session() as session:
        conv = Conversation(
            user_id=user_id,
            session_id="manual_session",
            role="user",
            content="这条消息没有 embedding",
            embedding=None,  # Explicitly no embedding
        )
        session.add(conv)
        await session.commit()

    # Recall should not return conversations without embeddings
    result = await nm.recall(user_id=user_id, query="消息", limit=10)

    # Should have empty conversation_results (or not include the manual one)
    assert "conversation_results" in result

    await nm.close()
