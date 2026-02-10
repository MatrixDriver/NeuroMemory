"""Conversation API endpoints"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas_conversation import (
    AutoExtractConfig,
    ConversationBatchRequest,
    ConversationBatchResponse,
    ConversationHistoryResponse,
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationSessionListResponse,
    ConversationSessionResponse,
    ExtractMemoriesRequest,
    ExtractMemoriesResponse,
)
from server.app.db.session import get_db
from server.app.services.auth import get_current_tenant
from server.app.services.conversation import ConversationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/messages", response_model=ConversationMessageResponse)
async def add_conversation_message(
    request: ConversationMessageRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Add a single conversation message

    This endpoint adds one message to a conversation session.
    If no session_id is provided, a new session will be created.

    **Example:**
    ```json
    {
        "user_id": "alice",
        "role": "user",
        "content": "I work at Google",
        "metadata": {"timestamp": "2024-01-15T10:00:00"}
    }
    ```
    """
    service = ConversationService(db)

    try:
        message = await service.add_message(
            tenant_id=tenant_id,
            user_id=request.user_id,
            role=request.role,
            content=request.content,
            session_id=request.session_id,
            metadata=request.metadata,
        )

        # Manually construct response to handle metadata_ field
        return ConversationMessageResponse(
            id=message.id,
            user_id=message.user_id,
            session_id=message.session_id,
            role=message.role,
            content=message.content,
            metadata_=message.metadata_,
            extracted=message.extracted,
            created_at=message.created_at,
        )

    except Exception as e:
        logger.error(f"Failed to add message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=ConversationBatchResponse)
async def add_conversation_batch(
    request: ConversationBatchRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Add multiple conversation messages in batch

    More efficient than adding messages one by one.
    All messages will be added to the same session.

    **Example:**
    ```json
    {
        "user_id": "alice",
        "messages": [
            {"role": "user", "content": "What's the weather?"},
            {"role": "assistant", "content": "It's sunny today!"}
        ]
    }
    ```
    """
    service = ConversationService(db)

    try:
        # Convert MessageCreate to dict
        messages = [
            {
                "role": msg.role,
                "content": msg.content,
                "metadata": msg.metadata,
            }
            for msg in request.messages
        ]

        session_id, message_ids = await service.add_messages_batch(
            tenant_id=tenant_id,
            user_id=request.user_id,
            messages=messages,
            session_id=request.session_id,
        )

        return ConversationBatchResponse(
            session_id=session_id,
            messages_added=len(message_ids),
            message_ids=message_ids,
        )

    except Exception as e:
        logger.error(f"Failed to add batch messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    session_id: str,
    user_id: Annotated[str, Query(description="User identifier")],
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=500, description="Maximum messages to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Get conversation history for a specific session

    Returns all messages in chronological order.

    **Query Parameters:**
    - user_id: User identifier (required)
    - limit: Maximum number of messages (default: 100)
    - offset: Pagination offset (default: 0)
    """
    service = ConversationService(db)

    try:
        messages = await service.get_session_messages(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            offset=offset,
        )

        message_responses = [
            ConversationMessageResponse.model_validate(msg)
            for msg in messages
        ]

        return ConversationHistoryResponse(
            session_id=session_id,
            message_count=len(message_responses),
            messages=message_responses,
        )

    except Exception as e:
        logger.error(f"Failed to get conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=ConversationSessionListResponse)
async def list_conversation_sessions(
    user_id: Annotated[str, Query(description="User identifier")],
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200, description="Maximum sessions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """List all conversation sessions for a user

    Returns sessions ordered by last message time (most recent first).

    **Query Parameters:**
    - user_id: User identifier (required)
    - limit: Maximum number of sessions (default: 50)
    - offset: Pagination offset (default: 0)
    """
    service = ConversationService(db)

    try:
        total, sessions = await service.list_sessions(
            tenant_id=tenant_id,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

        session_responses = [
            ConversationSessionResponse.model_validate(s)
            for s in sessions
        ]

        return ConversationSessionListResponse(
            total=total,
            sessions=session_responses,
        )

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auto-extract", response_model=dict)
async def enable_auto_extract(
    config: AutoExtractConfig,
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Enable automatic memory extraction

    Configure automatic extraction of memories from conversations.
    The system will periodically extract preferences, facts, and episodes
    from conversation messages.

    **Triggers:**
    - message_count: Extract after N messages
    - time_interval: Extract every N minutes

    **Example:**
    ```json
    {
        "user_id": "alice",
        "trigger": "message_count",
        "threshold": 10,
        "async_mode": true
    }
    ```

    **Note:** This is a configuration endpoint. The actual extraction
    will be implemented in Phase 1.2 (LLM Classifier).
    """
    # TODO: Implement auto-extraction configuration storage
    # For now, just acknowledge the request

    logger.info(
        f"Auto-extraction configured for user {config.user_id}: "
        f"trigger={config.trigger}, threshold={config.threshold}"
    )

    return {
        "status": "configured",
        "user_id": config.user_id,
        "trigger": config.trigger,
        "threshold": config.threshold,
        "message": "Auto-extraction will be implemented in Phase 1.2"
    }


@router.post("/extract", response_model=ExtractMemoriesResponse)
async def extract_memories(
    request: ExtractMemoriesRequest,
    tenant_id: Annotated[UUID, Depends(get_current_tenant)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Manually trigger memory extraction from conversations

    Extract preferences, facts, and episodes from conversation messages
    using LLM classification.

    **Example:**
    ```json
    {
        "user_id": "alice",
        "session_id": "session_123",
        "force": false
    }
    ```

    **Note:** LLM Classifier will be implemented in Phase 1.2.
    This endpoint currently returns a placeholder response.
    """
    service = ConversationService(db)

    try:
        # Get unextracted messages
        messages = await service.get_unextracted_messages(
            tenant_id=tenant_id,
            user_id=request.user_id,
            session_id=request.session_id,
            limit=100,
        )

        # TODO: Implement LLM-based extraction in Phase 1.2
        # For now, just return the count

        logger.info(
            f"Memory extraction requested for user {request.user_id}, "
            f"found {len(messages)} unextracted messages"
        )

        return ExtractMemoriesResponse(
            status="pending",
            messages_processed=len(messages),
            preferences_extracted=0,
            facts_extracted=0,
            episodes_extracted=0,
            documents_extracted=0,
        )

    except Exception as e:
        logger.error(f"Failed to extract memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))
