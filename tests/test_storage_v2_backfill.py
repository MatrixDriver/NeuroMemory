"""Tests for RPIV-1 storage foundation V2: Data backfill.

Covers: JSONB -> dedicated columns, type migration, content_hash, valid_at.
PRD section: 7.4
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Dummy 1024-dim zero vector for raw SQL INSERTs (backfill tests don't need real embeddings)
_ZERO_VEC = "[" + ",".join(["0"] * 1024) + "]"


async def _disable_memory_type_check(conn):
    """Temporarily disable chk_memory_type to allow inserting legacy types."""
    await conn.execute(text(
        "ALTER TABLE memories DROP CONSTRAINT IF EXISTS chk_memory_type"
    ))


async def _enable_memory_type_check(conn):
    """Re-enable chk_memory_type constraint."""
    await conn.execute(text(
        "ALTER TABLE memories ADD CONSTRAINT chk_memory_type "
        "CHECK (memory_type IN ('fact', 'episodic', 'trait', 'document')) NOT VALID"
    ))


async def _insert_v1_memory(conn, *, user_id: str, content: str, memory_type: str,
                            metadata: dict | None = None, embedding=None,
                            content_hash: str | None = None,
                            trait_subtype: str | None = None,
                            valid_from: str | None = None):
    """Insert a V1-style row directly via SQL into the memories table."""
    meta_json = "{}" if metadata is None else str(metadata).replace("'", '"').replace("None", "null")

    # Build column/value lists dynamically
    cols = "id, user_id, content, memory_type, metadata, embedding"
    vals = f"gen_random_uuid(), '{user_id}', '{content}', '{memory_type}', '{meta_json}'::jsonb, '{_ZERO_VEC}'::halfvec"

    if content_hash:
        cols += ", content_hash"
        vals += f", '{content_hash}'"

    if trait_subtype:
        cols += ", trait_subtype"
        vals += f", '{trait_subtype}'"

    if valid_from:
        cols += ", valid_from"
        vals += f", '{valid_from}'::timestamptz"

    await conn.execute(text(f"INSERT INTO memories ({cols}) VALUES ({vals})"))


# ---------------------------------------------------------------------------
# TC-B01: Backfill trait metadata to columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_trait_metadata_to_columns(db_session):
    """TC-B01: Trait metadata values are correctly backfilled to dedicated columns."""
    meta_json = '{"trait_subtype":"preference","trait_stage":"emerging","confidence":0.75,"context":"work","reinforcement_count":3,"contradiction_count":1,"derived_from":"reflection"}'
    await db_session.execute(
        text("INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
             "VALUES (gen_random_uuid(), 'bf_test', 'user prefers Python', 'trait', "
             "CAST(:meta AS jsonb), CAST(:vec AS halfvec))"),
        {"meta": meta_json, "vec": _ZERO_VEC},
    )
    await db_session.flush()

    # Execute backfill SQL
    await db_session.execute(text("""
        UPDATE memories SET
            trait_subtype = metadata->>'trait_subtype',
            trait_stage = COALESCE(trait_stage, metadata->>'trait_stage'),
            trait_confidence = (metadata->>'confidence')::float,
            trait_context = metadata->>'context',
            trait_reinforcement_count = COALESCE((metadata->>'reinforcement_count')::int, 0),
            trait_contradiction_count = COALESCE((metadata->>'contradiction_count')::int, 0),
            trait_derived_from = metadata->>'derived_from'
        WHERE memory_type = 'trait' AND trait_subtype IS NULL
          AND metadata->>'trait_subtype' IS NOT NULL
    """))

    result = await db_session.execute(text(
        "SELECT trait_subtype, trait_stage, trait_confidence, trait_context, "
        "trait_reinforcement_count, trait_contradiction_count, trait_derived_from "
        "FROM memories WHERE user_id = 'bf_test'"
    ))
    row = result.fetchone()

    assert row.trait_subtype == "preference"
    assert row.trait_stage == "emerging"
    assert abs(row.trait_confidence - 0.75) < 1e-6
    assert row.trait_context == "work"
    assert row.trait_reinforcement_count == 3
    assert row.trait_contradiction_count == 1
    assert row.trait_derived_from == "reflection"


# ---------------------------------------------------------------------------
# TC-B02: Backfill skips already filled columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_skips_already_filled(db_session):
    """TC-B02: Backfill does not overwrite existing dedicated column values."""
    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, memory_type, metadata, trait_subtype, embedding)
        VALUES (
            gen_random_uuid(), 'bf_skip', 'existing trait', 'trait',
            '{{"trait_subtype":"core"}}'::jsonb,
            'behavior',
            '{_ZERO_VEC}'::halfvec
        )
    """))
    await db_session.flush()

    # Backfill should skip because trait_subtype IS NOT NULL
    await db_session.execute(text("""
        UPDATE memories SET
            trait_subtype = metadata->>'trait_subtype'
        WHERE memory_type = 'trait' AND trait_subtype IS NULL
          AND metadata->>'trait_subtype' IS NOT NULL
    """))

    result = await db_session.execute(text(
        "SELECT trait_subtype FROM memories WHERE user_id = 'bf_skip'"
    ))
    assert result.scalar() == "behavior"  # Not overwritten to 'core'


