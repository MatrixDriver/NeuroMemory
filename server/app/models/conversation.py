"""Conversation models for session storage"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from server.app.models.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """Conversation message storage

    Stores all conversation messages for session management and memory extraction.
    Each message is a single turn in a conversation (user or assistant).
    """

    __tablename__ = "conversations"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()")
    )

    # Tenant isolation
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    # User identification
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    # Session grouping
    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Session identifier for grouping related messages"
    )

    # Message content
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Message role: user, assistant, system"
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message content"
    )

    # Metadata
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional metadata (timestamp, tags, etc.)"
    )

    # Memory extraction tracking
    extracted: Mapped[bool] = mapped_column(
        default=False,
        server_default=text("false"),
        comment="Whether memories have been extracted from this message"
    )

    extraction_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Background task ID for memory extraction"
    )

    __table_args__ = (
        # Composite index for efficient session queries
        Index(
            'idx_conversations_session',
            'tenant_id', 'user_id', 'session_id'
        ),
        # Index for extraction queries
        Index(
            'idx_conversations_extraction',
            'tenant_id', 'user_id', 'extracted'
        ),
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, session={self.session_id}, role={self.role})>"


class ConversationSession(Base, TimestampMixin):
    """Conversation session metadata

    Tracks session-level information for better organization and querying.
    Optional table for session management.
    """

    __tablename__ = "conversation_sessions"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()")
    )

    # Tenant isolation
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True
    )

    # User identification
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )

    # Session identifier
    session_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True
    )

    # Session metadata
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Session title (auto-generated or user-provided)"
    )

    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Session summary"
    )

    message_count: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        comment="Total number of messages in this session"
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of the last message"
    )

    # Metadata
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSONB,
        nullable=True
    )

    __table_args__ = (
        Index('idx_session_user', 'tenant_id', 'user_id'),
    )

    def __repr__(self) -> str:
        return f"<ConversationSession(id={self.id}, session={self.session_id}, messages={self.message_count})>"
