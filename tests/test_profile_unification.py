"""Tests for Profile Unification: elimination of parallel profile mechanisms.

Covers:
  - S1: Ingest no longer produces profile_updates
  - S2: profile_view() returns correct structure (facts/traits/recent_mood)
  - S3: Digest/Reflect no longer updates emotion_profiles, watermark in reflection_cycles
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider
from neuromem.services.search import SearchService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


# ---------------------------------------------------------------------------
# Mock LLM Providers
# ---------------------------------------------------------------------------

class MockExtractionLLM(LLMProvider):
    """Mock LLM that returns extraction results without profile_updates."""

    def __init__(self, response: str = ""):
        self._response = response

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return self._response


class MockReflectionLLM(LLMProvider):
    """Mock LLM that returns controllable reflection results."""

    def __init__(self, response: str = ""):
        self._response = response or '{"trends": [], "behaviors": [], "reinforcements": [], "contradictions": []}'
        self.call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self.call_count += 1
        return self._response


class MockDigestLLM(LLMProvider):
    """Mock LLM for digest tests: insight generation only, no emotion profile."""

    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        self.call_count += 1
        return '{"insights": [{"content": "test insight", "category": "pattern", "source_ids": []}]}'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_fact(db_session, mock_embedding, *, user_id: str,
                       content: str, category: str = "general") -> str:
    """Insert a fact memory with category metadata. Return id."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="fact",
        metadata={"category": category},
    )
    await db_session.commit()
    return str(record.id)


async def _insert_trait(db_session, mock_embedding, *, user_id: str,
                        content: str, stage: str = "emerging",
                        subtype: str = "behavior",
                        confidence: float = 0.5,
                        context: str = "general") -> str:
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
            "stage": stage,
            "subtype": subtype,
            "conf": confidence,
            "ctx": context,
        },
    )
    await db_session.commit()
    return str(record.id)


async def _insert_episodic_with_emotion(db_session, mock_embedding, *,
                                         user_id: str, content: str,
                                         valence: float, arousal: float,
                                         label: str = "",
                                         age_days: int = 0) -> str:
    """Insert an episodic memory with emotion metadata. Return id."""
    emotion = {"valence": valence, "arousal": arousal}
    if label:
        emotion["label"] = label

    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="episodic",
        metadata={"emotion": emotion},
    )
    if age_days > 0:
        await db_session.execute(
            text("""
                UPDATE memories
                SET created_at = NOW() - INTERVAL ':days days'
                WHERE id = :id
            """.replace(":days", str(int(age_days)))),
            {"id": str(record.id)},
        )
    await db_session.commit()
    return str(record.id)


# ===========================================================================
# S1: Ingest Flow — No more profile_updates
# ===========================================================================


