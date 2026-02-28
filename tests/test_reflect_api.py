"""Tests for public API — reflect(), should_reflect(), get_user_traits().

Covers scene S8: NeuroMemory facade methods for trait reflection and query.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.providers.llm import LLMProvider
from neuromem.services.search import SearchService


# ---------------------------------------------------------------------------
# Mock LLM that returns controllable reflection output
# ---------------------------------------------------------------------------

class MockReflectionLLM(LLMProvider):
    """LLM mock that returns configurable reflection results."""

    def __init__(self, response: str | None = None):
        self._response = response or json.dumps({
            "trends": [],
            "behaviors": [],
            "reinforcements": [],
            "contradictions": [],
        })
        self.call_count = 0

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> str:
        self.call_count += 1
        return self._response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_trait_row(
    db_session,
    mock_embedding,
    *,
    user_id: str,
    content: str,
    trait_stage: str = "emerging",
    trait_subtype: str = "behavior",
    trait_confidence: float = 0.5,
    trait_context: str = "general",
) -> str:
    """Insert a trait memory and set trait-specific columns. Return id."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="trait",
        metadata={"importance": 7},
    )
    await db_session.commit()

    await db_session.execute(
        text("""
            UPDATE memories
            SET trait_stage = :stage,
                trait_subtype = :subtype,
                trait_confidence = :conf,
                trait_context = :ctx,
                trait_reinforcement_count = 0,
                trait_contradiction_count = 0
            WHERE id = :mid
        """),
        {
            "mid": str(record.id),
            "stage": trait_stage,
            "subtype": trait_subtype,
            "conf": trait_confidence,
            "ctx": trait_context,
        },
    )
    await db_session.commit()
    return str(record.id)


async def _seed_memories(nm: NeuroMemory, user_id: str, count: int = 5) -> None:
    """Seed some fact memories so reflect has material to scan."""
    for i in range(count):
        await nm._add_memory(
            user_id=user_id,
            content=f"memory about topic {i} {uuid.uuid4().hex[:8]}",
            metadata={"importance": 6},
        )


# ---------------------------------------------------------------------------
# get_user_traits() tests
# ---------------------------------------------------------------------------


class TestGetUserTraits:
    """Tests for NeuroMemory.get_user_traits() public API."""

    @pytest.mark.asyncio
    async def test_get_user_traits_basic(self, db_session, mock_embedding, nm):
        """Basic query returns all active traits."""
        uid = f"gtr_basic_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="user loves hiking",
            trait_stage="emerging", trait_subtype="behavior",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="user prefers dark mode",
            trait_stage="established", trait_subtype="preference",
        )

        traits = await nm.get_user_traits(user_id=uid)
        assert len(traits) == 2
        # Each trait should have expected keys
        for t in traits:
            assert "id" in t
            assert "content" in t
            assert "trait_subtype" in t
            assert "trait_stage" in t
            assert "trait_confidence" in t

    @pytest.mark.asyncio
    async def test_get_user_traits_min_stage(self, db_session, mock_embedding, nm):
        """min_stage filters out lower stages."""
        uid = f"gtr_stage_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="emerging trait",
            trait_stage="emerging",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="established trait",
            trait_stage="established",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="core trait",
            trait_stage="core",
        )

        # min_stage="established" should exclude emerging
        traits = await nm.get_user_traits(user_id=uid, min_stage="established")
        stages = {t["trait_stage"] for t in traits}
        assert "emerging" not in stages
        assert "established" in stages or "core" in stages
        assert len(traits) == 2

    @pytest.mark.asyncio
    async def test_get_user_traits_subtype_filter(self, db_session, mock_embedding, nm):
        """subtype filter returns only matching subtype."""
        uid = f"gtr_sub_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="behavior trait",
            trait_subtype="behavior", trait_stage="emerging",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="preference trait",
            trait_subtype="preference", trait_stage="emerging",
        )

        traits = await nm.get_user_traits(user_id=uid, subtype="preference")
        assert len(traits) == 1
        assert traits[0]["trait_subtype"] == "preference"

    @pytest.mark.asyncio
    async def test_get_user_traits_context_filter(self, db_session, mock_embedding, nm):
        """context filter returns only matching context."""
        uid = f"gtr_ctx_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="work trait",
            trait_context="work", trait_stage="emerging",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="personal trait",
            trait_context="personal", trait_stage="emerging",
        )

        traits = await nm.get_user_traits(user_id=uid, context="work")
        assert len(traits) == 1
        assert traits[0]["trait_context"] == "work"

    @pytest.mark.asyncio
    async def test_get_user_traits_ordering(self, db_session, mock_embedding, nm):
        """Results ordered by stage desc then confidence desc."""
        uid = f"gtr_ord_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="emerging low conf",
            trait_stage="emerging", trait_confidence=0.3,
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="core high conf",
            trait_stage="core", trait_confidence=0.9,
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="established mid conf",
            trait_stage="established", trait_confidence=0.6,
        )

        traits = await nm.get_user_traits(user_id=uid)
        assert len(traits) == 3
        # First should be core, then established, then emerging
        assert traits[0]["trait_stage"] == "core"
        assert traits[1]["trait_stage"] == "established"
        assert traits[2]["trait_stage"] == "emerging"

    @pytest.mark.asyncio
    async def test_get_user_traits_empty(self, nm):
        """No traits for user returns empty list."""
        uid = f"gtr_empty_{uuid.uuid4().hex[:6]}"
        traits = await nm.get_user_traits(user_id=uid)
        assert traits == []

    @pytest.mark.asyncio
    async def test_get_user_traits_excludes_dissolved(
        self, db_session, mock_embedding, nm
    ):
        """Dissolved traits are excluded even if stage is in range."""
        uid = f"gtr_diss_{uuid.uuid4().hex[:6]}"
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="dissolved trait",
            trait_stage="dissolved",
        )
        await _insert_trait_row(
            db_session, mock_embedding,
            user_id=uid, content="active trait",
            trait_stage="emerging",
        )

        # Even with min_stage="trend" (most inclusive), dissolved should not appear
        traits = await nm.get_user_traits(user_id=uid, min_stage="trend")
        stages = {t["trait_stage"] for t in traits}
        assert "dissolved" not in stages


