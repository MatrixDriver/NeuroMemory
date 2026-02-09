"""Semantic search service - vector similarity search via pgvector."""

import uuid

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
) -> list[dict]:
    """Semantic search for memories using cosine similarity."""
    embedding_service = get_embedding_service()
    query_vector = await embedding_service.embed(query)

    # Build query with pgvector cosine distance
    vector_str = f"[{','.join(str(v) for v in query_vector)}]"

    filters = "tenant_id = :tenant_id AND user_id = :user_id"
    params: dict = {"tenant_id": tenant_id, "user_id": user_id, "limit": limit}

    if memory_type:
        filters += " AND memory_type = :memory_type"
        params["memory_type"] = memory_type

    sql = text(f"""
        SELECT id, content, memory_type, metadata,
               1 - (embedding <=> '{vector_str}'::vector) AS score
        FROM embeddings
        WHERE {filters}
        ORDER BY embedding <=> '{vector_str}'::vector
        LIMIT :limit
    """)

    result = await db.execute(sql, params)
    rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "content": row.content,
            "memory_type": row.memory_type,
            "metadata": row.metadata,
            "score": round(float(row.score), 4),
        }
        for row in rows
    ]
