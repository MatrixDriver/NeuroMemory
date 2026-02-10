"""Graph database client for NeuroMemory SDK."""

from __future__ import annotations

from typing import Any

import httpx


class GraphClient:
    """Client for graph database operations.

    This client provides methods for managing nodes and edges in the
    Apache AGE-powered graph database.

    Usage:
        client.graph.create_node(
            user_id="alice",
            node_type="Memory",
            node_id="mem_1",
            properties={"content": "Important meeting"}
        )

        client.graph.create_edge(
            user_id="alice",
            source_type="User",
            source_id="alice",
            edge_type="HAS_MEMORY",
            target_type="Memory",
            target_id="mem_1"
        )
    """

    def __init__(self, http: httpx.Client):
        self._http = http

    def create_node(
        self,
        user_id: str,
        node_type: str,
        node_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """Create a node in the graph.

        Args:
            user_id: User ID for tenant isolation
            node_type: Type of node (User, Memory, Concept, Entity)
            node_id: Unique identifier for the node
            properties: Optional node properties

        Returns:
            Created node metadata

        Raises:
            httpx.HTTPStatusError: If creation fails
        """
        resp = self._http.post(
            "/graph/nodes",
            json={
                "user_id": user_id,
                "node_type": node_type,
                "node_id": node_id,
                "properties": properties or {},
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_node(
        self,
        user_id: str,
        node_type: str,
        node_id: str,
    ) -> dict | None:
        """Get a node by type and ID.

        Args:
            user_id: User ID for tenant isolation
            node_type: Type of node
            node_id: Node ID

        Returns:
            Node data or None if not found
        """
        resp = self._http.get(
            f"/graph/nodes/{node_type}/{node_id}",
            params={"user_id": user_id},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def update_node(
        self,
        user_id: str,
        node_type: str,
        node_id: str,
        properties: dict[str, Any],
    ) -> dict:
        """Update node properties.

        Args:
            user_id: User ID for tenant isolation
            node_type: Type of node
            node_id: Node ID
            properties: Properties to update (merges with existing)

        Returns:
            Updated node metadata

        Raises:
            httpx.HTTPStatusError: If update fails
        """
        resp = self._http.put(
            f"/graph/nodes/{node_type}/{node_id}",
            json={
                "user_id": user_id,
                "properties": properties,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def delete_node(
        self,
        user_id: str,
        node_type: str,
        node_id: str,
    ) -> None:
        """Delete a node and all its edges.

        Args:
            user_id: User ID for tenant isolation
            node_type: Type of node
            node_id: Node ID

        Raises:
            httpx.HTTPStatusError: If deletion fails
        """
        resp = self._http.delete(
            f"/graph/nodes/{node_type}/{node_id}",
            params={"user_id": user_id},
        )
        resp.raise_for_status()

    def create_edge(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        edge_type: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict:
        """Create an edge between two nodes.

        Args:
            user_id: User ID for tenant isolation
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge (HAS_MEMORY, MENTIONS, RELATED_TO, etc.)
            target_type: Target node type
            target_id: Target node ID
            properties: Optional edge properties

        Returns:
            Created edge metadata

        Raises:
            httpx.HTTPStatusError: If creation fails
        """
        resp = self._http.post(
            "/graph/edges",
            json={
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "edge_type": edge_type,
                "target_type": target_type,
                "target_id": target_id,
                "properties": properties or {},
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_edge(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        edge_type: str,
        target_type: str,
        target_id: str,
    ) -> dict | None:
        """Get an edge between two nodes.

        Args:
            user_id: User ID for tenant isolation
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID

        Returns:
            Edge data or None if not found
        """
        resp = self._http.get(
            f"/graph/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}",
            params={"user_id": user_id},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def update_edge(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        edge_type: str,
        target_type: str,
        target_id: str,
        properties: dict[str, Any],
    ) -> dict:
        """Update edge properties.

        Args:
            user_id: User ID for tenant isolation
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID
            properties: Properties to update (merges with existing)

        Returns:
            Updated edge metadata

        Raises:
            httpx.HTTPStatusError: If update fails
        """
        resp = self._http.put(
            f"/graph/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}",
            json={
                "user_id": user_id,
                "properties": properties,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def delete_edge(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        edge_type: str,
        target_type: str,
        target_id: str,
    ) -> None:
        """Delete an edge.

        Args:
            user_id: User ID for tenant isolation
            source_type: Source node type
            source_id: Source node ID
            edge_type: Type of edge
            target_type: Target node type
            target_id: Target node ID

        Raises:
            httpx.HTTPStatusError: If deletion fails
        """
        resp = self._http.delete(
            f"/graph/edges/{source_type}/{source_id}/{edge_type}/{target_type}/{target_id}",
            params={"user_id": user_id},
        )
        resp.raise_for_status()

    def get_neighbors(
        self,
        user_id: str,
        node_type: str,
        node_id: str,
        edge_types: list[str] | None = None,
        direction: str = "both",
        limit: int = 10,
    ) -> list[dict]:
        """Get neighboring nodes.

        Args:
            user_id: User ID for tenant isolation
            node_type: Type of node
            node_id: Node ID
            edge_types: Filter by edge types (optional)
            direction: Direction of edges ("in", "out", "both")
            limit: Maximum number of neighbors

        Returns:
            List of neighbor nodes with relationship info

        Raises:
            httpx.HTTPStatusError: If query fails
        """
        resp = self._http.post(
            "/graph/neighbors",
            json={
                "user_id": user_id,
                "node_type": node_type,
                "node_id": node_id,
                "edge_types": edge_types,
                "direction": direction,
                "limit": limit,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def find_path(
        self,
        user_id: str,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = 3,
    ) -> list[dict]:
        """Find shortest path between two nodes.

        Args:
            user_id: User ID for tenant isolation
            source_type: Source node type
            source_id: Source node ID
            target_type: Target node type
            target_id: Target node ID
            max_depth: Maximum path length (1-10)

        Returns:
            List of paths with nodes and edges

        Raises:
            httpx.HTTPStatusError: If query fails
        """
        resp = self._http.post(
            "/graph/paths",
            json={
                "user_id": user_id,
                "source_type": source_type,
                "source_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "max_depth": max_depth,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def query(
        self,
        user_id: str,
        cypher: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Execute a custom Cypher query.

        The query must include tenant_id filter for security.

        Args:
            user_id: User ID for tenant isolation
            cypher: Cypher query string (must include tenant_id filter)
            params: Query parameters

        Returns:
            Query results

        Raises:
            httpx.HTTPStatusError: If query fails or doesn't include tenant_id
        """
        resp = self._http.post(
            "/graph/query",
            json={
                "user_id": user_id,
                "cypher": cypher,
                "params": params or {},
            },
        )
        resp.raise_for_status()
        return resp.json()