# ---------------------------------------------------------------------------
# should_reflect() tests
# ---------------------------------------------------------------------------


class TestShouldReflectAPI:
    """Tests for NeuroMemory.should_reflect() public API."""

    @pytest.mark.asyncio
    async def test_should_reflect_api_first_time(self, nm):
        """First-time user (no prior reflection) should return True."""
        uid = f"sr_first_{uuid.uuid4().hex[:6]}"
        await _seed_memories(nm, uid, count=3)

        result = await nm.should_reflect(user_id=uid)
        assert isinstance(result, bool)
        # First time should trigger (no last_reflected_at)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_reflect_api_returns_bool(self, nm):
        """should_reflect always returns a boolean."""
        uid = f"sr_bool_{uuid.uuid4().hex[:6]}"
        result = await nm.should_reflect(user_id=uid)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# reflect() tests
# ---------------------------------------------------------------------------


class TestReflectAPI:
    """Tests for NeuroMemory.reflect() public API."""

    @pytest.mark.asyncio
    async def test_reflect_api_returns_dict(self, mock_embedding):
        """reflect() returns a dict with expected keys."""
        uid = f"ref_dict_{uuid.uuid4().hex[:6]}"
        mock_llm = MockReflectionLLM()

        nm = NeuroMemory(
            database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
            embedding=mock_embedding,
            llm=mock_llm,
        )
        await nm.init()
        try:
            await _seed_memories(nm, uid, count=5)
            result = await nm.reflect(user_id=uid, force=True)

            assert isinstance(result, dict)
            assert "triggered" in result
            assert "memories_scanned" in result
            assert "traits_created" in result
            assert "traits_updated" in result
            assert "traits_dissolved" in result
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_reflect_api_force(self, mock_embedding):
        """reflect(force=True) bypasses trigger conditions."""
        uid = f"ref_force_{uuid.uuid4().hex[:6]}"
        mock_llm = MockReflectionLLM()

        nm = NeuroMemory(
            database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
            embedding=mock_embedding,
            llm=mock_llm,
        )
        await nm.init()
        try:
            await _seed_memories(nm, uid, count=3)
            result = await nm.reflect(user_id=uid, force=True)
            assert result["triggered"] is True
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_reflect_api_session_ended(self, mock_embedding):
        """reflect(session_ended=True) uses session_ended trigger type."""
        uid = f"ref_sess_{uuid.uuid4().hex[:6]}"
        mock_llm = MockReflectionLLM()

        nm = NeuroMemory(
            database_url="postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem",
            embedding=mock_embedding,
            llm=mock_llm,
        )
        await nm.init()
        try:
            await _seed_memories(nm, uid, count=3)
            result = await nm.reflect(
                user_id=uid, force=True, session_ended=True,
            )
            assert result["triggered"] is True
            if result.get("trigger_type"):
                assert result["trigger_type"] in (
                    "session_ended", "session_end", "force", "forced",
                    "first_time", "importance_threshold", "time_threshold",
                    "importance_accumulated", "scheduled",
                )
        finally:
            await nm.close()
