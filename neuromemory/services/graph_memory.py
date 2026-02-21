"""Graph memory service - Store and query entity-relation triples."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neuromemory.models.graph import EdgeType, GraphEdge, GraphNode, NodeType

logger = logging.getLogger(__name__)

# Mapping from LLM-extracted type strings to NodeType enums
_NODE_TYPE_MAP: dict[str, NodeType] = {
    "user": NodeType.USER,
    "person": NodeType.ENTITY,
    "organization": NodeType.ORGANIZATION,
    "location": NodeType.LOCATION,
    "skill": NodeType.SKILL,
    "concept": NodeType.CONCEPT,
    "entity": NodeType.ENTITY,
}

# Mapping from relation strings to EdgeType enums
_EDGE_TYPE_MAP: dict[str, EdgeType] = {
    "works_at": EdgeType.WORKS_AT,
    "lives_in": EdgeType.LIVES_IN,
    "has_skill": EdgeType.HAS_SKILL,
    "studied_at": EdgeType.STUDIED_AT,
    "belongs_to": EdgeType.BELONGS_TO,
    "uses": EdgeType.USES,
    "knows": EdgeType.KNOWS,
    "related_to": EdgeType.RELATED_TO,
    "mentions": EdgeType.MENTIONS,
}


def _normalize_node_id(name: str) -> str:
    """Normalize entity name to a stable node ID."""
    return name.strip().lower().replace(" ", "_")


def _resolve_node_type(type_str: str) -> NodeType:
    """Map an LLM-extracted type string to a NodeType enum."""
    return _NODE_TYPE_MAP.get(type_str.lower(), NodeType.ENTITY)


def _resolve_edge_type(relation: str) -> EdgeType:
    """Map an LLM-extracted relation string to an EdgeType enum."""
    return _EDGE_TYPE_MAP.get(relation.lower(), EdgeType.CUSTOM)


class GraphMemoryService:
    """Service for storing LLM-extracted triples into the graph.

    Handles:
    - Idempotent node creation (get-or-create)
    - Heuristic conflict resolution for edges
    - Temporal model with valid_from/valid_until
    - Entity fact queries
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def store_triples(self, user_id: str, triples: list[dict[str, Any]]) -> int:
        """Store a batch of triples into the graph.

        Each triple dict should have:
            subject, subject_type, relation, object, object_type, content, confidence

        Returns:
            Number of triples stored (ADD or UPDATE, not NOOP).
        """
        # 跟踪本批次中已创建的节点，避免重复创建
        # Key: (user_id, node_type, node_id)
        self._created_nodes = set()

        count = 0
        for triple in triples:
            try:
                stored = await self._store_single_triple(user_id, triple)
                if stored:
                    count += 1
            except Exception as e:
                logger.error("Failed to store triple %s: %s", triple, e, exc_info=True)
                # 不在这里 rollback，让调用方统一处理事务
                # 继续处理下一个 triple

        # 清除本批次的节点跟踪
        self._created_nodes = set()
        # 不在这里 flush，让调用方统一 commit 时一起 flush
        return count

    async def _store_single_triple(self, user_id: str, triple: dict[str, Any]) -> bool:
        """Store a single triple. Returns True if a new edge was created or updated."""
        subject = triple.get("subject", "").strip()
        obj = triple.get("object", "").strip()
        relation = triple.get("relation", "").strip()
        if not subject or not obj or not relation:
            return False

        subject_type = _resolve_node_type(triple.get("subject_type", "entity"))
        object_type = _resolve_node_type(triple.get("object_type", "entity"))
        edge_type = _resolve_edge_type(relation)

        # Normalize node IDs: USER type uses user_id directly
        subject_id = user_id if subject_type == NodeType.USER else _normalize_node_id(subject)
        object_id = _normalize_node_id(obj)

        content = triple.get("content", "")
        confidence = triple.get("confidence", 1.0)
        now = datetime.now(timezone.utc).isoformat()

        # Ensure both nodes exist
        await self._ensure_node(subject_type, subject_id, user_id, {"name": subject})
        await self._ensure_node(object_type, object_id, user_id, {"name": obj})

        # Conflict resolution
        action = await self._resolve_conflict(
            user_id, subject_type, subject_id, edge_type, object_type, object_id, content,
        )

        if action == "NOOP":
            return False

        if action == "UPDATE":
            await self._invalidate_existing_edges(
                user_id, subject_type, subject_id, edge_type, now,
            )

        # Create new edge
        edge_props = {
            "content": content,
            "confidence": confidence,
            "valid_from": now,
            "valid_until": None,
        }
        if edge_type == EdgeType.CUSTOM:
            edge_props["relation_name"] = relation

        edge = GraphEdge(
            user_id=user_id,
            source_type=subject_type.value,
            source_id=subject_id,
            edge_type=edge_type.value,
            target_type=object_type.value,
            target_id=object_id,
            properties=edge_props,
        )
        self.db.add(edge)

        return True

    async def _ensure_node(
        self,
        node_type: NodeType,
        node_id: str,
        user_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Get-or-create a node."""
        # 检查本批次是否已创建此节点（避免重复插入）
        node_key = (user_id, node_type.value, node_id)
        if hasattr(self, '_created_nodes') and node_key in self._created_nodes:
            logger.debug(f"节点已在本批次中创建，跳过: {node_type.value}:{node_id}")
            return

        # 修复：查询时必须加上 user_id 过滤，确保用户隔离
        result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        if result.scalar_one_or_none():
            return

        node = GraphNode(
            user_id=user_id,
            node_type=node_type.value,
            node_id=node_id,
            properties=properties,
        )
        self.db.add(node)
        logger.debug(f"添加节点到 session: {node_type.value}:{node_id}")

        # 记录本批次已创建的节点
        if hasattr(self, '_created_nodes'):
            self._created_nodes.add(node_key)

    async def _resolve_conflict(
        self,
        user_id: str,
        subject_type: NodeType,
        subject_id: str,
        edge_type: EdgeType,
        object_type: NodeType,
        object_id: str,
        content: str,
    ) -> str:
        """Determine action for a new triple: ADD, UPDATE, or NOOP.

        Rules:
        - No existing active edge with same subject+relation → ADD
        - Existing active edge with same subject+relation+object → NOOP
        - Existing active edge with same subject+relation but different object → UPDATE
        """
        result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == user_id,
                GraphEdge.source_type == subject_type.value,
                GraphEdge.source_id == subject_id,
                GraphEdge.edge_type == edge_type.value,
            )
        )
        existing_edges = result.scalars().all()

        # Filter to active edges (valid_until is None)
        active = [
            e for e in existing_edges
            if not (e.properties or {}).get("valid_until")
        ]

        if not active:
            return "ADD"

        # Check if any active edge points to the same object
        for edge in active:
            if edge.target_type == object_type.value and edge.target_id == object_id:
                return "NOOP"

        # Same subject+relation but different object → UPDATE (invalidate old)
        return "UPDATE"

    async def _invalidate_existing_edges(
        self,
        user_id: str,
        source_type: NodeType,
        source_id: str,
        edge_type: EdgeType,
        now: str,
    ) -> None:
        """Mark all active edges with given source+relation as invalid."""
        result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == user_id,
                GraphEdge.source_type == source_type.value,
                GraphEdge.source_id == source_id,
                GraphEdge.edge_type == edge_type.value,
            )
        )
        for edge in result.scalars().all():
            props = edge.properties or {}
            if not props.get("valid_until"):
                edge.properties = {**props, "valid_until": now}

    async def find_entity_facts(
        self,
        user_id: str,
        entity_name: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find all active facts related to an entity.

        Searches both outgoing and incoming edges for the entity node.
        Only returns edges where valid_until is None (active).
        """
        node_id = _normalize_node_id(entity_name)
        results: list[dict[str, Any]] = []

        # Search as source
        out_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == user_id,
                GraphEdge.source_id == node_id,
            )
        )
        for edge in out_result.scalars().all():
            props = edge.properties or {}
            if props.get("valid_until"):
                continue
            results.append({
                "subject": edge.source_id,
                "subject_type": edge.source_type,
                "relation": edge.edge_type,
                "object": edge.target_id,
                "object_type": edge.target_type,
                "content": props.get("content", ""),
                "confidence": props.get("confidence", 1.0),
                "valid_from": props.get("valid_from"),
            })

        # Search as target
        in_result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == user_id,
                GraphEdge.target_id == node_id,
            )
        )
        for edge in in_result.scalars().all():
            props = edge.properties or {}
            if props.get("valid_until"):
                continue
            results.append({
                "subject": edge.source_id,
                "subject_type": edge.source_type,
                "relation": edge.edge_type,
                "object": edge.target_id,
                "object_type": edge.target_type,
                "content": props.get("content", ""),
                "confidence": props.get("confidence", 1.0),
                "valid_from": props.get("valid_from"),
            })

        return results[:limit]
