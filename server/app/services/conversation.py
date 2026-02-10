"""Conversation service for session management"""

import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.conversation import Conversation, ConversationSession

logger = logging.getLogger(__name__)


class ConversationService:
    """Service for managing conversation sessions and messages"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_message(
        self,
        tenant_id: UUID,
        user_id: str,
        role: str,
        content: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Conversation:
        """Add a single conversation message

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            role: Message role (user/assistant/system)
            content: Message content
            session_id: Session ID (auto-generated if None)
            metadata: Additional metadata

        Returns:
            Created conversation message
        """
        # Generate session_id if not provided
        if session_id is None:
            session_id = f"session_{uuid4().hex[:16]}"

        # Create message
        message = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata_=metadata,
        )

        self.db.add(message)
        await self.db.flush()

        # Update session metadata
        await self._update_session_metadata(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id
        )

        await self.db.commit()
        await self.db.refresh(message)

        logger.info(f"Added message to session {session_id} for user {user_id}")
        return message

    async def add_messages_batch(
        self,
        tenant_id: UUID,
        user_id: str,
        messages: List[dict],
        session_id: Optional[str] = None,
    ) -> tuple[str, List[UUID]]:
        """Add multiple messages in batch

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            messages: List of message dicts with 'role', 'content', 'metadata'
            session_id: Session ID (auto-generated if None)

        Returns:
            Tuple of (session_id, list of message IDs)
        """
        # Generate session_id if not provided
        if session_id is None:
            session_id = f"session_{uuid4().hex[:16]}"

        # Create message objects
        message_objects = []
        message_ids = []

        for msg in messages:
            message = Conversation(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                role=msg["role"],
                content=msg["content"],
                metadata_=msg.get("metadata"),
            )
            message_objects.append(message)
            self.db.add(message)

        # Flush to get IDs
        await self.db.flush()

        # Collect IDs
        message_ids = [msg.id for msg in message_objects]

        # Update session metadata
        await self._update_session_metadata(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id
        )

        await self.db.commit()

        logger.info(
            f"Added {len(messages)} messages to session {session_id} "
            f"for user {user_id}"
        )

        return session_id, message_ids

    async def get_session_messages(
        self,
        tenant_id: UUID,
        user_id: str,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Conversation]:
        """Get messages from a specific session

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            session_id: Session ID
            limit: Maximum number of messages
            offset: Offset for pagination

        Returns:
            List of conversation messages
        """
        stmt = (
            select(Conversation)
            .where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.session_id == session_id,
                )
            )
            .order_by(Conversation.created_at.asc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        return list(messages)

    async def list_sessions(
        self,
        tenant_id: UUID,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, List[ConversationSession]]:
        """List all conversation sessions for a user

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            limit: Maximum number of sessions
            offset: Offset for pagination

        Returns:
            Tuple of (total count, list of sessions)
        """
        # Count total
        count_stmt = (
            select(func.count())
            .select_from(ConversationSession)
            .where(
                and_(
                    ConversationSession.tenant_id == tenant_id,
                    ConversationSession.user_id == user_id,
                )
            )
        )
        total = await self.db.scalar(count_stmt) or 0

        # Get sessions
        stmt = (
            select(ConversationSession)
            .where(
                and_(
                    ConversationSession.tenant_id == tenant_id,
                    ConversationSession.user_id == user_id,
                )
            )
            .order_by(desc(ConversationSession.last_message_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        sessions = result.scalars().all()

        return total, list(sessions)

    async def get_session_info(
        self,
        tenant_id: UUID,
        user_id: str,
        session_id: str,
    ) -> Optional[ConversationSession]:
        """Get session metadata

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            session_id: Session ID

        Returns:
            Session metadata or None if not found
        """
        stmt = (
            select(ConversationSession)
            .where(
                and_(
                    ConversationSession.tenant_id == tenant_id,
                    ConversationSession.user_id == user_id,
                    ConversationSession.session_id == session_id,
                )
            )
        )

        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()

        return session

    async def get_unextracted_messages(
        self,
        tenant_id: UUID,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Conversation]:
        """Get messages that haven't been processed for memory extraction

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            session_id: Optional session ID filter
            limit: Maximum number of messages

        Returns:
            List of unextracted messages
        """
        conditions = [
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.extracted == False,  # noqa: E712
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
        messages = result.scalars().all()

        return list(messages)

    async def mark_messages_extracted(
        self,
        message_ids: List[UUID],
        task_id: Optional[str] = None,
    ) -> int:
        """Mark messages as extracted

        Args:
            message_ids: List of message IDs
            task_id: Optional extraction task ID

        Returns:
            Number of messages updated
        """
        from sqlalchemy import update

        stmt = (
            update(Conversation)
            .where(Conversation.id.in_(message_ids))
            .values(
                extracted=True,
                extraction_task_id=task_id,
            )
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        return result.rowcount

    async def _update_session_metadata(
        self,
        tenant_id: UUID,
        user_id: str,
        session_id: str,
    ) -> None:
        """Update or create session metadata

        Args:
            tenant_id: Tenant UUID
            user_id: User identifier
            session_id: Session ID
        """
        # Check if session exists
        existing = await self.get_session_info(tenant_id, user_id, session_id)

        # Count messages in session
        count_stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.session_id == session_id,
                )
            )
        )
        message_count = await self.db.scalar(count_stmt) or 0

        # Get last message time
        last_msg_stmt = (
            select(Conversation.created_at)
            .where(
                and_(
                    Conversation.tenant_id == tenant_id,
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
            # Update existing session
            existing.message_count = message_count
            existing.last_message_at = last_message_at
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new session
            session = ConversationSession(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                message_count=message_count,
                last_message_at=last_message_at,
            )
            self.db.add(session)

        await self.db.flush()
