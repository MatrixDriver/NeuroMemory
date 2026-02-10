"""Search and memory API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.api.v1.schemas import (
    MemoryAdd,
    MemoryResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from server.app.core.logging import get_logger
from server.app.db.session import get_db
from server.app.services.auth import AuthContext, get_auth_context
from server.app.services.search import add_memory, search_memories

router = APIRouter(tags=["search"])
logger = get_logger(__name__)


@router.post("/search", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Semantic search for memories using vector similarity with optional time filtering.

    Converts the query to an embedding and searches for similar memories
    using cosine similarity on vector embeddings. Optionally filter by time range.

    Args:
        body: Search request with query, user_id, optional filters, and time range
        auth: Authentication context (injected)
        db: Database session (injected)

    Returns:
        SearchResponse: List of matching memories with similarity scores

    Raises:
        HTTPException 401: Invalid or missing API key
        HTTPException 500: Embedding service error or database error
    """
    try:
        results = await search_memories(
            db,
            auth.tenant_id,
            body.user_id,
            body.query,
            body.limit,
            body.memory_type,
            body.created_after,
            body.created_before,
        )
        logger.info(
            f"Search completed: {len(results)} results",
            extra={"user_id": body.user_id, "query": body.query[:50]}
        )
        return SearchResponse(
            user_id=body.user_id,
            query=body.query,
            results=[SearchResult(**r) for r in results],
        )
    except Exception as e:
        logger.error(
            f"Search failed: {str(e)}",
            extra={"user_id": body.user_id, "query": body.query[:50]}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/memories", response_model=MemoryResponse)
async def add_mem(
    body: MemoryAdd,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a memory with automatic embedding generation.

    Generates a vector embedding for the content and stores it for
    semantic search.

    Args:
        body: Memory content and optional metadata
        auth: Authentication context (injected)
        db: Database session (injected)

    Returns:
        MemoryResponse: The created memory record

    Raises:
        HTTPException 401: Invalid or missing API key
        HTTPException 500: Embedding service error or database error
    """
    try:
        record = await add_memory(
            db,
            auth.tenant_id,
            body.user_id,
            body.content,
            body.memory_type,
            body.metadata,
        )
        logger.info(
            "Memory added",
            extra={
                "user_id": body.user_id,
                "content_length": len(body.content),
                "memory_type": body.memory_type
            }
        )
        return MemoryResponse(
            id=str(record.id),
            user_id=body.user_id,
            content=record.content,
            memory_type=record.memory_type,
            metadata=record.metadata_,
            created_at=record.created_at,
        )
    except Exception as e:
        logger.error(
            f"Failed to add memory: {str(e)}",
            extra={"user_id": body.user_id, "content_length": len(body.content)}
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add memory: {str(e)}"
        )
