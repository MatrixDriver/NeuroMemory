"""Tests for graph service.

These tests verify graph operations using relational tables.
"""

import pytest

from neuromem.models.graph import EdgeType, NodeType
from neuromem.services.graph import GraphService

TEST_USER_ID = "test-user-123"


@pytest.mark.asyncio
async def test_create_node(db_session):
    """Test creating a graph node."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    node = await svc.create_node(
        node_type=NodeType.USER,
        node_id="user123",
        properties={"name": "Alice"},
    )

    assert node.node_type == "User"
    assert node.node_id == "user123"
    assert node.user_id == TEST_USER_ID
    assert node.properties == {"name": "Alice"}


@pytest.mark.asyncio
async def test_create_node_duplicate(db_session):
    """Test creating a duplicate node raises error."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    await svc.create_node(node_type=NodeType.USER, node_id="dup_user")
    await db_session.flush()

    with pytest.raises(ValueError, match="already exists"):
        await svc.create_node(node_type=NodeType.USER, node_id="dup_user")


@pytest.mark.asyncio
async def test_create_node_requires_user_id(db_session):
    """Test that user_id is required for node creation."""
    svc = GraphService(db_session)  # No user_id

    with pytest.raises(ValueError, match="user_id is required"):
        await svc.create_node(node_type=NodeType.USER, node_id="user1")


@pytest.mark.asyncio
async def test_create_edge(db_session):
    """Test creating a graph edge."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    # Create source and target nodes first
    await svc.create_node(node_type=NodeType.USER, node_id="user1")
    await svc.create_node(node_type=NodeType.MEMORY, node_id="mem1")
    await db_session.flush()

    edge = await svc.create_edge(
        source_type=NodeType.USER,
        source_id="user1",
        edge_type=EdgeType.HAS_MEMORY,
        target_type=NodeType.MEMORY,
        target_id="mem1",
        properties={"weight": 1.0},
    )

    assert edge.source_type == "User"
    assert edge.source_id == "user1"
    assert edge.edge_type == "HAS_MEMORY"
    assert edge.target_type == "Memory"
    assert edge.target_id == "mem1"
    assert edge.user_id == TEST_USER_ID


@pytest.mark.asyncio
async def test_create_edge_missing_node(db_session):
    """Test creating edge when node doesn't exist."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)

    with pytest.raises(ValueError, match="not found"):
        await svc.create_edge(
            source_type=NodeType.USER,
            source_id="nonexistent",
            edge_type=EdgeType.HAS_MEMORY,
            target_type=NodeType.MEMORY,
            target_id="mem1",
        )


