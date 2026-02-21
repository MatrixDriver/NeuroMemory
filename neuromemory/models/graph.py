"""Graph data models (relational tables for nodes and edges)."""

import uuid
from enum import Enum

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from neuromemory.models.base import Base, TimestampMixin


class NodeType(str, Enum):
    USER = "User"
    MEMORY = "Memory"
    CONCEPT = "Concept"
    ENTITY = "Entity"
    PERSON = "Person"  # v0.2.0: For people mentioned in episodes
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    EVENT = "Event"  # v0.2.0: For episode events
    SKILL = "Skill"


class EdgeType(str, Enum):
    HAS_MEMORY = "HAS_MEMORY"
    MENTIONS = "MENTIONS"
    RELATED_TO = "RELATED_TO"
    KNOWS = "KNOWS"
    ABOUT = "ABOUT"
    WORKS_AT = "WORKS_AT"
    LIVES_IN = "LIVES_IN"
    HAS_SKILL = "HAS_SKILL"
    STUDIED_AT = "STUDIED_AT"
    BELONGS_TO = "BELONGS_TO"
    USES = "USES"
    # Episode-specific relations (v0.2.0)
    MET = "MET"  # user met someone
    ATTENDED = "ATTENDED"  # user attended an event
    VISITED = "VISITED"  # user visited a place
    OCCURRED_AT = "OCCURRED_AT"  # episode occurred at a location
    OCCURRED_ON = "OCCURRED_ON"  # episode occurred on a date
    CUSTOM = "CUSTOM"


class GraphNode(Base, TimestampMixin):
    """Graph node table."""

    __tablename__ = "graph_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        # 修复：唯一索引必须包含 user_id，否则不同用户无法创建相同的节点
        # 例如：两个用户都去"前海滑雪场"时，应该各自创建独立的节点
        Index("ix_graph_nodes_lookup", "user_id", "node_type", "node_id", unique=True),
    )


class GraphEdge(Base, TimestampMixin):
    """Graph edge table."""

    __tablename__ = "graph_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        # 修复：索引包含 user_id 以确保用户隔离和性能
        Index(
            "ix_graph_edges_lookup",
            "user_id",
            "source_type", "source_id",
            "edge_type",
            "target_type", "target_id",
        ),
    )