# ---------------------------------------------------------------------------
# TC-B03: general -> fact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_general_to_fact(db_session):
    """TC-B03: memory_type='general' is migrated to 'fact'."""
    # Temporarily disable check constraint to insert legacy 'general' type
    await _disable_memory_type_check(db_session)

    for i in range(3):
        await db_session.execute(text(
            f"INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
            f"VALUES (gen_random_uuid(), 'bf_general', 'general content {i}', 'general', '{{}}'::jsonb, '{_ZERO_VEC}'::halfvec)"
        ))
    await db_session.flush()

    # Execute migration
    await db_session.execute(text(
        "UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general'"
    ))

    # Re-enable constraint
    await _enable_memory_type_check(db_session)

    # Verify
    result = await db_session.execute(text(
        "SELECT COUNT(*) FROM memories WHERE user_id = 'bf_general' AND memory_type = 'general'"
    ))
    assert result.scalar() == 0

    result = await db_session.execute(text(
        "SELECT COUNT(*) FROM memories WHERE user_id = 'bf_general' AND memory_type = 'fact'"
    ))
    assert result.scalar() == 3

    # Verify content preserved
    result = await db_session.execute(text(
        "SELECT content FROM memories WHERE user_id = 'bf_general' ORDER BY content"
    ))
    contents = [r[0] for r in result.fetchall()]
    assert all("general content" in c for c in contents)