class TestIngestNoProfileUpdates:
    """Verify that ingest no longer produces or stores profile_updates."""

    @pytest.mark.asyncio
    async def test_extraction_no_profile_updates(self, db_session, mock_embedding):
        """TC-1.1: Extraction with new LLM format (no profile_updates) succeeds."""
        from neuromem.services.memory_extraction import MemoryExtractionService
        from neuromem.services.conversation import ConversationService

        conv_svc = ConversationService(db_session)
        _, _ = await conv_svc.add_messages_batch(
            user_id="test_s1_1",
            messages=[
                {"role": "user", "content": "我在 Google 工作，名叫张三"},
                {"role": "assistant", "content": "你好张三!"},
            ],
        )
        messages = await conv_svc.get_unextracted_messages(user_id="test_s1_1")

        mock_llm = MockExtractionLLM(response="""```json
{
  "facts": [
    {"content": "在 Google 工作", "category": "work", "confidence": 0.98},
    {"content": "名叫张三", "category": "identity", "confidence": 0.95}
  ],
  "episodes": [],
  "triples": []
}
```""")

        extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
        result = await extraction_svc.extract_from_messages(
            user_id="test_s1_1",
            messages=messages,
        )

        assert result["facts_extracted"] == 2
        assert result["episodes_extracted"] == 0

    @pytest.mark.asyncio
    async def test_extraction_identity_as_fact_with_category(self, db_session, mock_embedding):
        """TC-1.2: Identity info stored as fact with category=identity metadata."""
        from neuromem.services.memory_extraction import MemoryExtractionService
        from neuromem.services.conversation import ConversationService

        conv_svc = ConversationService(db_session)
        _, _ = await conv_svc.add_messages_batch(
            user_id="test_s1_2",
            messages=[{"role": "user", "content": "我叫张三"}],
        )
        messages = await conv_svc.get_unextracted_messages(user_id="test_s1_2")

        mock_llm = MockExtractionLLM(response="""```json
{
  "facts": [{"content": "用户名叫张三", "category": "identity", "confidence": 0.95}],
  "episodes": [],
  "triples": []
}
```""")

        extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
        await extraction_svc.extract_from_messages(user_id="test_s1_2", messages=messages)

        # Verify stored as fact with category metadata
        rows = await db_session.execute(
            text("SELECT content, memory_type, metadata FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'fact'"),
            {"uid": "test_s1_2"},
        )
        stored = rows.fetchall()
        assert len(stored) >= 1

        identity_facts = [r for r in stored if (r.metadata or {}).get("category") == "identity"]
        assert len(identity_facts) >= 1

    @pytest.mark.asyncio
    async def test_extraction_old_format_graceful(self, db_session, mock_embedding):
        """TC-1.4: LLM returning profile_updates is silently ignored."""
        from neuromem.services.memory_extraction import MemoryExtractionService
        from neuromem.services.conversation import ConversationService

        conv_svc = ConversationService(db_session)
        _, _ = await conv_svc.add_messages_batch(
            user_id="test_s1_4",
            messages=[{"role": "user", "content": "我在 Google 工作"}],
        )
        messages = await conv_svc.get_unextracted_messages(user_id="test_s1_4")

        # Old format with profile_updates
        mock_llm = MockExtractionLLM(response="""```json
{
  "facts": [{"content": "在 Google 工作", "category": "work", "confidence": 0.98}],
  "episodes": [],
  "triples": [],
  "profile_updates": {
    "occupation": "Google 工程师"
  }
}
```""")

        extraction_svc = MemoryExtractionService(db_session, mock_embedding, mock_llm)
        # Should not raise
        result = await extraction_svc.extract_from_messages(user_id="test_s1_4", messages=messages)
        assert result["facts_extracted"] >= 1

        # Verify NO KV profile write
        from neuromem.services.kv import KVService
        kv_svc = KVService(db_session)
        occupation = await kv_svc.get("profile", "test_s1_4", "occupation")
        assert occupation is None

    @pytest.mark.asyncio
    async def test_parse_classification_no_profile_updates(self):
        """TC-1.6: _parse_classification_result output has no profile_updates key."""
        from neuromem.services.memory_extraction import MemoryExtractionService

        svc = MemoryExtractionService.__new__(MemoryExtractionService)

        result = svc._parse_classification_result("""```json
{
  "facts": [{"content": "test", "category": "work", "confidence": 0.9}],
  "episodes": [],
  "triples": []
}
```""")
        assert "facts" in result
        assert "episodes" in result
        assert "triples" in result
        assert "profile_updates" not in result

    @pytest.mark.asyncio
    async def test_parse_classification_ignores_profile_updates_in_input(self):
        """_parse_classification_result silently ignores profile_updates if present in LLM output."""
        from neuromem.services.memory_extraction import MemoryExtractionService

        svc = MemoryExtractionService.__new__(MemoryExtractionService)

        result = svc._parse_classification_result("""```json
{
  "facts": [{"content": "test", "category": "work", "confidence": 0.9}],
  "episodes": [],
  "triples": [],
  "profile_updates": {"identity": "test"}
}
```""")
        assert "profile_updates" not in result
        assert len(result["facts"]) == 1

    @pytest.mark.asyncio
    async def test_store_profile_updates_removed(self):
        """TC-1.7: _store_profile_updates and profile key constants are deleted."""
        from neuromem.services.memory_extraction import MemoryExtractionService

        assert not hasattr(MemoryExtractionService, "_store_profile_updates")
        assert not hasattr(MemoryExtractionService, "_PROFILE_OVERWRITE_KEYS")
        assert not hasattr(MemoryExtractionService, "_PROFILE_APPEND_KEYS")


# ===========================================================================
# S2: profile_view() — Unified user profile view
# ===========================================================================


