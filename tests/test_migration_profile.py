"""Tests for the profile unification data migration script.

Covers:
  - S4: KV profile -> fact/trait, emotion macro -> trait, watermark -> reflection_cycles
  - Dry-run, rollback, idempotency
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from neuromem import NeuroMemory
from neuromem.providers.llm import LLMProvider
from neuromem.services.kv import KVService
from neuromem.services.search import SearchService

TEST_DATABASE_URL = "postgresql+asyncpg://neuromem:neuromem@localhost:5436/neuromem"


class MockLLMProvider(LLMProvider):
    async def chat(self, messages, temperature=0.1, max_tokens=2048) -> str:
        return '{"facts": [], "episodes": [], "triples": []}'


# ---------------------------------------------------------------------------
# Helpers for seeding legacy data
# ---------------------------------------------------------------------------

async def _seed_kv_profile(db_session, user_id: str, data: dict):
    """Seed KV profile namespace with legacy data."""
    kv_svc = KVService(db_session)
    for key, value in data.items():
        await kv_svc.set("profile", user_id, key, value)
    await db_session.commit()


async def _seed_emotion_profile(db_session, user_id: str,
                                 latest_state: str = "stressed",
                                 dominant_emotions: dict | None = None,
                                 emotion_triggers: dict | None = None,
                                 last_reflected_at: datetime | None = None):
    """Insert legacy emotion_profiles row."""
    await db_session.execute(
        text("""
            INSERT INTO emotion_profiles
                (user_id, latest_state, latest_state_valence,
                 dominant_emotions, emotion_triggers, last_reflected_at)
            VALUES
                (:uid, :state, :val, CAST(:dom AS jsonb), CAST(:trig AS jsonb), :wm)
            ON CONFLICT (user_id) DO UPDATE SET
                latest_state = EXCLUDED.latest_state,
                dominant_emotions = EXCLUDED.dominant_emotions,
                emotion_triggers = EXCLUDED.emotion_triggers,
                last_reflected_at = EXCLUDED.last_reflected_at
        """),
        {
            "uid": user_id,
            "state": latest_state,
            "val": -0.5,
            "dom": '{}' if dominant_emotions is None else str(dominant_emotions).replace("'", '"'),
            "trig": '{}' if emotion_triggers is None else str(emotion_triggers).replace("'", '"'),
            "wm": last_reflected_at,
        },
    )
    await db_session.commit()


# ===========================================================================
# S4: Data Migration Tests
# ===========================================================================


class TestMigrationKVToFact:
    """Test migration of KV profile data to fact memories."""

    @pytest.mark.asyncio
    async def test_migrate_kv_identity_to_fact(self, db_session, mock_embedding):
        """TC-4.1: KV identity migrates to fact with category=identity."""
        user = "migrate_user_1"
        await _seed_kv_profile(db_session, user, {"identity": "张三"})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        # Verify fact created
        rows = await db_session.execute(
            text("SELECT content, metadata FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'fact' "
                 "AND metadata->>'category' = 'identity'"),
            {"uid": user},
        )
        facts = rows.fetchall()
        assert len(facts) >= 1
        assert "张三" in facts[0].content
        assert (facts[0].metadata or {}).get("source") == "migration"

    @pytest.mark.asyncio
    async def test_migrate_kv_occupation_to_fact(self, db_session, mock_embedding):
        """TC-4.2: KV occupation migrates to fact with category=work."""
        user = "migrate_user_2"
        await _seed_kv_profile(db_session, user, {"occupation": "Google 工程师"})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, metadata FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'fact' "
                 "AND metadata->>'category' = 'work'"),
            {"uid": user},
        )
        facts = rows.fetchall()
        assert len(facts) >= 1
        assert "Google" in facts[0].content

    @pytest.mark.asyncio
    async def test_migrate_kv_preferences_to_trait(self, db_session, mock_embedding):
        """TC-4.3: KV preferences migrate to behavior traits at trend stage."""
        user = "migrate_user_3"
        await _seed_kv_profile(db_session, user, {
            "preferences": ["喜欢蓝色", "爱吃火锅"],
        })

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, trait_subtype, trait_stage, trait_confidence, metadata "
                 "FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        traits = rows.fetchall()
        assert len(traits) >= 2

        for trait in traits:
            assert trait.trait_subtype == "behavior"
            assert trait.trait_stage == "trend"
            assert trait.trait_confidence == pytest.approx(0.2, abs=0.01)

    @pytest.mark.asyncio
    async def test_migrate_kv_interests_to_trait(self, db_session, mock_embedding):
        """TC-4.4: KV interests migrate to behavior traits."""
        user = "migrate_user_4"
        await _seed_kv_profile(db_session, user, {"interests": ["摄影", "徒步"]})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, trait_subtype, trait_stage "
                 "FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait'"),
            {"uid": user},
        )
        traits = rows.fetchall()
        assert len(traits) >= 2

    @pytest.mark.asyncio
    async def test_migrate_kv_values_to_trait(self, db_session, mock_embedding):
        """TC-4.5: KV values migrate to behavior traits with context=personal."""
        user = "migrate_user_5"
        await _seed_kv_profile(db_session, user, {"values": ["追求效率", "重视家庭"]})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, trait_context "
                 "FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait'"),
            {"uid": user},
        )
        traits = rows.fetchall()
        assert len(traits) >= 2
        for trait in traits:
            assert trait.trait_context == "personal"


class TestMigrationEmotionToTrait:
    """Test migration of emotion_profiles data to traits."""

    @pytest.mark.asyncio
    async def test_migrate_emotion_dominant_to_trait(self, db_session, mock_embedding):
        """TC-4.7: emotion dominant_emotions migrate to traits."""
        user = "migrate_emo_1"
        await _seed_emotion_profile(db_session, user,
                                     dominant_emotions={"焦虑": 0.6, "兴奋": 0.3})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, trait_stage, metadata "
                 "FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        traits = rows.fetchall()
        assert len(traits) >= 1

    @pytest.mark.asyncio
    async def test_migrate_emotion_triggers_to_trait(self, db_session, mock_embedding):
        """TC-4.8: emotion_triggers migrate to traits with context."""
        user = "migrate_emo_2"
        await _seed_emotion_profile(db_session, user,
                                     emotion_triggers={"工作": {"valence": -0.6}})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content, trait_context "
                 "FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        traits = rows.fetchall()
        assert len(traits) >= 1


class TestMigrationWatermark:
    """Test migration of watermark to reflection_cycles."""

    @pytest.mark.asyncio
    async def test_migrate_watermark_to_reflection_cycles(self, db_session, mock_embedding):
        """TC-4.9: last_reflected_at migrates to reflection_cycles."""
        user = "migrate_wm_1"
        wm_time = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_emotion_profile(db_session, user, last_reflected_at=wm_time)

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT trigger_type, completed_at, status "
                 "FROM reflection_cycles "
                 "WHERE user_id = :uid"),
            {"uid": user},
        )
        cycles = rows.fetchall()
        migration_cycles = [c for c in cycles if c.trigger_type == "migration"]
        assert len(migration_cycles) >= 1
        assert migration_cycles[0].status == "completed"
        assert migration_cycles[0].completed_at is not None


class TestMigrationEdgeCases:
    """Test migration edge cases: empty values, dry-run, rollback, idempotency."""

    @pytest.mark.asyncio
    async def test_migrate_empty_values_skip(self, db_session, mock_embedding):
        """TC-4.10: Empty/null values are not migrated."""
        user = "migrate_empty_1"
        kv_svc = KVService(db_session)
        # Set identity to None/empty
        await kv_svc.set("profile", user, "identity", None)
        await db_session.commit()

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        rows = await db_session.execute(
            text("SELECT content FROM memories "
                 "WHERE user_id = :uid AND metadata->>'category' = 'identity'"),
            {"uid": user},
        )
        facts = rows.fetchall()
        assert len(facts) == 0

    @pytest.mark.asyncio
    async def test_migrate_dry_run(self, db_session, mock_embedding):
        """TC-4.11: Dry-run does not write to database."""
        user = "migrate_dry_1"
        await _seed_kv_profile(db_session, user, {"identity": "张三", "occupation": "工程师"})

        from scripts.migrate_profile_unification import _migrate_user

        # Simulate dry-run: execute migration in a savepoint, then rollback
        savepoint = await db_session.begin_nested()
        result = await _migrate_user(db_session, user, mock_embedding)
        await savepoint.rollback()

        # Migration function should return stats
        assert result is not None
        assert result["facts"] >= 1

        # Verify no data was actually written (savepoint rolled back)
        rows = await db_session.execute(
            text("SELECT content FROM memories "
                 "WHERE user_id = :uid AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        assert len(rows.fetchall()) == 0

    @pytest.mark.asyncio
    async def test_migrate_idempotent(self, db_session, mock_embedding):
        """TC-4.13: Running migration twice does not produce duplicate data."""
        user = "migrate_idem_1"
        await _seed_kv_profile(db_session, user, {"identity": "张三"})

        from scripts.migrate_profile_unification import _migrate_user

        # Run twice
        await _migrate_user(db_session, user, mock_embedding)
        await _migrate_user(db_session, user, mock_embedding)

        # Should not have duplicates
        rows = await db_session.execute(
            text("SELECT content FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'fact' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        facts = rows.fetchall()
        # Should only have 1 identity fact, not 2
        identity_count = len([f for f in facts if "张三" in f.content])
        assert identity_count == 1


class TestMigrationEndToEnd:
    """End-to-end migration test with profile_view verification."""

    @pytest.mark.asyncio
    async def test_migration_full_pipeline(self, db_session, mock_embedding):
        """TC-4.14: Complete migration with all data types verified."""
        user = "migrate_e2e_1"

        # Seed KV profile
        await _seed_kv_profile(db_session, user, {
            "identity": "张三",
            "occupation": "软件工程师",
            "interests": ["摄影", "徒步"],
            "preferences": ["喜欢蓝色"],
        })

        # Seed emotion profile
        wm_time = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        await _seed_emotion_profile(
            db_session, user,
            dominant_emotions={"焦虑": 0.6},
            emotion_triggers={"工作": {"valence": -0.5}},
            last_reflected_at=wm_time,
        )

        # Run migration
        from scripts.migrate_profile_unification import _migrate_user

        result = await _migrate_user(db_session, user, mock_embedding)

        # Verify stats
        assert result["facts"] >= 2  # identity + occupation
        assert result["traits"] >= 3  # interests + preferences + emotion
        assert result["watermarks"] >= 1

        # Verify facts created with correct categories
        facts_rows = await db_session.execute(
            text("SELECT content, metadata->>'category' as category FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'fact' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        facts = facts_rows.fetchall()
        categories = {f.category for f in facts}
        assert "identity" in categories
        assert "work" in categories
        identity_facts = [f for f in facts if f.category == "identity"]
        assert any("张三" in f.content for f in identity_facts)

        # Verify traits created
        traits_rows = await db_session.execute(
            text("SELECT content, trait_subtype, trait_stage FROM memories "
                 "WHERE user_id = :uid AND memory_type = 'trait' "
                 "AND metadata->>'source' = 'migration'"),
            {"uid": user},
        )
        traits = traits_rows.fetchall()
        assert len(traits) >= 3

        # Verify watermark migrated to reflection_cycles
        rc_rows = await db_session.execute(
            text("SELECT completed_at, status FROM reflection_cycles "
                 "WHERE user_id = :uid AND trigger_type = 'migration'"),
            {"uid": user},
        )
        cycle = rc_rows.fetchone()
        assert cycle is not None
        assert cycle.status == "completed"

        # Verify KV cleanup
        kv_svc = KVService(db_session)
        items = await kv_svc.list("profile", user)
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_migration_kv_cleanup(self, db_session, mock_embedding):
        """TC-4.15: After migration, KV profile namespace is cleaned up."""
        user = "migrate_cleanup_1"
        await _seed_kv_profile(db_session, user, {"identity": "张三", "occupation": "工程师"})

        from scripts.migrate_profile_unification import _migrate_user

        await _migrate_user(db_session, user, mock_embedding)

        # Verify KV profile namespace is empty
        kv_svc = KVService(db_session)
        items = await kv_svc.list("profile", user)
        assert len(items) == 0
