"""Tests for recall() emotion injection: EmotionProfile + per-memory emotion labels."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


class MockLLMProvider(LLMProvider):
    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return "{}"


# ---------------------------------------------------------------------------
# Emotion Profile injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_no_emotion_profile_in_merged(mock_embedding):
    """EmotionProfile is NOT injected into merged results (disabled)."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_1"

        await nm._add_memory(user, "I work at Google", memory_type="fact")

        # Insert emotion profile directly
        async with nm._db.session() as session:
            await session.execute(
                text("""
                    INSERT INTO emotion_profiles (user_id, latest_state, latest_state_valence)
                    VALUES (:uid, :state, :val)
                    ON CONFLICT (user_id) DO UPDATE
                        SET latest_state = EXCLUDED.latest_state,
                            latest_state_valence = EXCLUDED.latest_state_valence
                """),
                {"uid": user, "state": "Recently feeling stressed about work", "val": -0.5},
            )
            await session.commit()

        result = await nm.recall(user, "How is the user feeling?", limit=10)
        merged = result["merged"]

        # No emotion_profile source in results (injection disabled)
        ep_items = [m for m in merged if m.get("source") == "emotion_profile"]
        assert len(ep_items) == 0
    finally:
        await nm.close()


# ---------------------------------------------------------------------------
# Per-memory emotion labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_surfaces_emotion_label(mock_embedding):
    """Memories with emotion metadata get [sentiment: label] prefix."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_3"
        await nm._add_memory(
            user, "Got promoted at work today",
            memory_type="episodic",
            metadata={"emotion": {"label": "excited", "valence": 0.8, "arousal": 0.9}},
        )

        result = await nm.recall(user, "work promotion", limit=10)
        merged = result["merged"]

        # Find the memory (skip emotion_profile if present)
        memory_items = [m for m in merged if m.get("source") == "vector"]
        assert len(memory_items) >= 1
        assert "sentiment: excited" in memory_items[0].get("display_content", memory_items[0]["content"])
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_recall_valence_fallback(mock_embedding):
    """When label is missing but valence exists, use positive/negative/neutral."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_4"
        await nm._add_memory(
            user, "Had a terrible meeting",
            memory_type="episodic",
            metadata={"emotion": {"valence": -0.8, "arousal": 0.5}},
        )

        result = await nm.recall(user, "meeting", limit=10)
        merged = result["merged"]

        memory_items = [m for m in merged if m.get("source") == "vector"]
        assert len(memory_items) >= 1
        assert "sentiment: negative" in memory_items[0].get("display_content", memory_items[0]["content"])
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_recall_neutral_valence(mock_embedding):
    """Valence near zero shows 'neutral'."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_5"
        await nm._add_memory(
            user, "Attended a routine standup",
            memory_type="episodic",
            metadata={"emotion": {"valence": 0.1, "arousal": 0.2}},
        )

        result = await nm.recall(user, "standup", limit=10)
        merged = result["merged"]

        memory_items = [m for m in merged if m.get("source") == "vector"]
        assert len(memory_items) >= 1
        assert "sentiment: neutral" in memory_items[0].get("display_content", memory_items[0]["content"])
    finally:
        await nm.close()


@pytest.mark.asyncio
async def test_recall_no_emotion_metadata(mock_embedding):
    """Memories without emotion metadata have no sentiment prefix."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_6"
        await nm._add_memory(user, "Lives in Beijing", memory_type="fact")

        result = await nm.recall(user, "location", limit=10)
        merged = result["merged"]

        memory_items = [m for m in merged if m.get("source") == "vector"]
        assert len(memory_items) >= 1
        assert "sentiment:" not in memory_items[0].get("display_content", memory_items[0]["content"])
    finally:
        await nm.close()


# ---------------------------------------------------------------------------
# extracted_timestamp in recall
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_surfaces_extracted_timestamp(mock_embedding):
    """Memories with extracted_timestamp get [YYYY-MM-DD] prefix."""
    nm = NeuroMemory(
        database_url=TEST_DATABASE_URL,
        embedding=mock_embedding,
        llm=MockLLMProvider(),
        auto_extract=False,
    )
    await nm.init()

    try:
        user = "recall_emotion_7"
        record = await nm._add_memory(user, "Birthday party on the rooftop", memory_type="episodic")

        # Manually set extracted_timestamp (use timezone-aware timestamp)
        async with nm._db.session() as session:
            await session.execute(
                text("UPDATE memories SET extracted_timestamp = '2023-05-07 00:00:00+00' WHERE id = :id"),
                {"id": str(record.id)},
            )
            await session.commit()

        result = await nm.recall(user, "birthday party", limit=10)
        merged = result["merged"]

        memory_items = [m for m in merged if m.get("source") == "vector"]
        assert len(memory_items) >= 1
        # The date prefix should contain "2023-05" (exact day may shift by timezone)
        assert "2023-05" in memory_items[0].get("display_content", memory_items[0]["content"])
        assert "Birthday party" in memory_items[0].get("display_content", memory_items[0]["content"])
    finally:
        await nm.close()
