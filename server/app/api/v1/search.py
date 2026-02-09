"""Search and memory API endpoints."""

from fastapi import APIRouter, Depends
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
    """Semantic search for memories using vector similarity."""
    results = await search_memories(
        db,
        auth.tenant_id,
        body.user_id,
        body.query,
        body.limit,
        body.memory_type,
    )
    return SearchResponse(
        user_id=body.user_id,
        query=body.query,
        results=[SearchResult(**r) for r in results],
    )


@router.post("/memories", response_model=MemoryResponse)
async def add_mem(
    body: MemoryAdd,
    auth: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
):
    """Add a memory with automatic embedding generation."""
    record = await add_memory(
        db,
        auth.tenant_id,
        body.user_id,
        body.content,
        body.memory_type,
        body.metadata,
    )
    return MemoryResponse(
        id=str(record.id),
        user_id=body.user_id,
        content=record.content,
        memory_type=record.memory_type,
        metadata=record.metadata_,
        created_at=record.created_at,
    )
