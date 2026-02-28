"""Reflection cycle model - records of reflection engine runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from neuromem.models.base import Base


class ReflectionCycle(Base):
    __tablename__ = "reflection_cycles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    memories_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    traits_created: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    traits_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    traits_dissolved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="running", server_default="'running'"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_reflection_user", "user_id", "started_at"),
    )
