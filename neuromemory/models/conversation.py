"""Conversation models for session storage."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

import neuromemory.models as _models
from neuromemory.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """Single conversation message."""

    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(_models._embedding_dims), nullable=True  # v0.2.0: Store conversation embeddings for recall
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    extracted: Mapped[bool] = mapped_column(
        default=False, server_default=text("false")
    )
    extraction_task_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True
    )

    __table_args__ = (
        Index("idx_conversations_session", "user_id", "session_id"),
        Index("idx_conversations_extraction", "user_id", "extracted"),
    )

    @classmethod
    def __declare_last__(cls):
        """Set vector dimension from runtime config after all models declared."""
        if cls.__table__.c.embedding.type.dim is None:
            cls.__table__.c.embedding.type = Vector(_models._embedding_dims)


class ConversationSession(Base, TimestampMixin):
    """Conversation session metadata."""

    __tablename__ = "conversation_sessions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    __table_args__ = (
        Index("idx_session_user", "user_id"),
    )
