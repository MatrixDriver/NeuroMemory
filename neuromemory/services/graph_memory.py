"""Graph memory service - Store and query entity-relation triples."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select, text
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
        self._created_nodes: set[tuple[str, str, str]] = set()

        # Pre-parse all valid triples and collect needed nodes
        parsed: list[tuple] = []
        needed_nodes: set[tuple[NodeType, str, str]] = set()

        for triple in triples:
            subject = triple.get("subject", "").strip()
            obj = triple.get("object", "").strip()
            relation = triple.get("relation", "").strip()
            if not subject or not obj or not relation:
                continue

            stype = _resolve_node_type(triple.get("subject_type", "entity"))
            otype = _resolve_node_type(triple.get("object_type", "entity"))
            etype = _resolve_edge_type(relation)
            sid = user_id if stype == NodeType.USER else _normalize_node_id(subject)
            oid = _normalize_node_id(obj)

            needed_nodes.add((stype, sid, subject))
            needed_nodes.add((otype, oid, obj))
            parsed.append((triple, stype, sid, otype, oid, etype, relation))

        if not parsed:
            self._created_nodes = set()
            return 0

        # Batch ensure all nodes exist (1 DB query instead of 2N)
        await self._ensure_nodes_batch(user_id, needed_nodes)

        count = 0
        for triple, stype, sid, otype, oid, etype, relation in parsed:
            try:
                stored = await self._store_single_triple(
                    user_id, triple, stype, sid, otype, oid, etype, relation,
                )
                if stored:
                    count += 1
            except Exception as e:
                logger.error("Failed to store triple %s: %s", triple, e, exc_info=True)

        self._created_nodes = set()
        return count

    async def _ensure_nodes_batch(
        self,
        user_id: str,
        needed_nodes: set[tuple[NodeType, str, str]],
    ) -> None:
        """Batch get-or-create nodes (1 DB query instead of 2N individual checks)."""
        if not needed_nodes:
            return

        # Filter out nodes already created in this batch
        to_check = [
            (nt, nid, name) for nt, nid, name in needed_nodes
            if (user_id, nt.value, nid) not in self._created_nodes
        ]
        if not to_check:
            return

        # Single query for all needed node IDs
        node_id_set = {nid for _, nid, _ in to_check}
        result = await self.db.execute(
            select(GraphNode.node_type, GraphNode.node_id).where(
                GraphNode.user_id == user_id,
                GraphNode.node_id.in_(node_id_set),
            )
        )
        existing = {(row.node_type, row.node_id) for row in result.fetchall()}

        # Insert only missing nodes
        for node_type, node_id, name in to_check:
            if (node_type.value, node_id) not in existing:
                self.db.add(GraphNode(
                    user_id=user_id,
                    node_type=node_type.value,
                    node_id=node_id,
                    properties={"name": name},
                ))
                logger.debug("添加节点到 session: %s:%s", node_type.value, node_id)
            self._created_nodes.add((user_id, node_type.value, node_id))

    async def _store_single_triple(
        self,
        user_id: str,
        triple: dict[str, Any],
        stype: NodeType,
        sid: str,
        otype: NodeType,
        oid: str,
        etype: EdgeType,
        relation: str,
    ) -> bool:
        """Store a single pre-parsed triple. Returns True if edge was created or updated."""
        content = triple.get("content", "")
        confidence = triple.get("confidence", 1.0)
        now = datetime.now(timezone.utc).isoformat()

        action = await self._resolve_conflict(user_id, stype, sid, etype, otype, oid, content)

        if action == "NOOP":
            return False

        if action == "UPDATE":
            await self._invalidate_existing_edges(user_id, stype, sid, etype, now)

        edge_props: dict[str, Any] = {
            "content": content,
            "confidence": confidence,
            "valid_from": now,
            "valid_until": None,
        }
        if etype == EdgeType.CUSTOM:
            edge_props["relation_name"] = relation

        self.db.add(GraphEdge(
            user_id=user_id,
            source_type=stype.value,
            source_id=sid,
            edge_type=etype.value,
            target_type=otype.value,
            target_id=oid,
            properties=edge_props,
        ))
        return True

    async def _ensure_node(
        self,
        node_type: NodeType,
        node_id: str,
        user_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Get-or-create a single node (kept for backward compatibility)."""
        node_key = (user_id, node_type.value, node_id)
        if hasattr(self, '_created_nodes') and node_key in self._created_nodes:
            return

        result = await self.db.execute(
            select(GraphNode).where(
                GraphNode.user_id == user_id,
                GraphNode.node_type == node_type.value,
                GraphNode.node_id == node_id,
            )
        )
        if result.scalar_one_or_none():
            return

        self.db.add(GraphNode(
            user_id=user_id,
            node_type=node_type.value,
            node_id=node_id,
            properties=properties,
        ))
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
                text("(properties->>'valid_until') IS NULL"),
            )
        )
        active = result.scalars().all()

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
                text("(properties->>'valid_until') IS NULL"),
            )
        )
        for edge in result.scalars().all():
            props = edge.properties or {}
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

        # Single query covers both outgoing and incoming edges, active only
        result = await self.db.execute(
            select(GraphEdge).where(
                GraphEdge.user_id == user_id,
                or_(GraphEdge.source_id == node_id, GraphEdge.target_id == node_id),
                text("(properties->>'valid_until') IS NULL"),
            ).limit(limit)
        )

        results: list[dict[str, Any]] = []
        for edge in result.scalars().all():
            props = edge.properties or {}
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

        return results
