"""Tests for RPIV-1 storage foundation V2: Read compatibility.

Covers: dedicated column priority, JSONB fallback, search result format.
PRD section: 7.7
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from neuromem.services.search import SearchService


# ---------------------------------------------------------------------------
# TC-R01: Read prefers dedicated column
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_prefers_dedicated_column(db_session, mock_embedding):
    """TC-R01: When both dedicated column and JSONB have a value, column wins."""
    # Insert directly via SQL to control both values independently
    vec = await mock_embedding.embed("dedicated test")
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, embedding, memory_type,
                              metadata, trait_subtype)
        VALUES (gen_random_uuid(), 'r_pref', 'dedicated test',
                '{vec_str}', 'trait',
                '{{"trait_subtype":"behavior"}}'::jsonb,
                'preference')
    """))
    await db_session.commit()

    # Read via COALESCE pattern (what the implementation should use)
    result = await db_session.execute(text("""
        SELECT COALESCE(trait_subtype, metadata->>'trait_subtype') AS resolved_subtype
        FROM memories WHERE user_id = 'r_pref'
    """))
    row = result.fetchone()
    assert row.resolved_subtype == "preference"  # Column value, not JSONB


# ---------------------------------------------------------------------------
# TC-R02: Read falls back to JSONB
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_fallback_to_jsonb(db_session, mock_embedding):
    """TC-R02: When dedicated column is NULL, fallback to JSONB value."""
    vec = await mock_embedding.embed("fallback test")
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, embedding, memory_type,
                              metadata)
        VALUES (gen_random_uuid(), 'r_fall', 'fallback test',
                '{vec_str}', 'trait',
                '{{"trait_subtype":"behavior"}}'::jsonb)
    """))
    await db_session.commit()

    result = await db_session.execute(text("""
        SELECT COALESCE(trait_subtype, metadata->>'trait_subtype') AS resolved_subtype
        FROM memories WHERE user_id = 'r_fall'
    """))
    row = result.fetchone()
    assert row.resolved_subtype == "behavior"  # JSONB fallback


# ---------------------------------------------------------------------------
# TC-R03: Both NULL returns None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_both_null_returns_none(db_session, mock_embedding):
    """TC-R03: When both column and JSONB are NULL, result is NULL."""
    vec = await mock_embedding.embed("null test")
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"

    await db_session.execute(text(f"""
        INSERT INTO memories (id, user_id, content, embedding, memory_type, metadata)
        VALUES (gen_random_uuid(), 'r_null', 'null test',
                '{vec_str}', 'fact', '{{}}'::jsonb)
    """))
    await db_session.commit()

    result = await db_session.execute(text("""
        SELECT COALESCE(trait_subtype, metadata->>'trait_subtype') AS resolved_subtype
        FROM memories WHERE user_id = 'r_null'
    """))
    row = result.fetchone()
    assert row.resolved_subtype is None


# ---------------------------------------------------------------------------
# TC-R04: Search result format unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_result_format_unchanged(db_session, mock_embedding):
    """TC-R04: search() returns results with all expected V1 fields."""
    svc = SearchService(db_session, mock_embedding)

    await svc.add_memory(user_id="r_fmt", content="format test", memory_type="fact")
    await db_session.commit()

    results = await svc.search(user_id="r_fmt", query="format test", limit=5)
    assert len(results) > 0

    r = results[0]
    # V1 expected fields
    assert "id" in r
    assert "content" in r
    assert "memory_type" in r
    assert "metadata" in r


# ---------------------------------------------------------------------------
# TC-R05: scored_search result format unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scored_search_result_format_unchanged(db_session, mock_embedding):
    """TC-R05: scored_search() returns relevance/recency/importance/score."""
    svc = SearchService(db_session, mock_embedding)

    await svc.add_memory(
        user_id="r_scored", content="scored test",
        memory_type="fact", metadata={"importance": 5},
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="r_scored", query="scored test", limit=5)
    assert len(results) > 0

    r = results[0]
    assert "relevance" in r
    assert "recency" in r
    assert "importance" in r
    assert "score" in r
    assert r["relevance"] >= 0
    assert r["recency"] >= 0
    assert r["importance"] >= 0