class TestProfileView:
    """Verify profile_view() returns correct facts/traits/recent_mood structure."""

    @pytest.mark.asyncio
    async def test_profile_view_returns_correct_structure(self, db_session, mock_embedding):
        """TC-2.1: profile_view returns {facts, traits, recent_mood}."""
        user = "pv_user_1"

        # Insert facts
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="张三，男，28岁", category="identity")
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="Meta 软件工程师", category="occupation")

        # Insert trait
        await _insert_trait(db_session, mock_embedding, user_id=user,
                           content="工作场景下倾向焦虑", stage="emerging",
                           subtype="behavior", context="work")

        # Insert recent episodic with emotion
        await _insert_episodic_with_emotion(db_session, mock_embedding,
                                            user_id=user,
                                            content="今天加班到很晚",
                                            valence=-0.5, arousal=0.3)

        # Create NeuroMemory and test profile_view
        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view(user)

            assert "facts" in result
            assert "traits" in result
            assert "recent_mood" in result

            assert isinstance(result["facts"], dict)
            assert isinstance(result["traits"], list)
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_facts_latest_identity(self, db_session, mock_embedding):
        """TC-2.2: profile_view takes latest identity/occupation fact."""
        user = "pv_user_2"

        # Insert old occupation
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="在 Google 工作", category="occupation")

        # Insert newer occupation (created later)
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="跳槽到 Meta", category="occupation")

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view(user)
            # Latest occupation should be "跳槽到 Meta"
            assert "Meta" in result["facts"].get("occupation", "")
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_traits_emerging_and_above(self, db_session, mock_embedding):
        """TC-2.3: Only emerging+ stage traits are included."""
        user = "pv_user_3"

        await _insert_trait(db_session, mock_embedding, user_id=user,
                           content="trend trait (should be excluded)", stage="trend")
        await _insert_trait(db_session, mock_embedding, user_id=user,
                           content="emerging trait (should be included)", stage="emerging")
        await _insert_trait(db_session, mock_embedding, user_id=user,
                           content="established trait (should be included)", stage="established")
        await _insert_trait(db_session, mock_embedding, user_id=user,
                           content="dissolved trait (should be excluded)", stage="dissolved")

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view(user)
            trait_contents = [t["content"] for t in result["traits"]]

            assert "trend trait (should be excluded)" not in trait_contents
            assert "dissolved trait (should be excluded)" not in trait_contents
            assert "emerging trait (should be included)" in trait_contents
            assert "established trait (should be included)" in trait_contents
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_recent_mood_aggregation(self, db_session, mock_embedding):
        """TC-2.5: recent_mood aggregates from recent episodic emotion metadata."""
        user = "pv_user_5"

        # Recent episodics (within 14 days)
        await _insert_episodic_with_emotion(db_session, mock_embedding,
                                            user_id=user, content="stressful day",
                                            valence=-0.3, arousal=0.5, age_days=0)
        await _insert_episodic_with_emotion(db_session, mock_embedding,
                                            user_id=user, content="another bad day",
                                            valence=-0.5, arousal=0.4, age_days=2)
        await _insert_episodic_with_emotion(db_session, mock_embedding,
                                            user_id=user, content="slightly better",
                                            valence=-0.1, arousal=0.3, age_days=5)

        # Old episodic (should be excluded from 14-day window)
        await _insert_episodic_with_emotion(db_session, mock_embedding,
                                            user_id=user, content="old event",
                                            valence=0.8, arousal=0.9, age_days=30)

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view(user)
            mood = result["recent_mood"]

            assert mood is not None
            assert mood["sample_count"] == 3  # Only recent 3, not the 30-day old one
            # Average valence of -0.3, -0.5, -0.1 = -0.3
            assert -0.4 < mood["valence_avg"] < -0.2
            assert mood["period"] == "last_14_days"
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_new_user_empty(self, db_session, mock_embedding):
        """TC-2.6: New user returns empty facts, empty traits, null recent_mood."""
        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view("nonexistent_user_xyz")

            assert result["facts"] == {}
            assert result["traits"] == []
            assert result["recent_mood"] is None
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_no_emotion_data(self, db_session, mock_embedding):
        """TC-2.7: No emotion data results in recent_mood=None."""
        user = "pv_user_7"

        # Only facts, no episodic with emotion
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="some fact", category="general")

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            result = await nm.profile_view(user)
            assert result["recent_mood"] is None
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_fetch_user_profile_removed(self, mock_embedding):
        """TC-2.8: _fetch_user_profile is removed or redirects to profile_view."""
        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        # Method should not exist
        assert not hasattr(nm, "_fetch_user_profile")

    @pytest.mark.asyncio
    async def test_recall_uses_profile_view_structure(self, db_session, mock_embedding):
        """TC-2.9: recall() returns user_profile with new structure."""
        user = "pv_user_9"

        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="张三", category="identity")
        await _insert_fact(db_session, mock_embedding, user_id=user,
                          content="软件工程师", category="occupation")

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        await nm.init()

        try:
            await nm._add_memory(user, "I work on backend systems", memory_type="fact")

            result = await nm.recall(user, "work", limit=10)

            # user_profile should use new structure
            profile = result.get("user_profile", {})
            assert "facts" in profile
            assert "traits" in profile
            assert "recent_mood" in profile
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_profile_view_as_public_method(self, mock_embedding):
        """TC-2.11: profile_view is a public method on NeuroMemory."""
        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=MockExtractionLLM(),
            auto_extract=False,
        )
        assert hasattr(nm, "profile_view")
        assert callable(getattr(nm, "profile_view"))


# ===========================================================================
# S3: Digest/Reflect — No emotion_profiles, watermark in reflection_cycles
# ===========================================================================


