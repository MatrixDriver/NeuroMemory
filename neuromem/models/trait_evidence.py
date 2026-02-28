"""Trait evidence model - evidence chain for trait memories."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from neuromem.models.base import Base


class TraitEvidence(Base):
    __tablename__ = "trait_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    trait_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(15), nullable=False)
    quality: Mapped[str] = mapped_column(String(1), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('supporting', 'contradicting')",
            name="chk_evidence_type",
        ),
        CheckConstraint("quality IN ('A', 'B', 'C', 'D')", name="chk_quality"),
        Index("idx_evidence_trait", "trait_id", "evidence_type"),
        Index("idx_evidence_memory", "memory_id"),
    )
