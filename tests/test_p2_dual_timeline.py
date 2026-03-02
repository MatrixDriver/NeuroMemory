"""Tests for P2-3 Dual Timeline — event_time extraction and storage for facts."""

import pytest
from sqlalchemy import select

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService


class MockLLMWithEventTime(LLMProvider):
    """Mock LLM that returns a fact with event_time."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '''```json
{
  "facts": [
    {
      "content": "User joined Google",
      "category": "work",
      "temporality": "historical",
      "confidence": 0.95,
      "event_time": "2026-02-25"
    }
  ],
  "episodes": [],
  "relations": []
}
```'''


class MockLLMWithoutEventTime(LLMProvider):
    """Mock LLM that returns a fact without event_time."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '''```json
{
  "facts": [
    {
      "content": "User likes Python programming",
      "category": "skill",
      "temporality": "current",
      "confidence": 0.90
    }
  ],
  "episodes": [],
  "relations": []
}
```'''


@pytest.mark.asyncio
async def test_fact_event_time_stored_in_metadata(db_session, mock_embedding):
    """When LLM returns a fact with event_time, it should be stored in metadata_."""
    # Add conversation messages
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "I joined Google on February 25th"},
            {"role": "assistant", "content": "That's great!"},
        ],
    )

    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    mock_llm = MockLLMWithEventTime()
    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="test_user",
        messages=messages,
    )

    assert result["facts_extracted"] == 1

    # Query the stored fact from DB
    rows = (
        await db_session.execute(
            select(Memory).where(
                Memory.user_id == "test_user",
                Memory.memory_type == "fact",
            )
        )
    ).scalars().all()

    assert len(rows) == 1
    fact = rows[0]
    assert fact.metadata_.get("event_time") == "2026-02-25"


@pytest.mark.asyncio
async def test_fact_without_event_time_has_no_event_time_key(db_session, mock_embedding):
    """When LLM returns a fact without event_time, metadata_ should not contain event_time."""
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "I really enjoy Python programming"},
            {"role": "assistant", "content": "Python is a great language!"},
        ],
    )

    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    mock_llm = MockLLMWithoutEventTime()
    extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
    result = await extraction_svc.extract_from_messages(
        user_id="test_user",
        messages=messages,
    )

    assert result["facts_extracted"] == 1

    rows = (
        await db_session.execute(
            select(Memory).where(
                Memory.user_id == "test_user",
                Memory.memory_type == "fact",
            )
        )
    ).scalars().all()

    assert len(rows) == 1
    fact = rows[0]
    assert "event_time" not in fact.metadata_
