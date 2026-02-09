"""Tests for graph API endpoints.

These tests use mocked AGE functionality since AGE requires specific
database configuration that may not be available in all test environments.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_create_node(client):
    """Test creating a graph node."""
    with patch("server.app.services.graph.GraphService.create_node") as mock_create:
        # Mock the node creation
        mock_node = MagicMock()
        mock_node.id = "node-uuid-123"
        mock_node.tenant_id = "tenant-uuid"
        mock_node.node_type = "User"
        mock_node.node_id = "user123"
        mock_node.properties = {"name": "Alice"}
        mock_node.created_at = "2024-01-15T10:00:00"
        mock_create.return_value = mock_node

        resp = await client.post(
            "/v1/graph/nodes",
            json={
                "node_type": "User",
                "node_id": "user123",
                "properties": {"name": "Alice"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["node_type"] == "User"
        assert data["node_id"] == "user123"
        assert data["properties"]["name"] == "Alice"

        # Verify service was called
        mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_create_node_invalid_type(client):
    """Test creating node with invalid type."""
    resp = await client.post(
        "/v1/graph/nodes",
        json={
            "node_type": "InvalidType",
            "node_id": "test123",
        },
    )

    assert resp.status_code == 400
    data = resp.json()
    assert "Invalid node_type" in data["detail"]


@pytest.mark.asyncio
async def test_create_edge(client):
    """Test creating a graph edge."""
    with patch("server.app.services.graph.GraphService.create_edge") as mock_create:
        # Mock the edge creation
        mock_edge = MagicMock()
        mock_edge.id = "edge-uuid-123"
        mock_edge.tenant_id = "tenant-uuid"
        mock_edge.source_type = "User"
        mock_edge.source_id = "user123"
        mock_edge.edge_type = "HAS_MEMORY"
        mock_edge.target_type = "Memory"
        mock_edge.target_id = "mem456"
        mock_edge.properties = {"created_at": "2024-01-15"}
        mock_edge.created_at = "2024-01-15T10:00:00"
        mock_create.return_value = mock_edge

        resp = await client.post(
            "/v1/graph/edges",
            json={
                "source_type": "User",
                "source_id": "user123",
                "edge_type": "HAS_MEMORY",
                "target_type": "Memory",
                "target_id": "mem456",
                "properties": {"created_at": "2024-01-15"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["source_type"] == "User"
        assert data["source_id"] == "user123"
        assert data["edge_type"] == "HAS_MEMORY"
        assert data["target_type"] == "Memory"
        assert data["target_id"] == "mem456"


@pytest.mark.asyncio
async def test_create_edge_invalid_type(client):
    """Test creating edge with invalid type."""
    resp = await client.post(
        "/v1/graph/edges",
        json={
            "source_type": "User",
            "source_id": "user123",
            "edge_type": "INVALID_EDGE",
            "target_type": "Memory",
            "target_id": "mem456",
        },
    )

    assert resp.status_code == 400
    data = resp.json()
    assert "Invalid type" in data["detail"]


@pytest.mark.asyncio
async def test_create_edge_node_not_found(client):
    """Test creating edge when source node doesn't exist."""
    with patch("server.app.services.graph.GraphService.create_edge") as mock_create:
        mock_create.side_effect = ValueError("Node User:user123 not found")

        resp = await client.post(
            "/v1/graph/edges",
            json={
                "source_type": "User",
                "source_id": "user123",
                "edge_type": "HAS_MEMORY",
                "target_type": "Memory",
                "target_id": "mem456",
            },
        )

        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"]


