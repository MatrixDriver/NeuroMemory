"""Memory embedding model."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

import neuromem.models as _models
from neuromem.models.base import Base, TimestampMixin


class Embedding(Base, TimestampMixin):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(
        Vector(_models._embedding_dims), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), default="general"
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    access_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    extracted_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Versioning fields for time-travel queries
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False,
    )
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    __table_args__ = (
        Index("ix_emb_user", "user_id"),
        Index("ix_emb_user_ts", "user_id", "extracted_timestamp"),
        Index("ix_emb_type_user", "user_id", "memory_type"),
        Index("ix_emb_user_valid", "user_id", "valid_from", "valid_until"),
    )

    @classmethod
    def __declare_last__(cls):
        """Set vector dimension from runtime config after all models declared."""
        cls.__table__.c.embedding.type = Vector(_models._embedding_dims)
