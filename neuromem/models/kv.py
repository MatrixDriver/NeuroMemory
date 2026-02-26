"""Key-Value storage model (JSONB values with namespace partitioning)."""

import uuid

from sqlalchemy import Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from neuromem.models.base import Base, TimestampMixin


class KeyValue(Base, TimestampMixin):
    __tablename__ = "key_values"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(255), nullable=False)
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        Index(
            "ix_kv_lookup",
            "namespace", "scope_id", "key",
            unique=True,
        ),
        Index(
            "ix_kv_ns_scope",
            "namespace", "scope_id",
        ),
    )