@pytest.mark.asyncio
async def test_get_neighbors(client):
    """Test getting neighboring nodes."""
    with patch("server.app.services.graph.GraphService.get_neighbors") as mock_neighbors:
        mock_neighbors.return_value = [
            {
                "neighbor": {"id": "mem1", "content": "Memory 1"},
                "rel_type": "HAS_MEMORY",
                "rel_props": {},
            },
            {
                "neighbor": {"id": "mem2", "content": "Memory 2"},
                "rel_type": "HAS_MEMORY",
                "rel_props": {},
            },
        ]

        resp = await client.post(
            "/v1/graph/neighbors",
            json={
                "node_type": "User",
                "node_id": "user123",
                "edge_types": ["HAS_MEMORY"],
                "direction": "out",
                "limit": 10,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["rel_type"] == "HAS_MEMORY"


@pytest.mark.asyncio
async def test_get_neighbors_invalid_node_type(client):
    """Test getting neighbors with invalid node type."""
    resp = await client.post(
        "/v1/graph/neighbors",
        json={
            "node_type": "InvalidType",
            "node_id": "user123",
        },
    )

    assert resp.status_code == 400
    data = resp.json()
    assert "Invalid node_type" in data["detail"]


@pytest.mark.asyncio
async def test_find_path(client):
    """Test finding path between nodes."""
    with patch("server.app.services.graph.GraphService.find_path") as mock_path:
        mock_path.return_value = [
            {
                "nodes": [
                    {"id": "user123", "type": "User"},
                    {"id": "mem456", "type": "Memory"},
                ],
                "rels": [{"type": "HAS_MEMORY"}],
            }
        ]

        resp = await client.post(
            "/v1/graph/paths",
            json={
                "source_type": "User",
                "source_id": "user123",
                "target_type": "Memory",
                "target_id": "mem456",
                "max_depth": 3,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert len(data["results"]) == 1


@pytest.mark.asyncio
async def test_find_path_not_found(client):
    """Test finding path when no path exists."""
    with patch("server.app.services.graph.GraphService.find_path") as mock_path:
        mock_path.return_value = []

        resp = await client.post(
            "/v1/graph/paths",
            json={
                "source_type": "User",
                "source_id": "user123",
                "target_type": "Concept",
                "target_id": "concept789",
                "max_depth": 3,
            },
        )

        assert resp.status_code == 404
        data = resp.json()
        assert "No path found" in data["detail"]


@pytest.mark.asyncio
async def test_custom_query(client):
    """Test executing custom Cypher query."""
    with patch("server.app.services.graph.GraphService.query") as mock_query:
        mock_query.return_value = [
            {"user_id": "user123", "memory_count": 5},
            {"user_id": "user456", "memory_count": 3},
        ]

        resp = await client.post(
            "/v1/graph/query",
            json={
                "cypher": "MATCH (u:User {tenant_id: $tenant_id})-[:HAS_MEMORY]->(m:Memory) RETURN u.id as user_id, count(m) as memory_count",
                "params": {},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["results"]) == 2
        assert data["results"][0]["memory_count"] == 5


@pytest.mark.asyncio
async def test_custom_query_missing_tenant_filter(client):
    """Test custom query without tenant_id filter."""
    with patch("server.app.services.graph.GraphService.query") as mock_query:
        mock_query.side_effect = ValueError("Cypher query must include tenant_id filter")

        resp = await client.post(
            "/v1/graph/query",
            json={
                "cypher": "MATCH (u:User)-[:HAS_MEMORY]->(m:Memory) RETURN u, m",
            },
        )

        assert resp.status_code == 400
        data = resp.json()
        assert "tenant_id" in data["detail"]


@pytest.mark.asyncio
async def test_graph_workflow(client):
    """Test a complete graph workflow: create nodes, create edges, query."""
    with patch("server.app.services.graph.GraphService.create_node") as mock_node, \
         patch("server.app.services.graph.GraphService.create_edge") as mock_edge, \
         patch("server.app.services.graph.GraphService.get_neighbors") as mock_neighbors:

        # Setup mocks
        mock_node_user = MagicMock()
        mock_node_user.id = "node-1"
        mock_node_user.tenant_id = "tenant-1"
        mock_node_user.node_type = "User"
        mock_node_user.node_id = "alice"
        mock_node_user.properties = {}
        mock_node_user.created_at = "2024-01-15T10:00:00"

        mock_node_memory = MagicMock()
        mock_node_memory.id = "node-2"
        mock_node_memory.tenant_id = "tenant-1"
        mock_node_memory.node_type = "Memory"
        mock_node_memory.node_id = "mem1"
        mock_node_memory.properties = {"content": "Test memory"}
        mock_node_memory.created_at = "2024-01-15T10:01:00"

        mock_edge_obj = MagicMock()
        mock_edge_obj.id = "edge-1"
        mock_edge_obj.tenant_id = "tenant-1"
        mock_edge_obj.source_type = "User"
        mock_edge_obj.source_id = "alice"
        mock_edge_obj.edge_type = "HAS_MEMORY"
        mock_edge_obj.target_type = "Memory"
        mock_edge_obj.target_id = "mem1"
        mock_edge_obj.properties = {}
        mock_edge_obj.created_at = "2024-01-15T10:02:00"

        mock_node.side_effect = [mock_node_user, mock_node_memory]
        mock_edge.return_value = mock_edge_obj
        mock_neighbors.return_value = [
            {
                "neighbor": {"id": "mem1", "content": "Test memory"},
                "rel_type": "HAS_MEMORY",
            }
        ]

        # 1. Create user node
        resp1 = await client.post(
            "/v1/graph/nodes",
            json={"node_type": "User", "node_id": "alice"},
        )
        assert resp1.status_code == 200

        # 2. Create memory node
        resp2 = await client.post(
            "/v1/graph/nodes",
            json={
                "node_type": "Memory",
                "node_id": "mem1",
                "properties": {"content": "Test memory"},
            },
        )
        assert resp2.status_code == 200

        # 3. Create edge
        resp3 = await client.post(
            "/v1/graph/edges",
            json={
                "source_type": "User",
                "source_id": "alice",
                "edge_type": "HAS_MEMORY",
                "target_type": "Memory",
                "target_id": "mem1",
            },
        )
        assert resp3.status_code == 200

        # 4. Query neighbors
        resp4 = await client.post(
            "/v1/graph/neighbors",
            json={"node_type": "User", "node_id": "alice", "direction": "out"},
        )
        assert resp4.status_code == 200
        data = resp4.json()
        assert data["count"] == 1
