"""Tests for profile_view() S1 enhancement: new trait metadata fields.

Covers test spec module A (TC-A01 ~ TC-A06):
  - TC-A01: trait returns 4 new fields with correct values
  - TC-A02: new field types correct
  - TC-A03: missing metadata defaults
  - TC-A04: existing fields unchanged
  - TC-A05: sort order and limit unchanged
  - TC-A06: empty user structure unchanged

Also covers module C (TC-C03): profile_view displays correct context values.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider
from neuromem.services.search import SearchService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


class MockLLM(LLMProvider):
    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '{"facts": [], "episodes": [], "triples": []}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_trait_with_metadata(
    db_session, mock_embedding, *,
    user_id: str, content: str,
    stage: str = "emerging", subtype: str = "behavior",
    confidence: float = 0.5, context: str = "work",
    reinforcement_count: int = 0, contradiction_count: int = 0,
    first_observed: str | None = None,
    last_reinforced: str | None = None,
) -> str:
    """Insert a trait with full metadata including new S1 fields. Return id."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="trait",
        metadata={"importance": 7},
    )
    await db_session.commit()

    sql = """
        UPDATE memories
        SET trait_stage = :stage,
            trait_subtype = :subtype,
            trait_confidence = :conf,
            trait_context = :ctx,
            trait_reinforcement_count = :rc,
            trait_contradiction_count = :cc
    """
    params: dict = {
        "mid": str(record.id),
        "stage": stage,
        "subtype": subtype,
        "conf": confidence,
        "ctx": context,
        "rc": reinforcement_count,
        "cc": contradiction_count,
    }

    if first_observed:
        sql += ", trait_first_observed = :fo"
        params["fo"] = datetime.fromisoformat(first_observed) if isinstance(first_observed, str) else first_observed
    if last_reinforced:
        sql += ", trait_last_reinforced = :lr"
        params["lr"] = datetime.fromisoformat(last_reinforced) if isinstance(last_reinforced, str) else last_reinforced

    sql += " WHERE id = :mid"

    await db_session.execute(text(sql), params)
    await db_session.commit()
    return str(record.id)


# ===========================================================================
# TC-A01: trait returns 4 new fields with correct values
# ===========================================================================

class TestProfileViewEnhancedFields:

    @pytest.mark.asyncio
    async def test_trait_new_fields_present_and_correct(self, db_session, mock_embedding):
        """TC-A01: profile_view trait includes reinforcement_count, first_observed,
        last_reinforced, contradiction_count with correct values."""
        user = "s1_a01"

        await _insert_trait_with_metadata(
            db_session, mock_embedding,
            user_id=user, content="prefers concise code",
            stage="emerging", subtype="preference", confidence=0.72,
            context="work",
            reinforcement_count=3,
            contradiction_count=1,
            first_observed="2026-02-15T10:00:00+00:00",
            last_reinforced="2026-03-01T14:30:00+00:00",
        )

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            traits = result["traits"]
            assert len(traits) >= 1

            trait = traits[0]
            assert "reinforcement_count" in trait
            assert "first_observed" in trait
            assert "last_reinforced" in trait
            assert "contradiction_count" in trait

            assert trait["reinforcement_count"] == 3
            assert trait["contradiction_count"] == 1
            # ISO 8601 string checks
            assert "2026-02-15" in trait["first_observed"]
            assert "2026-03-01" in trait["last_reinforced"]
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_trait_new_fields_types(self, db_session, mock_embedding):
        """TC-A02: new field types are int / str|None."""
        user = "s1_a02"

        await _insert_trait_with_metadata(
            db_session, mock_embedding,
            user_id=user, content="likes hiking",
            reinforcement_count=5, contradiction_count=2,
            first_observed="2026-01-01T00:00:00+00:00",
            last_reinforced="2026-03-01T00:00:00+00:00",
        )

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            trait = result["traits"][0]

            assert isinstance(trait["reinforcement_count"], int)
            assert isinstance(trait["contradiction_count"], int)
            assert isinstance(trait["first_observed"], str)
            assert isinstance(trait["last_reinforced"], str)
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_trait_missing_metadata_defaults(self, db_session, mock_embedding):
        """TC-A03: missing metadata uses safe defaults (0 / None)."""
        user = "s1_a03"

        # Insert trait WITHOUT setting first_observed / last_reinforced
        svc = SearchService(db_session, mock_embedding)
        record = await svc.add_memory(
            user_id=user, content="legacy trait", memory_type="trait",
            metadata={"importance": 5},
        )
        await db_session.commit()

        await db_session.execute(
            text("""
                UPDATE memories
                SET trait_stage = 'emerging',
                    trait_subtype = 'behavior',
                    trait_confidence = 0.4,
                    trait_context = 'general'
                WHERE id = :mid
            """),
            {"mid": str(record.id)},
        )
        await db_session.commit()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            trait = result["traits"][0]

            assert trait["reinforcement_count"] == 0
            assert trait["contradiction_count"] == 0
            assert trait["first_observed"] is None
            assert trait["last_reinforced"] is None
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_existing_fields_unchanged(self, db_session, mock_embedding):
        """TC-A04: existing 5 fields (content, subtype, stage, confidence, context) unchanged."""
        user = "s1_a04"

        await _insert_trait_with_metadata(
            db_session, mock_embedding,
            user_id=user, content="prefers concise code",
            stage="emerging", subtype="preference",
            confidence=0.72, context="work",
        )

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            trait = result["traits"][0]

            assert trait["content"] == "prefers concise code"
            assert trait["subtype"] == "preference"
            assert trait["stage"] == "emerging"
            assert trait["confidence"] == 0.72
            assert trait["context"] == "work"
            # Also has new fields
            assert "reinforcement_count" in trait
            assert "contradiction_count" in trait
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_trait_sort_and_limit(self, db_session, mock_embedding):
        """TC-A05: traits sorted by confidence DESC, limited to 30."""
        user = "s1_a05"

        for i in range(35):
            await _insert_trait_with_metadata(
                db_session, mock_embedding,
                user_id=user,
                content=f"trait_{i:02d}",
                confidence=round(0.01 * (i + 1), 2),
            )

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            traits = result["traits"]

            assert len(traits) == 30
            # Descending confidence
            confidences = [t["confidence"] for t in traits]
            assert confidences == sorted(confidences, reverse=True)
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_empty_user_structure(self, db_session, mock_embedding):
        """TC-A06: empty user returns {facts: {}, traits: [], recent_mood: null}."""
        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view("nonexistent_s1_a06")

            assert result["facts"] == {}
            assert result["traits"] == []
            assert result["recent_mood"] is None
        finally:
            await nm.close()


# ===========================================================================
# TC-C03: profile_view displays correct context values
# ===========================================================================

class TestProfileViewContext:

    @pytest.mark.asyncio
    async def test_context_values_reflected(self, db_session, mock_embedding):
        """TC-C03: profile_view shows actual context values from database."""
        user = "s3_c03"

        await _insert_trait_with_metadata(
            db_session, mock_embedding,
            user_id=user, content="trait with unspecified ctx",
            context="unspecified", confidence=0.8,
        )
        await _insert_trait_with_metadata(
            db_session, mock_embedding,
            user_id=user, content="trait with work ctx",
            context="work", confidence=0.7,
        )

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding, llm=MockLLM(), auto_extract=False,
        )
        await nm.init()
        try:
            result = await nm.profile_view(user)
            traits = result["traits"]
            contexts = {t["content"]: t["context"] for t in traits}

            assert contexts["trait with unspecified ctx"] == "unspecified"
            assert contexts["trait with work ctx"] == "work"
        finally:
            await nm.close()