# ---------------------------------------------------------------------------
# TC-B04: insight -> trait(trend)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_insight_to_trait_trend(db_session):
    """TC-B04: memory_type='insight' migrates to trait with stage='trend'."""
    # Temporarily disable check constraint to insert legacy 'insight' type
    await _disable_memory_type_check(db_session)

    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, memory_type, metadata, created_at, embedding)
        VALUES (gen_random_uuid(), 'bf_insight', 'user tends to be efficient', 'insight',
                '{{}}'::jsonb, '2024-06-01T00:00:00Z'::timestamptz, '{_ZERO_VEC}'::halfvec)
    """))
    await db_session.flush()

    await db_session.execute(text("""
        UPDATE memories SET
            memory_type = 'trait',
            trait_stage = 'trend',
            trait_window_start = created_at,
            trait_window_end = created_at + interval '30 days'
        WHERE memory_type = 'insight'
    """))

    # Re-enable constraint
    await _enable_memory_type_check(db_session)

    result = await db_session.execute(text(
        "SELECT memory_type, trait_stage, trait_window_start, trait_window_end "
        "FROM memories WHERE user_id = 'bf_insight'"
    ))
    row = result.fetchone()

    assert row.memory_type == "trait"
    assert row.trait_stage == "trend"
    assert row.trait_window_start is not None
    assert row.trait_window_end is not None
    # Window should be 30 days after start
    delta = row.trait_window_end - row.trait_window_start
    assert abs(delta.days - 30) <= 1

    # No insight type left
    result = await db_session.execute(text(
        "SELECT COUNT(*) FROM memories WHERE memory_type = 'insight'"
    ))
    assert result.scalar() == 0


# ---------------------------------------------------------------------------
# TC-B05: content_hash backfill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_content_hash(db_session):
    """TC-B05: content_hash is correctly backfilled with MD5(content)."""
    test_content = "Hello World test content"
    expected_hash = hashlib.md5(test_content.encode()).hexdigest()

    await db_session.execute(text(
        "INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
        f"VALUES (gen_random_uuid(), 'bf_hash', '{test_content}', 'fact', '{{}}'::jsonb, '{_ZERO_VEC}'::halfvec)"
    ))
    await db_session.flush()

    await db_session.execute(text(
        "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL"
    ))

    result = await db_session.execute(text(
        "SELECT content_hash FROM memories WHERE user_id = 'bf_hash'"
    ))
    assert result.scalar() == expected_hash


# ---------------------------------------------------------------------------
# TC-B06: content_hash skips existing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_content_hash_skips_existing(db_session):
    """TC-B06: Backfill does not overwrite existing content_hash."""
    await db_session.execute(text(
        "INSERT INTO memories (id, user_id, content, memory_type, metadata, content_hash, embedding) "
        f"VALUES (gen_random_uuid(), 'bf_hash_keep', 'some content', 'fact', '{{}}'::jsonb, 'abc123', '{_ZERO_VEC}'::halfvec)"
    ))
    await db_session.flush()

    await db_session.execute(text(
        "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL"
    ))

    result = await db_session.execute(text(
        "SELECT content_hash FROM memories WHERE user_id = 'bf_hash_keep'"
    ))
    assert result.scalar() == "abc123"


# ---------------------------------------------------------------------------
# TC-B07: valid_at backfill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_valid_at(db_session):
    """TC-B07: valid_at = COALESCE(valid_from, created_at)."""
    # Memory A: has valid_from
    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, memory_type, metadata,
                              valid_from, created_at, embedding)
        VALUES (gen_random_uuid(), 'bf_valid_a', 'has valid_from', 'fact', '{{}}'::jsonb,
                '2024-01-01T00:00:00Z'::timestamptz, '2024-01-05T00:00:00Z'::timestamptz,
                '{_ZERO_VEC}'::halfvec)
    """))

    # Memory B: no valid_from
    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, memory_type, metadata,
                              created_at, embedding)
        VALUES (gen_random_uuid(), 'bf_valid_b', 'no valid_from', 'fact', '{{}}'::jsonb,
                '2024-02-01T00:00:00Z'::timestamptz,
                '{_ZERO_VEC}'::halfvec)
    """))
    await db_session.flush()

    await db_session.execute(text(
        "UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL"
    ))

    # Check A: should use valid_from
    result = await db_session.execute(text(
        "SELECT valid_at FROM memories WHERE user_id = 'bf_valid_a'"
    ))
    row_a = result.fetchone()
    assert row_a.valid_at.year == 2024
    assert row_a.valid_at.month == 1
    assert row_a.valid_at.day == 1

    # Check B: should use created_at
    result = await db_session.execute(text(
        "SELECT valid_at FROM memories WHERE user_id = 'bf_valid_b'"
    ))
    row_b = result.fetchone()
    assert row_b.valid_at.year == 2024
    assert row_b.valid_at.month == 2
    assert row_b.valid_at.day == 1


# ---------------------------------------------------------------------------
# TC-B08: Backfill idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_idempotent(db_session):
    """TC-B08: Running backfill twice produces same results."""
    # Temporarily disable check constraint to insert legacy 'general' type
    await _disable_memory_type_check(db_session)

    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding)
        VALUES (gen_random_uuid(), 'bf_idemp', 'idempotent test', 'general', '{{}}'::jsonb, '{_ZERO_VEC}'::halfvec)
    """))
    await db_session.flush()

    backfill_sqls = [
        "UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general'",
        "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL",
        "UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL",
    ]

    # Run twice
    for _ in range(2):
        for sql in backfill_sqls:
            await db_session.execute(text(sql))

    # Re-enable constraint
    await _enable_memory_type_check(db_session)

    result = await db_session.execute(text(
        "SELECT memory_type, content_hash, valid_at FROM memories WHERE user_id = 'bf_idemp'"
    ))
    row = result.fetchone()
    assert row.memory_type == "fact"
    assert row.content_hash is not None
    assert row.valid_at is not None


