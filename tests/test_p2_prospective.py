"""Tests for P2-5 Prospective Memory — recall penalty for expired + auto-expire in digest."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select, text

from neuromem.models.memory import Memory
from neuromem.providers.llm import LLMProvider
from neuromem.services.search import SearchService
from neuromem.services.reflection import ReflectionService


class MockReflectionLLM(LLMProvider):
    """Mock LLM that returns empty reflection results."""

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '{"new_trends": [], "new_behaviors": [], "reinforcements": [], "contradictions": [], "upgrades": []}'


@pytest.mark.asyncio
async def test_expired_prospective_fact_gets_score_penalty(db_session, mock_embedding):
    """A prospective fact with past event_time should score lower than a current fact."""
    search_svc = SearchService(db_session, mock_embedding)

    # Create a prospective fact with past event_time (should get penalty)
    mem1 = await search_svc.add_memory(
        user_id="test_user",
        content="User plans to attend Python conference",
        memory_type="fact",
        metadata={"temporality": "prospective", "event_time": "2025-01-01", "importance": 5},
    )

    # Create a current fact (no penalty)
    mem2 = await search_svc.add_memory(
        user_id="test_user",
        content="User attends Python meetups regularly",
        memory_type="fact",
        metadata={"temporality": "current", "importance": 5},
    )
    await db_session.commit()

    assert mem1 is not None
    assert mem2 is not None

    results = await search_svc.scored_search(
        user_id="test_user",
        query="Python conference meetup",
        limit=10,
    )

    assert len(results) >= 2

    # Find results by content
    prospective_result = next(r for r in results if "conference" in r["content"])
    current_result = next(r for r in results if "meetups" in r["content"])

    # The prospective fact with past event_time should have lower score
    assert prospective_result["score"] < current_result["score"], (
        f"Prospective score {prospective_result['score']} should be < current score {current_result['score']}"
    )


@pytest.mark.asyncio
async def test_digest_expires_prospective_to_historical(db_session, mock_embedding):
    """Running digest should change expired prospective facts to historical."""
    # Insert a prospective fact with past event_time directly
    now = datetime.now(timezone.utc)
    import hashlib
    content = "User plans to visit Tokyo"
    content_hash = hashlib.md5(content.encode()).hexdigest()
    vector = await mock_embedding.embed(content)

    mem = Memory(
        user_id="test_user",
        content=content,
        embedding=vector,
        memory_type="fact",
        metadata_={"temporality": "prospective", "event_time": "2025-06-01", "importance": 5},
        valid_from=now,
        content_hash=content_hash,
        valid_at=now,
    )
    db_session.add(mem)
    await db_session.commit()

    # Verify it starts as prospective
    rows = (await db_session.execute(
        select(Memory).where(Memory.user_id == "test_user", Memory.memory_type == "fact")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].metadata_["temporality"] == "prospective"

    # Run reflection (force=True to skip trigger checks)
    mock_llm = MockReflectionLLM()
    reflection_svc = ReflectionService(db_session, mock_embedding, mock_llm)
    result = await reflection_svc.reflect(user_id="test_user", force=True)

    assert result["triggered"] is True

    # Refresh the session to see updated data
    db_session.expire_all()

    # Check that temporality was changed to historical
    rows = (await db_session.execute(
        select(Memory).where(Memory.user_id == "test_user", Memory.memory_type == "fact")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].metadata_["temporality"] == "historical", (
        f"Expected 'historical' but got '{rows[0].metadata_['temporality']}'"
    )
