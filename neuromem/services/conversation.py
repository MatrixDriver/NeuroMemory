"""Conversation service for session management."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.conversation import Conversation, ConversationSession

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Conversation:
        """Add a single conversation message."""
        if session_id is None:
            session_id = f"session_{uuid4().hex[:16]}"

        message = Conversation(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata_=metadata,
        )

        self.db.add(message)
        await self.db.flush()

        await self._update_session_metadata(user_id=user_id, session_id=session_id)

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def add_messages_batch(
        self,
        user_id: str,
        messages: list[dict],
        session_id: Optional[str] = None,
    ) -> tuple[str, list[UUID]]:
        """Add multiple messages in batch."""
        if session_id is None:
            session_id = f"session_{uuid4().hex[:16]}"

        message_objects = []
        for msg in messages:
            message = Conversation(
                user_id=user_id,
                session_id=session_id,
                role=msg["role"],
                content=msg["content"],
                metadata_=msg.get("metadata"),
            )
            message_objects.append(message)
            self.db.add(message)

        await self.db.flush()
        message_ids = [msg.id for msg in message_objects]

        await self._update_session_metadata(user_id=user_id, session_id=session_id)
        await self.db.commit()

        return session_id, message_ids

    async def get_session_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Conversation]:
        """Get messages from a specific session."""
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.session_id == session_id,
                )
            )
            .order_by(Conversation.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[ConversationSession]]:
        """List all conversation sessions for a user."""
        count_stmt = (
            select(func.count())
            .select_from(ConversationSession)
            .where(ConversationSession.user_id == user_id)
        )
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(ConversationSession)
            .where(ConversationSession.user_id == user_id)
            .order_by(desc(ConversationSession.last_message_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        sessions = result.scalars().all()
        return total, list(sessions)

    async def get_unextracted_messages(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[Conversation]:
        """Get messages not yet processed for memory extraction."""
        conditions = [
            Conversation.user_id == user_id,
            Conversation.extraction_status == "pending",
        ]

        if session_id:
            conditions.append(Conversation.session_id == session_id)

        stmt = (
            select(Conversation)
            .where(and_(*conditions))
            .order_by(Conversation.created_at.asc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def mark_messages_extracted(
        self,
        message_ids: list[UUID],
        task_id: Optional[str] = None,
    ) -> int:
        """Mark messages as successfully extracted."""
        stmt = (
            update(Conversation)
            .where(Conversation.id.in_(message_ids))
            .values(
                extracted=True,
                extraction_task_id=task_id,
                extraction_status="done",
                extraction_error=None,
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def mark_messages_failed(
        self,
        message_ids: list[UUID],
        error: str,
    ) -> int:
        """Mark messages as failed extraction, incrementing retry count."""
        stmt = (
            update(Conversation)
            .where(Conversation.id.in_(message_ids))
            .values(
                extraction_status="failed",
                extraction_error=error,
                extraction_retries=Conversation.extraction_retries + 1,
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def get_failed_messages(
        self,
        user_id: Optional[str] = None,
        max_retries: int = 3,
        limit: int = 100,
    ) -> list[Conversation]:
        """Get messages that failed extraction and are eligible for retry."""
        conditions = [
            Conversation.extraction_status == "failed",
            Conversation.extraction_retries < max_retries,
        ]
        if user_id:
            conditions.append(Conversation.user_id == user_id)

        stmt = (
            select(Conversation)
            .where(and_(*conditions))
            .order_by(Conversation.created_at.asc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _update_session_metadata(
        self,
        user_id: str,
        session_id: str,
    ) -> None:
        """Update or create session metadata."""
        existing_stmt = select(ConversationSession).where(
            and_(
                ConversationSession.user_id == user_id,
                ConversationSession.session_id == session_id,
            )
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()

        count_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.session_id == session_id,
                )
            )
        )
        message_count = await self.db.scalar(count_stmt) or 0

        last_msg_stmt = (
            select(Conversation.created_at)
            .where(
                and_(
                    Conversation.user_id == user_id,
                    Conversation.session_id == session_id,
                )
            )
            .order_by(desc(Conversation.created_at))
            .limit(1)
        )
        result = await self.db.execute(last_msg_stmt)
        last_message_at = result.scalar_one_or_none()

        if existing:
            existing.message_count = message_count
            existing.last_message_at = last_message_at
            existing.updated_at = datetime.now(timezone.utc)
        else:
            session = ConversationSession(
                user_id=user_id,
                session_id=session_id,
                message_count=message_count,
                last_message_at=last_message_at,
            )
            self.db.add(session)

        await self.db.flush()
