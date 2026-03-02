"""Tests for P2-4 Procedural Memory — extract workflow steps in facts."""

import pytest
from sqlalchemy import select

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.conversation import ConversationService
from neuromem.services.memory_extraction import MemoryExtractionService


class MockLLMWithWorkflow(LLMProvider):
    """Mock LLM that returns a workflow fact with procedure_steps."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '''```json
{
  "facts": [
    {
      "content": "User deploys code using a 3-step process",
      "category": "workflow",
      "temporality": "current",
      "confidence": 0.90,
      "importance": 6,
      "procedure_steps": ["Run tests locally", "Create pull request", "Merge and deploy"]
    }
  ],
  "episodes": []
}
```'''


class MockLLMWithNormalFact(LLMProvider):
    """Mock LLM that returns a normal fact without procedure_steps."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '''```json
{
  "facts": [
    {
      "content": "User is a backend developer",
      "category": "work",
      "temporality": "current",
      "confidence": 0.95,
      "importance": 7
    }
  ],
  "episodes": []
}
```'''


@pytest.mark.asyncio
async def test_workflow_fact_has_procedure_steps(db_session, mock_embedding):
    """When LLM returns a workflow fact with procedure_steps, they should be stored in metadata_."""
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "When I deploy code, I first run tests, then create a PR, then merge and deploy"},
            {"role": "assistant", "content": "That sounds like a solid workflow!"},
        ],
    )

    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    mock_llm = MockLLMWithWorkflow()
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
    assert fact.metadata_.get("category") == "workflow"
    assert fact.metadata_.get("procedure_steps") == [
        "Run tests locally",
        "Create pull request",
        "Merge and deploy",
    ]


@pytest.mark.asyncio
async def test_non_workflow_fact_has_no_procedure_steps(db_session, mock_embedding):
    """A normal fact without procedure_steps should not have procedure_steps in metadata_."""
    conv_svc = ConversationService(db_session)
    _, msg_ids = await conv_svc.add_messages_batch(
        user_id="test_user",
        messages=[
            {"role": "user", "content": "I work as a backend developer"},
            {"role": "assistant", "content": "Great!"},
        ],
    )

    messages = await conv_svc.get_unextracted_messages(user_id="test_user")

    mock_llm = MockLLMWithNormalFact()
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
    assert "procedure_steps" not in fact.metadata_
