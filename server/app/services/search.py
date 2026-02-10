"""Semantic search service - vector similarity search via pgvector."""

import uuid
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from server.app.models.memory import Embedding
from server.app.services.embedding import get_embedding_service


async def add_memory(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
    content: str,
    memory_type: str = "general",
    metadata: dict | None = None,
) -> Embedding:
    """Add a memory with its embedding vector."""
    embedding_service = get_embedding_service()
    vector = await embedding_service.embed(content)

    record = Embedding(
        tenant_id=tenant_id,
        user_id=user_id,
        content=content,
        embedding=vector,
        memory_type=memory_type,
        metadata_=metadata,
    )
    db.add(record)
    await db.flush()
    return record


async def search_memories(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: str,
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> list[dict]:
    """Semantic search for memories using cosine similarity with optional time filtering.

    Args:
        db: Database session
        tenant_id: Tenant UUID
        user_id: User identifier
        query: Search query text
        limit: Maximum results
        memory_type: Optional memory type filter
        created_after: Optional start time filter
        created_before: Optional end time filter

    Returns:
        List of search results with scores
    """
    embedding_service = get_embedding_service()
    query_vector = await embedding_service.embed(query)

    # Validate vector data (security: ensure only numeric values)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in query_vector):
        raise ValueError("Invalid vector data: must contain only numeric values")

    # Build query with pgvector cosine distance
    # Use validated numeric values to prevent SQL injection
    vector_str = f"[{','.join(str(float(v)) for v in query_vector)}]"

    filters = "tenant_id = :tenant_id AND user_id = :user_id"
    params: dict = {"tenant_id": tenant_id, "user_id": user_id, "limit": limit}

    if memory_type:
        filters += " AND memory_type = :memory_type"
        params["memory_type"] = memory_type

    # Add time filters
    if created_after:
        filters += " AND created_at >= :created_after"
        params["created_after"] = created_after

    if created_before:
        filters += " AND created_at < :created_before"
        params["created_before"] = created_before

    sql = text(
        f"""
        SELECT id, content, memory_type, metadata, created_at,
               1 - (embedding <=> '{vector_str}'::vector) AS score
        FROM embeddings
        WHERE {filters}
        ORDER BY embedding <=> '{vector_str}'::vector
        LIMIT :limit
    """
    )

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "content": row.content,
            "memory_type": row.memory_type,
            "metadata": row.metadata,
            "created_at": row.created_at,
            "score": round(float(row.score), 4),
        }
        for row in rows
    ]
