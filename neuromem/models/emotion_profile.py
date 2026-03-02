"""Emotion profile model for aggregated user emotional state.

DEPRECATED: This model is deprecated as part of the Profile Unification refactoring.
The emotion_profiles table will be dropped after data migration is complete.
Use profile_view() for emotion data (aggregated from episodic memories).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from neuromem.models.base import Base, TimestampMixin


class EmotionProfile(Base, TimestampMixin):
    """Aggregated emotion profile for a user.

    This table stores both recent emotional state (meso-level) and
    long-term emotional traits (macro-level), aggregated from
    micro-level emotion tags on individual memories.

    Three-layer emotion architecture:
    - Micro: emotion tags on fact/episodic (in metadata_)
    - Meso: latest_state (recent 1-2 weeks)
    - Macro: emotion_insight (long-term traits)
    """

    __tablename__ = "emotion_profiles"

    user_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, nullable=False
    )

    # === Meso-level: Recent emotional state (1-2 weeks) ===
    latest_state: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Recent emotional state summary, e.g., '最近一周工作压力大，情绪低落'"
    )
    latest_state_period: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="Time period for latest_state, e.g., '2026-W06' or '2026-02-05~2026-02-12'"
    )
    latest_state_valence: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Average valence in recent period: -1.0 (negative) to 1.0 (positive)"
    )
    latest_state_arousal: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Average arousal in recent period: 0.0 (calm) to 1.0 (excited)"
    )
    latest_state_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When latest_state was last updated"
    )

    # === Macro-level: Long-term emotional traits ===
    valence_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Long-term average valence: -1.0 (negative) to 1.0 (positive)"
    )
    arousal_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Long-term average arousal: 0.0 (calm) to 1.0 (excited)"
    )
    dominant_emotions: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment='Emotion distribution, e.g., {"焦虑": 0.6, "兴奋": 0.3}'
    )
    emotion_triggers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment='Topic-emotion map, e.g., {"工作": {"valence": -0.5}, "技术": {"valence": 0.7}}'
    )

    # === Reflection watermark ===
    last_reflected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Watermark: max created_at of memories analyzed by reflect(). "
                "Next reflect() only processes memories newer than this."
    )

    # === Provenance ===
    source_memory_ids: Mapped[list | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=True,
        comment="UUIDs of source memories used to generate this profile"
    )
    source_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Number of memories this profile is based on"
    )