@pytest.mark.asyncio
async def test_get_neighbors(db_session):
    """Test getting neighbors via relational tables."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    # Create nodes and edge
    await svc.create_node(node_type=NodeType.USER, node_id="user123")
    await svc.create_node(node_type=NodeType.MEMORY, node_id="mem1")
    await svc.create_node(node_type=NodeType.MEMORY, node_id="mem2")
    await db_session.flush()

    await svc.create_edge(
        source_type=NodeType.USER, source_id="user123",
        edge_type=EdgeType.HAS_MEMORY,
        target_type=NodeType.MEMORY, target_id="mem1",
    )
    await svc.create_edge(
        source_type=NodeType.USER, source_id="user123",
        edge_type=EdgeType.HAS_MEMORY,
        target_type=NodeType.MEMORY, target_id="mem2",
    )
    await db_session.flush()

    results = await svc.get_neighbors(
        node_type=NodeType.USER,
        node_id="user123",
        edge_types=[EdgeType.HAS_MEMORY],
        direction="out",
    )

    assert len(results) == 2
    assert all(r["rel_type"] == "HAS_MEMORY" for r in results)


@pytest.mark.asyncio
async def test_get_neighbors_user_isolation(db_session):
    """Test that get_neighbors only returns edges for the requesting user."""
    # User A creates nodes and edge
    svc_a = GraphService(db_session, user_id="user-a")
    await svc_a.create_node(node_type=NodeType.USER, node_id="alice")
    await svc_a.create_node(node_type=NodeType.CONCEPT, node_id="python")
    await db_session.flush()
    await svc_a.create_edge(
        source_type=NodeType.USER, source_id="alice",
        edge_type=EdgeType.HAS_SKILL,
        target_type=NodeType.CONCEPT, target_id="python",
    )
    await db_session.flush()

    # User B creates nodes with same IDs
    svc_b = GraphService(db_session, user_id="user-b")
    await svc_b.create_node(node_type=NodeType.USER, node_id="alice")
    await db_session.flush()

    # User B should see no neighbors for "alice"
    results = await svc_b.get_neighbors(
        node_type=NodeType.USER, node_id="alice", direction="out",
    )
    assert len(results) == 0

    # User A should see the neighbor
    results = await svc_a.get_neighbors(
        node_type=NodeType.USER, node_id="alice", direction="out",
    )
    assert len(results) == 1


@pytest.mark.asyncio
async def test_find_path(db_session):
    """Test finding path via relational tables."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    await svc.create_node(node_type=NodeType.USER, node_id="user123")
    await svc.create_node(node_type=NodeType.MEMORY, node_id="mem456")
    await db_session.flush()
    await svc.create_edge(
        source_type=NodeType.USER, source_id="user123",
        edge_type=EdgeType.HAS_MEMORY,
        target_type=NodeType.MEMORY, target_id="mem456",
    )
    await db_session.flush()

    results = await svc.find_path(
        source_type=NodeType.USER,
        source_id="user123",
        target_type=NodeType.MEMORY,
        target_id="mem456",
        max_depth=3,
    )

    assert len(results) == 1
    assert len(results[0]["nodes"]) == 2


@pytest.mark.asyncio
async def test_find_path_invalid_depth(db_session):
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    with pytest.raises(ValueError, match="max_depth"):
        await svc.find_path(
            source_type=NodeType.USER,
            source_id="u1",
            target_type=NodeType.MEMORY,
            target_id="m1",
            max_depth=11,
        )


@pytest.mark.asyncio
async def test_update_node(db_session):
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    await svc.create_node(node_type=NodeType.USER, node_id="upd_user", properties={"name": "Alice"})
    await db_session.flush()

    node = await svc.update_node(
        node_type=NodeType.USER,
        node_id="upd_user",
        properties={"email": "alice@example.com"},
    )

    assert node.properties["email"] == "alice@example.com"
    assert node.properties["name"] == "Alice"


@pytest.mark.asyncio
async def test_update_node_not_found(db_session):
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    with pytest.raises(ValueError, match="not found"):
        await svc.update_node(
            node_type=NodeType.USER,
            node_id="nonexistent",
            properties={"name": "Bob"},
        )


@pytest.mark.asyncio
async def test_delete_node(db_session):
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    await svc.create_node(node_type=NodeType.USER, node_id="del_user")
    await db_session.flush()

    await svc.delete_node(node_type=NodeType.USER, node_id="del_user")
    # Should not raise


@pytest.mark.asyncio
async def test_delete_node_not_found(db_session):
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    with pytest.raises(ValueError, match="not found"):
        await svc.delete_node(node_type=NodeType.USER, node_id="nonexistent")


@pytest.mark.asyncio
async def test_get_node(db_session):
    """Test getting a node by type and ID."""
    svc = GraphService(db_session, user_id=TEST_USER_ID)
    await svc.create_node(node_type=NodeType.USER, node_id="get_user", properties={"name": "Test"})
    await db_session.flush()

    result = await svc.get_node(node_type=NodeType.USER, node_id="get_user")
    assert result is not None
    assert result["node_id"] == "get_user"
    assert result["user_id"] == TEST_USER_ID

    # Different user should not see this node
    svc2 = GraphService(db_session, user_id="other-user")
    result2 = await svc2.get_node(node_type=NodeType.USER, node_id="get_user")
    assert result2 is None
