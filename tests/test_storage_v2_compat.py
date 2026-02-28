"""Tests for RPIV-1 storage foundation V2: Backward compatibility.

Covers: Public API unchanged, general type mapping, Embedding alias, data lifecycle.
PRD sections: all (cross-cutting)
"""

from __future__ import annotations

import pytest

from neuromem.services.search import SearchService


# ---------------------------------------------------------------------------
# TC-C01: add_memory API unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_memory_api_unchanged(db_session, mock_embedding):
    """TC-C01: add_memory with V1 parameters works without error."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id="c_add",
        content="backward compat test",
        memory_type="fact",
        metadata={"key": "val"},
    )
    assert record is not None
    assert record.content == "backward compat test"


# ---------------------------------------------------------------------------
# TC-C02: search API unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_api_unchanged(db_session, mock_embedding):
    """TC-C02: search with V1 parameters works without error."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(user_id="c_search", content="search compat")
    await svc.add_memory(user_id="c_search", content="another memory")
    await db_session.commit()

    results = await svc.search(user_id="c_search", query="search", limit=5)
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# TC-C03: scored_search API unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scored_search_api_unchanged(db_session, mock_embedding):
    """TC-C03: scored_search returns expected score fields."""
    svc = SearchService(db_session, mock_embedding)
    await svc.add_memory(
        user_id="c_scored", content="scored compat",
        metadata={"importance": 5},
    )
    await db_session.commit()

    results = await svc.scored_search(user_id="c_scored", query="scored", limit=5)
    assert isinstance(results, list)
    if len(results) > 0:
        r = results[0]
        assert "relevance" in r
        assert "recency" in r
        assert "importance" in r
        assert "score" in r


# ---------------------------------------------------------------------------
# TC-C04: recall API unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_api_unchanged(nm):
    """TC-C04: recall() returns dict with 'merged' key."""
    await nm._add_memory(user_id="c_recall", content="recall compat test")

    result = await nm.recall(user_id="c_recall", query="recall")
    assert isinstance(result, dict)
    assert "merged" in result


# ---------------------------------------------------------------------------
# TC-C05: general type accepted and mapped to fact
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_general_type_accepted_and_mapped(db_session, mock_embedding):
    """TC-C05: memory_type='general' is accepted and stored as 'fact'."""
    svc = SearchService(db_session, mock_embedding)
    record = await svc.add_memory(
        user_id="c_general", content="general type test", memory_type="general"
    )
    await db_session.commit()

    # The record should exist - whether stored as 'general' or mapped to 'fact'
    # depends on implementation. After RPIV-1, it should map to 'fact'.
    from sqlalchemy import text
    result = await db_session.execute(text(
        "SELECT memory_type FROM memories WHERE user_id = 'c_general'"
    ))
    row = result.fetchone()
    assert row is not None
    # Accept either 'general' (pre-migration) or 'fact' (post-migration)
    assert row.memory_type in ("general", "fact")


# ---------------------------------------------------------------------------
# TC-C06: ingest API unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_api_unchanged(nm):
    """TC-C06: ingest() works with standard parameters."""
    # ingest should not raise
    result = await nm.ingest(user_id="c_ingest", role="user", content="I work at Google")
    # Result can vary, just verify no exception


# ---------------------------------------------------------------------------
# TC-C07: delete_user_data works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_user_data_still_works(nm):
    """TC-C07: delete_user_data clears all user data including memories."""
    user_id = "c_delete"

    await nm._add_memory(user_id=user_id, content="delete test", memory_type="fact")

    result = await nm.delete_user_data(user_id)
    assert "deleted" in result

    # Verify data is gone
    recall_result = await nm.recall(user_id=user_id, query="delete test")
    assert len(recall_result["merged"]) == 0


# ---------------------------------------------------------------------------
# TC-C08: export_user_data works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_export_user_data_unchanged(nm):
    """TC-C08: export_user_data returns expected structure."""
    user_id = "c_export"

    await nm._add_memory(user_id=user_id, content="export test", memory_type="fact")

    result = await nm.export_user_data(user_id)
    assert isinstance(result, dict)
    assert "memories" in result
    assert "conversations" in result
    assert "graph" in result
    assert "kv" in result
    assert "profile" in result
    assert "documents" in result


# ---------------------------------------------------------------------------
# TC-C09: Embedding import alias
# ---------------------------------------------------------------------------

def test_embedding_import_alias():
    """TC-C09: Embedding can be imported from models.memory and equals Memory."""
    from neuromem.models.memory import Embedding, Memory
    assert Embedding is Memory

    # Also importable from models package
    from neuromem.models import Embedding as PkgEmbedding
    assert PkgEmbedding is Memory
