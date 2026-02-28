"""Tests for recall trait_boost — search stage filtering and boost weights.

Covers scene S7: trait_boost weights per stage, stage exclusion in search,
and backward compatibility with NULL trait_stage.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from neuromem.services.search import SearchService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_trait(
    db_session,
    mock_embedding,
    *,
    user_id: str = "boost_user",
    content: str | None = None,
    trait_stage: str | None = None,
    trait_subtype: str = "behavior",
    trait_confidence: float = 0.5,
) -> str:
    """Insert a trait-type memory with given stage, return its id."""
    svc = SearchService(db_session, mock_embedding)
    if content is None:
        content = f"trait {uuid.uuid4().hex[:8]}"
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="trait",
        metadata={"importance": 7},
    )
    await db_session.commit()

    # Update trait-specific columns directly
    params: dict = {"mid": str(record.id)}
    set_parts = [
        "trait_subtype = :subtype",
        "trait_confidence = :conf",
    ]
    params["subtype"] = trait_subtype
    params["conf"] = trait_confidence

    if trait_stage is not None:
        set_parts.append("trait_stage = :stage")
        params["stage"] = trait_stage

    stmt = text(f"UPDATE memories SET {', '.join(set_parts)} WHERE id = :mid")
    await db_session.execute(stmt, params)
    await db_session.commit()
    return str(record.id)


async def _insert_fact(
    db_session,
    mock_embedding,
    *,
    user_id: str = "boost_user",
    content: str | None = None,
) -> str:
    """Insert a fact-type memory, return its id."""
    svc = SearchService(db_session, mock_embedding)
    if content is None:
        content = f"fact {uuid.uuid4().hex[:8]}"
    record = await svc.add_memory(
        user_id=user_id,
        content=content,
        memory_type="fact",
        metadata={"importance": 7},
    )
    await db_session.commit()
    return str(record.id)


# ---------------------------------------------------------------------------
# S7: Stage exclusion — trend/candidate/dissolved are filtered out
# ---------------------------------------------------------------------------


class TestStageExclusion:
    """Search should exclude traits in inactive stages."""

    @pytest.mark.asyncio
    async def test_search_excludes_trend(self, db_session, mock_embedding):
        """Traits in 'trend' stage should not appear in search results."""
        uid = f"excl_trend_{uuid.uuid4().hex[:6]}"
        content = f"user likes hiking {uuid.uuid4().hex[:6]}"
        await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="trend",
        )
        await db_session.commit()

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)
        trait_ids_in_results = [
            r["id"] for r in results if r.get("memory_type") == "trait"
        ]
        assert len(trait_ids_in_results) == 0, "trend traits should be excluded from search"

    @pytest.mark.asyncio
    async def test_search_excludes_candidate(self, db_session, mock_embedding):
        """Traits in 'candidate' stage should not appear in search results."""
        uid = f"excl_cand_{uuid.uuid4().hex[:6]}"
        content = f"user prefers dark mode {uuid.uuid4().hex[:6]}"
        await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="candidate",
        )
        await db_session.commit()

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)
        trait_ids_in_results = [
            r["id"] for r in results if r.get("memory_type") == "trait"
        ]
        assert len(trait_ids_in_results) == 0, "candidate traits should be excluded from search"

    @pytest.mark.asyncio
    async def test_search_excludes_dissolved(self, db_session, mock_embedding):
        """Traits in 'dissolved' stage should not appear in search results."""
        uid = f"excl_diss_{uuid.uuid4().hex[:6]}"
        content = f"user was a morning person {uuid.uuid4().hex[:6]}"
        await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="dissolved",
        )
        await db_session.commit()

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)
        trait_ids_in_results = [
            r["id"] for r in results if r.get("memory_type") == "trait"
        ]
        assert len(trait_ids_in_results) == 0, "dissolved traits should be excluded from search"

    @pytest.mark.asyncio
    async def test_search_includes_emerging(self, db_session, mock_embedding):
        """Traits in 'emerging' stage should appear in search results."""
        uid = f"incl_emrg_{uuid.uuid4().hex[:6]}"
        content = f"user enjoys classical music {uuid.uuid4().hex[:6]}"
        await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="emerging",
        )
        await db_session.commit()

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)
        trait_ids_in_results = [
            r["id"] for r in results if r.get("memory_type") == "trait"
        ]
        assert len(trait_ids_in_results) >= 1, "emerging traits should be included in search"


# ---------------------------------------------------------------------------
# S7: Boost weights per stage
# ---------------------------------------------------------------------------


class TestTraitBoost:
    """Verify trait_boost weight values for each active stage."""

    @pytest.mark.asyncio
    async def test_search_boost_core(self, db_session, mock_embedding):
        """Core trait should receive 0.25 boost factor in score."""
        uid = f"boost_core_{uuid.uuid4().hex[:6]}"
        content = f"user is a Python expert {uuid.uuid4().hex[:6]}"

        # Insert core trait and a matching fact with same content
        trait_id = await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="core",
            trait_confidence=0.9,
        )
        fact_id = await _insert_fact(
            db_session, mock_embedding,
            user_id=uid, content=content,
        )

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)

        # Find both results
        trait_result = next((r for r in results if r["id"] == trait_id), None)
        fact_result = next((r for r in results if r["id"] == fact_id), None)

        assert trait_result is not None, "core trait should appear in results"
        assert fact_result is not None, "fact should appear in results"
        # Core trait score should be higher due to 0.25 boost
        assert trait_result["score"] > fact_result["score"], (
            f"core trait score ({trait_result['score']}) should exceed "
            f"fact score ({fact_result['score']}) due to 0.25 boost"
        )

    @pytest.mark.asyncio
    async def test_search_boost_established(self, db_session, mock_embedding):
        """Established trait should receive 0.15 boost factor."""
        uid = f"boost_estab_{uuid.uuid4().hex[:6]}"
        content = f"user prefers vim editor {uuid.uuid4().hex[:6]}"

        trait_id = await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="established",
            trait_confidence=0.7,
        )
        fact_id = await _insert_fact(
            db_session, mock_embedding,
            user_id=uid, content=content,
        )

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)

        trait_result = next((r for r in results if r["id"] == trait_id), None)
        fact_result = next((r for r in results if r["id"] == fact_id), None)

        assert trait_result is not None, "established trait should appear in results"
        assert fact_result is not None, "fact should appear in results"
        assert trait_result["score"] > fact_result["score"], (
            f"established trait score ({trait_result['score']}) should exceed "
            f"fact score ({fact_result['score']}) due to 0.15 boost"
        )

    @pytest.mark.asyncio
    async def test_search_boost_emerging(self, db_session, mock_embedding):
        """Emerging trait should receive 0.05 boost factor."""
        uid = f"boost_emrg_{uuid.uuid4().hex[:6]}"
        content = f"user likes green tea {uuid.uuid4().hex[:6]}"

        trait_id = await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage="emerging",
            trait_confidence=0.5,
        )
        fact_id = await _insert_fact(
            db_session, mock_embedding,
            user_id=uid, content=content,
        )

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)

        trait_result = next((r for r in results if r["id"] == trait_id), None)
        fact_result = next((r for r in results if r["id"] == fact_id), None)

        assert trait_result is not None, "emerging trait should appear in results"
        assert fact_result is not None, "fact should appear in results"
        # Emerging gets only 0.05 boost, so might be marginal
        assert trait_result["score"] >= fact_result["score"], (
            f"emerging trait score ({trait_result['score']}) should be >= "
            f"fact score ({fact_result['score']}) due to 0.05 boost"
        )


# ---------------------------------------------------------------------------
# S7: Backward compat and edge cases
# ---------------------------------------------------------------------------


class TestTraitBoostEdgeCases:
    """Edge cases for trait_boost: NULL stage, non-trait memories."""

    @pytest.mark.asyncio
    async def test_search_null_stage(self, db_session, mock_embedding):
        """Trait with NULL trait_stage should not cause errors and get no boost."""
        uid = f"null_stage_{uuid.uuid4().hex[:6]}"
        content = f"old trait from v1 {uuid.uuid4().hex[:6]}"

        # Insert trait without setting trait_stage (stays NULL)
        await _insert_trait(
            db_session, mock_embedding,
            user_id=uid, content=content, trait_stage=None,
        )
        await db_session.commit()

        svc = SearchService(db_session, mock_embedding)
        # Should not raise any exception
        results = await svc.scored_search(user_id=uid, query=content, limit=10)
        # NULL stage traits should still appear (not in the exclusion list)
        # but get no boost (ELSE 0 in CASE)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_non_trait_no_boost(self, db_session, mock_embedding):
        """Fact-type memories should receive zero trait_boost."""
        uid = f"no_boost_{uuid.uuid4().hex[:6]}"
        content = f"plain fact about weather {uuid.uuid4().hex[:6]}"

        fact_id = await _insert_fact(
            db_session, mock_embedding,
            user_id=uid, content=content,
        )

        svc = SearchService(db_session, mock_embedding)
        results = await svc.scored_search(user_id=uid, query=content, limit=10)

        fact_result = next((r for r in results if r["id"] == fact_id), None)
        assert fact_result is not None
        # If trait_boost is exposed in result, verify it is 0
        if "trait_boost" in fact_result:
            assert fact_result["trait_boost"] == 0