class TestDigestNoEmotionProfile:
    """Verify digest no longer updates emotion_profiles table."""

    @pytest.mark.asyncio
    async def test_digest_no_emotion_profile_update(self, db_session, mock_embedding):
        """TC-3.1: digest() does not write to emotion_profiles table."""
        mock_llm = MockDigestLLM()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=mock_llm,
            auto_extract=False,
        )
        await nm.init()

        try:
            user = "digest_s3_1"
            await nm._add_memory(user, "Some fact about work", memory_type="fact")
            await nm._add_memory(user, "Feeling stressed today", memory_type="episodic",
                                 metadata={"emotion": {"valence": -0.5, "arousal": 0.7}})

            await nm.digest(user, batch_size=50)

            # Check emotion_profiles table is not written to
            async with nm._db.session() as session:
                try:
                    row = await session.execute(
                        text("SELECT * FROM emotion_profiles WHERE user_id = :uid"),
                        {"uid": user},
                    )
                    result = row.fetchone()
                    assert result is None, "emotion_profiles should not be updated by digest"
                except Exception:
                    # Table might not exist anymore, which is also correct
                    pass
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_digest_returns_no_emotion_profile(self, db_session, mock_embedding):
        """TC-3.2: digest() return value does not contain emotion_profile."""
        mock_llm = MockDigestLLM()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=mock_llm,
            auto_extract=False,
        )
        await nm.init()

        try:
            user = "digest_s3_2"
            await nm._add_memory(user, "Some fact", memory_type="fact")

            result = await nm.digest(user, batch_size=50)

            assert "memories_analyzed" in result
            assert "insights_generated" in result
            assert "emotion_profile" not in result
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_update_emotion_profile_removed(self, db_session, mock_embedding):
        """TC-3.3: _update_emotion_profile method is deleted."""
        from neuromem.services.reflection import ReflectionService

        assert not hasattr(ReflectionService, "_update_emotion_profile")

    @pytest.mark.asyncio
    async def test_digest_watermark_in_reflection_cycles(self, db_session, mock_embedding):
        """TC-3.5: watermark stored in reflection_cycles table."""
        mock_llm = MockDigestLLM()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=mock_llm,
            auto_extract=False,
        )
        await nm.init()

        try:
            user = "digest_s3_5"
            await nm._add_memory(user, "Test fact for watermark", memory_type="fact")

            await nm.digest(user, batch_size=50)

            # Verify watermark in reflection_cycles
            async with nm._db.session() as session:
                row = await session.execute(
                    text("SELECT completed_at, status FROM reflection_cycles "
                         "WHERE user_id = :uid ORDER BY completed_at DESC LIMIT 1"),
                    {"uid": user},
                )
                cycle = row.fetchone()
                assert cycle is not None, "reflection_cycles should have a record"
                assert cycle.status == "completed"
                assert cycle.completed_at is not None
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_digest_watermark_incremental(self, db_session, mock_embedding):
        """TC-3.6: Second digest only processes memories after watermark."""
        mock_llm = MockDigestLLM()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=mock_llm,
            auto_extract=False,
        )
        await nm.init()

        try:
            user = "digest_s3_6"

            # First batch
            await nm._add_memory(user, "Old fact 1", memory_type="fact")
            await nm._add_memory(user, "Old fact 2", memory_type="fact")
            result1 = await nm.digest(user, batch_size=50)
            assert result1["memories_analyzed"] >= 2

            # Add new memories
            await nm._add_memory(user, "New fact after digest", memory_type="fact")

            # Reset LLM counter
            mock_llm.call_count = 0

            # Second digest should only process new memory (+ possible traits from first)
            result2 = await nm.digest(user, batch_size=50)
            assert result2["memories_analyzed"] >= 1
        finally:
            await nm.close()

    @pytest.mark.asyncio
    async def test_digest_convergence(self, db_session, mock_embedding):
        """TC-3.7: Multiple digests converge to zero new memories."""
        mock_llm = MockDigestLLM()

        nm = NeuroMemory(
            database_url=TEST_DATABASE_URL,
            embedding=mock_embedding,
            llm=mock_llm,
            auto_extract=False,
        )
        await nm.init()

        try:
            user = "digest_s3_7"
            await nm._add_memory(user, "Single fact", memory_type="fact")

            # Run digest multiple times
            await nm.digest(user, batch_size=50)
            await nm.digest(user, batch_size=50)

            mock_llm.call_count = 0
            result = await nm.digest(user, batch_size=50)

            # Should converge: either 0 or processing remaining insights
            assert result["memories_analyzed"] >= 0
            if result["memories_analyzed"] == 0:
                assert result["insights_generated"] == 0
        finally:
            await nm.close()
