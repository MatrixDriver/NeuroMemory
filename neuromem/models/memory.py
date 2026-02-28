"""Memory model (formerly Embedding)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

import neuromem.models as _models
from neuromem.models.base import Base, TimestampMixin


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(
        HALFVEC(_models._embedding_dims), nullable=False
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), default="fact"
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

    # Bi-temporal timeline
    valid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invalid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Importance
    importance: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5", nullable=False)

    # Deduplication
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Trait-specific columns
    trait_subtype: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trait_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trait_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    trait_context: Mapped[str | None] = mapped_column(String(20), nullable=True)
    trait_parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    trait_reinforcement_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trait_contradiction_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    trait_last_reinforced: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trait_first_observed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trait_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trait_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trait_derived_from: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Entity association
    subject_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    object_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Conversation provenance
    source_episode_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)

    __table_args__ = (
        CheckConstraint("memory_type IN ('fact', 'episodic', 'trait', 'document')", name="chk_memory_type"),
        Index("ix_mem_user", "user_id"),
        Index("ix_mem_user_ts", "user_id", "extracted_timestamp"),
        Index("ix_mem_type_user", "user_id", "memory_type"),
        Index("ix_mem_user_valid", "user_id", "valid_from", "valid_until"),
    )

    @classmethod
    def __declare_last__(cls):
        """Set vector dimension from runtime config after all models declared."""
        cls.__table__.c.embedding.type = HALFVEC(_models._embedding_dims)


# Backward compatibility alias
Embedding = Memory
