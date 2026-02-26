"""Graph database service using relational tables."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.graph import EdgeType, GraphEdge, GraphNode, NodeType


class GraphService:
    """Service for managing graph data with relational tables."""

    def __init__(self, db: AsyncSession, user_id: Optional[str] = None):
        self.db = db
        self.user_id = user_id

    def _effective_user_id(self, user_id: Optional[str] = None) -> str:
        """Resolve user_id from parameter or instance default."""
        uid = user_id or self.user_id
        if not uid:
            raise ValueError("user_id is required for graph operations")
        return uid

    async def create_node(
        self,
        node_type: NodeType,
        node_id: str,
        properties: dict[str, Any] = None,
        user_id: Optional[str] = None,
    ) -> GraphNode:
        """Create a node in the graph."""
        effective_user_id = self._effective_user_id(user_id)

        existing = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == effective_user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Node {node_type.value}:{node_id} already exists")

        node = GraphNode(
            user_id=effective_user_id,
            node_type=node_type.value,
            node_id=node_id,
            properties=properties,
        )
        self.db.add(node)
        await self.db.flush()

        return node

    async def create_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        properties: dict[str, Any] = None,
        user_id: Optional[str] = None,
    ) -> GraphEdge:
        """Create an edge between two nodes."""
        effective_user_id = self._effective_user_id(user_id)

        for ntype, nid in [(source_type, source_id), (target_type, target_id)]:
            node = await self.db.execute(
                select(GraphNode).where(
                    GraphNode.user_id == effective_user_id,
                    GraphNode.node_type == ntype.value,
                    GraphNode.node_id == nid,
                )
            )
            if not node.scalar_one_or_none():
                raise ValueError(f"Node {ntype.value}:{nid} not found")

        edge = GraphEdge(
            user_id=effective_user_id,
            source_type=source_type.value,
            source_id=source_id,
            edge_type=edge_type.value,
            target_type=target_type.value,
            target_id=target_id,
            properties=properties,
        )
        self.db.add(edge)
        await self.db.flush()

        return edge

    async def get_neighbors(
        self,
        node_type: NodeType,
        node_id: str,
        edge_types: list[EdgeType] = None,
        direction: str = "both",
        limit: int = 10,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Get neighboring nodes (user-isolated)."""
        effective_user_id = self._effective_user_id(user_id)

        conditions = [GraphEdge.user_id == effective_user_id]

        if edge_types:
            edge_type_values = [et.value for et in edge_types]
            conditions.append(GraphEdge.edge_type.in_(edge_type_values))

        results = []

        if direction in ("out", "both"):
            out_conditions = conditions + [
                GraphEdge.source_type == node_type.value,
                GraphEdge.source_id == node_id,
            ]
            out_result = await self.db.execute(
                select(GraphEdge).where(*out_conditions).limit(limit)
            )
            for edge in out_result.scalars().all():
                props = edge.properties or {}
                rel = props.get("relation_name") if edge.edge_type == "CUSTOM" else edge.edge_type
                results.append({
                    "neighbor_type": edge.target_type,
                    "neighbor_id": edge.target_id,
                    "rel_type": rel,
                    "rel_props": props,
                    "direction": "out",
                })

        if direction in ("in", "both"):
            remaining = limit - len(results)
            if remaining > 0:
                in_conditions = conditions + [
                    GraphEdge.target_type == node_type.value,
                    GraphEdge.target_id == node_id,
                ]
                in_result = await self.db.execute(
                    select(GraphEdge).where(*in_conditions).limit(remaining)
                )
                for edge in in_result.scalars().all():
                    props = edge.properties or {}
                    rel = props.get("relation_name") if edge.edge_type == "CUSTOM" else edge.edge_type
                    results.append({
                        "neighbor_type": edge.source_type,
                        "neighbor_id": edge.source_id,
                        "rel_type": rel,
                        "rel_props": props,
                        "direction": "in",
                    })

        return results

    async def find_path(
        self,
        source_type: NodeType,
        source_id: str,
        target_type: NodeType,
        target_id: str,
        max_depth: int = 3,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Find shortest path between two nodes using BFS on relational tables."""
        effective_user_id = self._effective_user_id(user_id)

        if not isinstance(max_depth, int) or max_depth < 1 or max_depth > 10:
            raise ValueError("max_depth must be an integer between 1 and 10")

        visited = set()
        queue = [(source_type.value, source_id, [])]
        visited.add((source_type.value, source_id))

        while queue:
            current_type, current_id, path = queue.pop(0)

            if current_type == target_type.value and current_id == target_id:
                return [{"nodes": [step["node"] for step in path] + [{"type": current_type, "id": current_id}],
                         "rels": [step["edge"] for step in path]}]

            if len(path) >= max_depth:
                continue

            # Get outgoing edges
            result = await self.db.execute(
                select(GraphEdge).where(
                    GraphEdge.user_id == effective_user_id,
                    GraphEdge.source_type == current_type,
                    GraphEdge.source_id == current_id,
                )
            )
            for edge in result.scalars().all():
                neighbor_key = (edge.target_type, edge.target_id)
                if neighbor_key not in visited:
                    visited.add(neighbor_key)
                    new_path = path + [{
                        "node": {"type": current_type, "id": current_id},
                        "edge": {"type": edge.edge_type, "props": edge.properties},
                    }]
                    queue.append((edge.target_type, edge.target_id, new_path))

            # Get incoming edges
            result = await self.db.execute(
                select(GraphEdge).where(
                    GraphEdge.user_id == effective_user_id,
                    GraphEdge.target_type == current_type,
                    GraphEdge.target_id == current_id,
                )
            )
            for edge in result.scalars().all():
                neighbor_key = (edge.source_type, edge.source_id)
                if neighbor_key not in visited:
                    visited.add(neighbor_key)
                    new_path = path + [{
                        "node": {"type": current_type, "id": current_id},
                        "edge": {"type": edge.edge_type, "props": edge.properties},
                    }]
                    queue.append((edge.source_type, edge.source_id, new_path))

        return []  # No path found

    async def get_node(
        self,
        node_type: NodeType,
        node_id: str,
        user_id: Optional[str] = None,
    ) -> dict | None:
        """Get a single node by type and ID."""
        effective_user_id = self._effective_user_id(user_id)

        result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == effective_user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        node = result.scalar_one_or_none()
        if not node:
            return None

        return {
            "id": str(node.id),
            "node_type": node.node_type,
            "node_id": node.node_id,
            "properties": node.properties,
            "user_id": node.user_id,
        }

    async def update_node(
        self,
        node_type: NodeType,
        node_id: str,
        properties: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> GraphNode:
        """Update node properties."""
        effective_user_id = self._effective_user_id(user_id)

        node_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == effective_user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        node = node_result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node {node_type.value}:{node_id} not found")

        node.properties = {**(node.properties or {}), **properties}
        await self.db.flush()

        return node

    async def delete_node(
        self,
        node_type: NodeType,
        node_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Delete a node and all its edges."""
        effective_user_id = self._effective_user_id(user_id)

        node_result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == effective_user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        node = node_result.scalar_one_or_none()
        if not node:
            raise ValueError(f"Node {node_type.value}:{node_id} not found")

        await self.db.delete(node)
        await self.db.execute(
            delete(GraphEdge).where(
                GraphEdge.user_id == effective_user_id,
                or_(
                    (GraphEdge.source_type == node_type.value) & (GraphEdge.source_id == node_id),
                    (GraphEdge.target_type == node_type.value) & (GraphEdge.target_id == node_id)
                )
            )
        )
        await self.db.flush()

    async def get_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        user_id: Optional[str] = None,
    ) -> dict | None:
        """Get a single edge."""
        effective_user_id = self._effective_user_id(user_id)

        result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == effective_user_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
                GraphEdge.target_type == target_type.value,
                GraphEdge.target_id == target_id,
            )
        )
        edge = result.scalar_one_or_none()
        if not edge:
            return None

        return {
            "id": str(edge.id),
            "source_type": edge.source_type,
            "source_id": edge.source_id,
            "edge_type": edge.edge_type,
            "target_type": edge.target_type,
            "target_id": edge.target_id,
            "properties": edge.properties,
            "user_id": edge.user_id,
        }

    async def update_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        properties: dict[str, Any],
        user_id: Optional[str] = None,
    ) -> GraphEdge:
        """Update edge properties."""
        effective_user_id = self._effective_user_id(user_id)

        edge_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == effective_user_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
                GraphEdge.target_type == target_type.value,
                GraphEdge.target_id == target_id,
            )
        )
        edge = edge_result.scalar_one_or_none()
        if not edge:
            raise ValueError(f"Edge {source_type.value}:{source_id}-[{edge_type.value}]->{target_type.value}:{target_id} not found")

        edge.properties = {**(edge.properties or {}), **properties}
        await self.db.flush()

        return edge

    async def delete_edge(
        self,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        target_type: NodeType,
        target_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Delete an edge."""
        effective_user_id = self._effective_user_id(user_id)

        edge_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == effective_user_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
                GraphEdge.target_type == target_type.value,
                GraphEdge.target_id == target_id,
            )
        )
        edge = edge_result.scalar_one_or_none()
        if not edge:
            raise ValueError(f"Edge {source_type.value}:{source_id}-[{edge_type.value}]->{target_type.value}:{target_id} not found")

        await self.db.delete(edge)
        await self.db.flush()
