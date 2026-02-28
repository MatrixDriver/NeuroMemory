"""File CRUD service - upload, list, get, delete documents."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.models.document import Document
from neuromem.providers.embedding import EmbeddingProvider
from neuromem.services.file_processor import (
    extract_text,
    get_file_extension,
    get_mime_type,
    validate_file,
)
from neuromem.services.search import SearchService
from neuromem.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


class FileService:
    def __init__(
        self,
        db: AsyncSession,
        embedding: EmbeddingProvider,
        storage: ObjectStorage,
    ):
        self.db = db
        self._embedding = embedding
        self._storage = storage

    async def upload(
        self,
        user_id: str,
        filename: str,
        file_data: bytes,
        category: str = "general",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        auto_extract: bool = True,
    ) -> Document:
        """Upload file to storage and create document record."""
        file_size = len(file_data)
        is_valid, error = validate_file(filename, file_size)
        if not is_valid:
            raise ValueError(error)

        file_type = get_file_extension(filename)
        mime_type = get_mime_type(filename)

        object_key = await self._storage.upload(user_id, filename, file_data, mime_type)

        extracted = None
        embedding_id = None

        if auto_extract:
            extracted = extract_text(file_data, file_type)
            if extracted and extracted.strip():
                try:
                    search_svc = SearchService(self.db, self._embedding)
                    embedding = await search_svc.add_memory(
                        user_id,
                        extracted[:8000],
                        memory_type="document",
                        metadata={"source_file": filename, "category": category},
                    )
                    embedding_id = embedding.id
                except Exception as e:
                    logger.warning("Embedding generation failed for %s: %s", filename, e)

        doc = Document(
            user_id=user_id,
            filename=filename,
            file_type=file_type,
            mime_type=mime_type,
            file_size=file_size,
            object_key=object_key,
            extracted_text=extracted,
            embedding_id=embedding_id,
            category=category,
            tags=tags,
            metadata_=metadata,
            source_type="upload",
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def create_from_text(
        self,
        user_id: str,
        title: str,
        content: str,
        category: str = "general",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Document:
        """Create a document from raw text content."""
        file_data = content.encode("utf-8")
        filename = f"{title}.txt"

        object_key = await self._storage.upload(user_id, filename, file_data, "text/plain")

        embedding_id = None
        if content.strip():
            try:
                search_svc = SearchService(self.db, self._embedding)
                embedding = await search_svc.add_memory(
                    user_id,
                    content[:8000],
                    memory_type="document",
                    metadata={"source_file": title, "category": category},
                )
                embedding_id = embedding.id
            except Exception as e:
                logger.warning("Embedding generation failed for text doc %s: %s", title, e)

        doc = Document(
            user_id=user_id,
            filename=filename,
            file_type="txt",
            mime_type="text/plain",
            file_size=len(file_data),
            object_key=object_key,
            extracted_text=content,
            embedding_id=embedding_id,
            category=category,
            tags=tags,
            metadata_=metadata,
            source_type="text",
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        file_types: list[str] | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
    ) -> list[dict]:
        """Semantic search for file contents with document metadata."""
        query_vector = await self._embedding.embed(query)
        vector_str = f"[{','.join(str(float(v)) for v in query_vector)}]"

        filters = "d.user_id = :user_id"
        params: dict = {"user_id": user_id, "limit": limit}

        if file_types:
            filters += " AND d.file_type = ANY(:file_types)"
            params["file_types"] = file_types

        if category:
            filters += " AND d.category = :category"
            params["category"] = category

        if tags:
            filters += " AND d.tags @> :tags::jsonb"
            params["tags"] = str(tags).replace("'", '"')

        sql = text(
            f"""
            SELECT d.id, d.filename, d.file_type, d.category, d.tags,
                   d.file_size, d.extracted_text, d.created_at,
                   1 - (e.embedding <=> '{vector_str}') AS similarity
            FROM documents d
            JOIN memories e ON d.embedding_id = e.id
            WHERE {filters}
            ORDER BY e.embedding <=> '{vector_str}'
            LIMIT :limit
            """
        )

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        return [
            {
                "file_id": str(row.id),
                "filename": row.filename,
                "file_type": row.file_type,
                "category": row.category,
                "tags": row.tags,
                "file_size": row.file_size,
                "extracted_text": row.extracted_text[:200] if row.extracted_text else None,
                "similarity": round(float(row.similarity), 4),
                "created_at": row.created_at,
            }
            for row in rows
        ]

    async def list_documents(
        self,
        user_id: str,
        category: str | None = None,
        tags: list[str] | None = None,
        file_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[Document]:
        """List documents with optional filters."""
        stmt = (
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        if category:
            stmt = stmt.where(Document.category == category)

        if file_types:
            stmt = stmt.where(Document.file_type.in_(file_types))

        if tags:
            for tag in tags:
                stmt = stmt.where(Document.tags.contains([tag]))

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_document(
        self,
        file_id: uuid.UUID,
        user_id: str,
    ) -> Document | None:
        """Get a single document by ID with ownership check."""
        result = await self.db.execute(
            select(Document).where(
                Document.id == file_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def delete_document(
        self,
        file_id: uuid.UUID,
        user_id: str,
    ) -> bool:
        """Delete document from storage and database with ownership check."""
        doc = await self.get_document(file_id, user_id)
        if not doc:
            return False

        try:
            await self._storage.delete(doc.object_key)
        except Exception as e:
            logger.warning("Storage delete failed for %s: %s", doc.object_key, e)

        await self.db.delete(doc)
        await self.db.flush()
        return True
