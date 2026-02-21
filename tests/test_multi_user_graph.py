"""Multi-user graph integration tests.

These tests verify that the knowledge graph correctly handles multiple users
creating nodes with the same names (e.g., two users both visiting "前海滑雪场").
"""

from __future__ import annotations

import pytest

from neuromemory.services.graph_memory import GraphMemoryService


@pytest.mark.asyncio
async def test_multiple_users_can_create_same_location_node(db_session):
    """Test that different users can create nodes with the same name.

    This was a bug: the unique index on (node_type, node_id) didn't include user_id,
    causing the second user to fail when creating a node with the same name.

    Fixed by changing the index to (user_id, node_type, node_id).
    """
    svc = GraphMemoryService(db_session)

    # User 1 visits "前海滑雪场"
    count1 = await svc.store_triples("user_1", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "visited",
        "object": "前海滑雪场",
        "object_type": "location",
        "content": "去了前海滑雪场",
        "confidence": 1.0,
    }])
    assert count1 == 1

    # User 2 also visits "前海滑雪场" - should NOT fail
    count2 = await svc.store_triples("user_2", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "visited",
        "object": "前海滑雪场",
        "object_type": "location",
        "content": "也去了前海滑雪场",
        "confidence": 1.0,
    }])
    assert count2 == 1  # Should succeed, not fail with unique constraint violation

    await db_session.commit()


@pytest.mark.asyncio
async def test_multiple_users_same_event(db_session):
    """Test multiple users can create nodes for the same event type."""
    svc = GraphMemoryService(db_session)

    # User 1: 滑雪活动
    count1 = await svc.store_triples("user_1", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "attended",
        "object": "滑雪活动",
        "object_type": "event",
        "content": "参加了滑雪活动",
        "confidence": 1.0,
    }])
    assert count1 == 1

    # User 2: 滑雪活动 (different instance, same name)
    count2 = await svc.store_triples("user_2", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "attended",
        "object": "滑雪活动",
        "object_type": "event",
        "content": "也参加了滑雪活动",
        "confidence": 1.0,
    }])
    assert count2 == 1

    await db_session.commit()


@pytest.mark.asyncio
async def test_user_isolation_in_node_lookup(db_session):
    """Test that _ensure_node queries filter by user_id.

    This was a bug: _ensure_node was querying without user_id filter,
    potentially returning nodes from other users.
    """
    svc = GraphMemoryService(db_session)

    # User 1 creates a "Google" organization node
    await svc.store_triples("user_1", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "works_at",
        "object": "Google",
        "object_type": "organization",
        "content": "在 Google 工作",
        "confidence": 1.0,
    }])

    # User 2 creates their own "Google" node - should create a separate node
    await svc.store_triples("user_2", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "works_at",
        "object": "Google",
        "object_type": "organization",
        "content": "也在 Google 工作",
        "confidence": 1.0,
    }])

    await db_session.commit()

    # Query to verify: there should be 2 separate "Google" nodes
    from sqlalchemy import select, func
    from neuromemory.models.graph import GraphNode

    result = await db_session.execute(
        select(func.count(GraphNode.id))
        .where(GraphNode.node_type == "Organization")
        .where(GraphNode.node_id.like("%google%"))
    )
    count = result.scalar()
    assert count == 2, "Should have 2 separate Google nodes, one per user"


@pytest.mark.asyncio
async def test_cross_user_edge_isolation(db_session):
    """Test that edges are properly isolated between users."""
    svc = GraphMemoryService(db_session)

    # User 1: works at Google
    await svc.store_triples("user_1", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "works_at",
        "object": "Google",
        "object_type": "organization",
        "content": "在 Google 工作",
        "confidence": 1.0,
    }])

    # User 2: works at Meta
    await svc.store_triples("user_2", [{
        "subject": "user",
        "subject_type": "user",
        "relation": "works_at",
        "object": "Meta",
        "object_type": "organization",
        "content": "在 Meta 工作",
        "confidence": 1.0,
    }])

    await db_session.commit()

    # Verify: each user should have exactly 1 works_at edge
    from sqlalchemy import select, func
    from neuromemory.models.graph import GraphEdge

    for user_id in ["user_1", "user_2"]:
        result = await db_session.execute(
            select(func.count(GraphEdge.id))
            .where(GraphEdge.user_id == user_id)
            .where(GraphEdge.edge_type == "WORKS_AT")
        )
        count = result.scalar()
        assert count == 1, f"User {user_id} should have exactly 1 works_at edge"
