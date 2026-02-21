"""Tests for graph memory service - triple storage and conflict resolution."""

from __future__ import annotations

import pytest

from neuromemory.models.graph import EdgeType, GraphEdge, GraphNode, NodeType
from neuromemory.services.graph_memory import GraphMemoryService


@pytest.mark.asyncio
async def test_store_triple_creates_nodes_and_edge(db_session):
    """Storing a triple should create subject/object nodes and an edge."""
    svc = GraphMemoryService(db_session)
    count = await svc.store_triples("u1", [
        {
            "subject": "user",
            "subject_type": "user",
            "relation": "works_at",
            "object": "Google",
            "object_type": "organization",
            "content": "在 Google 工作",
            "confidence": 0.98,
        },
    ])

    assert count == 1

    # Verify nodes were created
    from sqlalchemy import select
    nodes = (await db_session.execute(select(GraphNode))).scalars().all()
    node_ids = {n.node_id for n in nodes}
    assert "u1" in node_ids  # USER node uses user_id
    assert "google" in node_ids  # normalized

    # Verify edge was created
    edges = (await db_session.execute(select(GraphEdge))).scalars().all()
    assert len(edges) == 1
    assert edges[0].edge_type == "WORKS_AT"
    assert edges[0].source_id == "u1"
    assert edges[0].target_id == "google"
    assert edges[0].properties["valid_from"] is not None
    assert edges[0].properties["valid_until"] is None


@pytest.mark.asyncio
async def test_duplicate_triple_returns_noop(db_session):
    """Storing the same triple twice should only create one edge."""
    svc = GraphMemoryService(db_session)
    triple = {
        "subject": "user",
        "subject_type": "user",
        "relation": "has_skill",
        "object": "Python",
        "object_type": "skill",
        "content": "会 Python",
        "confidence": 0.95,
    }

    count1 = await svc.store_triples("u1", [triple])
    assert count1 == 1

    count2 = await svc.store_triples("u1", [triple])
    assert count2 == 0  # NOOP


@pytest.mark.asyncio
async def test_conflict_resolution_update(db_session):
    """Changing a fact (e.g. new job) should invalidate old edge and create new one."""
    svc = GraphMemoryService(db_session)

    # First: works at Google
    count1 = await svc.store_triples("u1", [{
        "subject": "user", "subject_type": "user",
        "relation": "works_at",
        "object": "Google", "object_type": "organization",
        "content": "在 Google 工作", "confidence": 0.98,
    }])
    assert count1 == 1

    # Then: works at Meta (should UPDATE, not ADD)
    count2 = await svc.store_triples("u1", [{
        "subject": "user", "subject_type": "user",
        "relation": "works_at",
        "object": "Meta", "object_type": "organization",
        "content": "在 Meta 工作", "confidence": 0.98,
    }])
    assert count2 == 1

    # Verify: old edge should have valid_until set
    from sqlalchemy import select
    edges = (await db_session.execute(
        select(GraphEdge).where(
            GraphEdge.user_id == "u1",
            GraphEdge.edge_type == "WORKS_AT",
        )
    )).scalars().all()

    assert len(edges) == 2
    google_edge = [e for e in edges if e.target_id == "google"][0]
    meta_edge = [e for e in edges if e.target_id == "meta"][0]

    assert google_edge.properties["valid_until"] is not None  # invalidated
    assert meta_edge.properties["valid_until"] is None  # active


@pytest.mark.asyncio
async def test_find_entity_facts(db_session):
    """Should find all active facts for an entity."""
    svc = GraphMemoryService(db_session)
    await svc.store_triples("u1", [
        {
            "subject": "user", "subject_type": "user",
            "relation": "works_at",
            "object": "Google", "object_type": "organization",
            "content": "在 Google 工作", "confidence": 0.98,
        },
        {
            "subject": "user", "subject_type": "user",
            "relation": "has_skill",
            "object": "Python", "object_type": "skill",
            "content": "会 Python", "confidence": 0.95,
        },
    ])

    # Find facts for user (using user_id directly since USER nodes use user_id)
    facts = await svc.find_entity_facts("u1", "u1")
    assert len(facts) == 2

    relations = {f["relation"] for f in facts}
    assert "WORKS_AT" in relations
    assert "HAS_SKILL" in relations


@pytest.mark.asyncio
async def test_invalid_triple_skipped(db_session):
    """Triples with empty fields should be skipped."""
    svc = GraphMemoryService(db_session)
    count = await svc.store_triples("u1", [
        {"subject": "", "subject_type": "user", "relation": "works_at",
         "object": "Google", "object_type": "organization",
         "content": "test", "confidence": 0.9},
        {"subject": "user", "subject_type": "user", "relation": "",
         "object": "Google", "object_type": "organization",
         "content": "test", "confidence": 0.9},
        {"subject": "user", "subject_type": "user", "relation": "works_at",
         "object": "", "object_type": "organization",
         "content": "test", "confidence": 0.9},
    ])
    assert count == 0


@pytest.mark.asyncio
async def test_custom_relation_stored(db_session):
    """Unknown relations should map to CUSTOM edge type with relation_name in properties."""
    svc = GraphMemoryService(db_session)
    count = await svc.store_triples("u1", [{
        "subject": "user", "subject_type": "user",
        "relation": "manages",
        "object": "Team Alpha", "object_type": "entity",
        "content": "管理 Team Alpha", "confidence": 0.9,
    }])
    assert count == 1

    from sqlalchemy import select
    edges = (await db_session.execute(select(GraphEdge))).scalars().all()
    assert edges[0].edge_type == "CUSTOM"
    assert edges[0].properties["relation_name"] == "manages"
