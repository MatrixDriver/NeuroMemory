"""Graph data models for Apache AGE integration."""

import uuid
from enum import Enum

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base, TimestampMixin


class NodeType(str, Enum):
    """Graph node types."""

    USER = "User"
    MEMORY = "Memory"
    CONCEPT = "Concept"
    ENTITY = "Entity"


class EdgeType(str, Enum):
    """Graph edge types."""

    HAS_MEMORY = "HAS_MEMORY"
    MENTIONS = "MENTIONS"
    RELATED_TO = "RELATED_TO"
    KNOWS = "KNOWS"
    ABOUT = "ABOUT"


class GraphNode(Base, TimestampMixin):
    """
    Graph node tracking table.

    This table tracks nodes created in the AGE graph for reference and
    multi-tenant isolation. The actual graph data is stored in AGE.
    """

    __tablename__ = "graph_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    node_id: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_graph_nodes_lookup", "tenant_id", "node_type", "node_id", unique=True),
    )


class GraphEdge(Base, TimestampMixin):
    """
    Graph edge tracking table.

    This table tracks edges created in the AGE graph for reference and
    multi-tenant isolation. The actual graph data is stored in AGE.
    """

    __tablename__ = "graph_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    edge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_graph_edges_lookup",
            "tenant_id",
            "source_type",
            "source_id",
            "edge_type",
            "target_type",
            "target_id",
        ),
    )