# ---------------------------------------------------------------------------
# TC-B09: Backfill preserves metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_preserves_metadata(db_session):
    """TC-B09: Backfill does not modify the metadata JSONB content."""
    meta_json = '{"trait_subtype":"preference","extra_field":"keep_me","emotion":{"valence":0.5}}'
    await db_session.execute(
        text("INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
             "VALUES (gen_random_uuid(), 'bf_meta', 'preserve meta', 'trait', "
             "CAST(:meta AS jsonb), CAST(:vec AS halfvec))"),
        {"meta": meta_json, "vec": _ZERO_VEC},
    )
    await db_session.flush()

    # Run trait backfill
    await db_session.execute(text("""
        UPDATE memories SET
            trait_subtype = metadata->>'trait_subtype'
        WHERE memory_type = 'trait' AND trait_subtype IS NULL
          AND metadata->>'trait_subtype' IS NOT NULL
    """))

    result = await db_session.execute(text(
        "SELECT metadata FROM memories WHERE user_id = 'bf_meta'"
    ))
    meta = result.scalar()
    assert meta["extra_field"] == "keep_me"
    assert meta["emotion"]["valence"] == 0.5
    assert meta["trait_subtype"] == "preference"


# ---------------------------------------------------------------------------
# TC-B10: Backfill with NULL metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_null_metadata(db_session):
    """TC-B10: Backfill does not error on NULL metadata."""
    await db_session.execute(text(
        "INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
        f"VALUES (gen_random_uuid(), 'bf_null', 'null meta', 'trait', NULL, '{_ZERO_VEC}'::halfvec)"
    ))
    await db_session.flush()

    # Should not error
    await db_session.execute(text("""
        UPDATE memories SET
            trait_subtype = metadata->>'trait_subtype'
        WHERE memory_type = 'trait' AND trait_subtype IS NULL
          AND metadata->>'trait_subtype' IS NOT NULL
    """))

    result = await db_session.execute(text(
        "SELECT trait_subtype FROM memories WHERE user_id = 'bf_null'"
    ))
    assert result.scalar() is None  # Not backfilled, as expected


# ---------------------------------------------------------------------------
# TC-B11: Backfill with empty metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_empty_metadata(db_session):
    """TC-B11: Backfill does not error on empty {} metadata."""
    await db_session.execute(text(
        "INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
        f"VALUES (gen_random_uuid(), 'bf_empty', 'empty meta', 'trait', '{{}}'::jsonb, '{_ZERO_VEC}'::halfvec)"
    ))
    await db_session.flush()

    await db_session.execute(text("""
        UPDATE memories SET
            trait_subtype = metadata->>'trait_subtype'
        WHERE memory_type = 'trait' AND trait_subtype IS NULL
          AND metadata->>'trait_subtype' IS NOT NULL
    """))

    result = await db_session.execute(text(
        "SELECT trait_subtype FROM memories WHERE user_id = 'bf_empty'"
    ))
    assert result.scalar() is None


# ---------------------------------------------------------------------------
# TC-B12: Unicode content hash
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_backfill_unicode_content_hash(db_session):
    """TC-B12: content_hash is correct for Unicode content."""
    content = "用户在Google工作喜欢Python和JavaScript"
    expected_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

    await db_session.execute(text(
        "INSERT INTO memories (id, user_id, content, memory_type, metadata, embedding) "
        f"VALUES (gen_random_uuid(), 'bf_unicode', '{content}', 'fact', '{{}}'::jsonb, '{_ZERO_VEC}'::halfvec)"
    ))
    await db_session.flush()

    await db_session.execute(text(
        "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL"
    ))

    result = await db_session.execute(text(
        "SELECT content_hash FROM memories WHERE user_id = 'bf_unicode'"
    ))
    db_hash = result.scalar()

    # Note: PG MD5() uses server encoding (UTF-8), should match Python
    assert db_hash == expected_hash
