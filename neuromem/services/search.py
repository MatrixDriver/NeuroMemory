"""Semantic search service - vector similarity + BM25 hybrid search."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from neuromem.db import _is_encrypted
from neuromem.models.memory import Memory
from neuromem.providers.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)

# Default decay rate: 30 days in seconds
DEFAULT_DECAY_RATE = 86400 * 30

# RRF constant (standard value from the original paper)
RRF_K = 60


def _sanitize_bm25_query(query: str) -> str:
    """Sanitize query text for pg_search BM25 parser.

    paradedb.parse() uses Tantivy query syntax where certain characters
    (quotes, apostrophes, special operators) can cause parse errors.
    """
    # Remove characters that break Tantivy query parser
    sanitized = query.replace("'", " ").replace("\u2018", " ").replace("\u2019", " ")
    # Remove other Tantivy special chars
    for ch in ['"', '\u201c', '\u201d', '(', ')', '[', ']', '{', '}', '~', '^', '\\']:
        sanitized = sanitized.replace(ch, " ")
    # Collapse multiple spaces
    return " ".join(sanitized.split())


class SearchService:
    def __init__(self, db: AsyncSession, embedding: EmbeddingProvider, pg_search_available: bool = False, encryption=None):
        self.db = db
        self._embedding = embedding
        self._pg_search = pg_search_available if not encryption else False
        self._encryption = encryption

    async def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "fact",
        metadata: dict | None = None,
        valid_from: datetime | None = None,
    ) -> Memory | None:
        """Add a memory with its embedding vector."""
        if memory_type == "general":
            memory_type = "fact"
        elif memory_type == "insight":
            memory_type = "trait"

        import hashlib
        from datetime import timezone

        vector = await self._embedding.embed(content)
        content_hash = hashlib.md5(content.encode()).hexdigest()

        # Hash-based dedup check (skip episodic — same event in different conversations is valid)
        if memory_type != "episodic":
            dup_check = await self.db.execute(
                text("SELECT 1 FROM memories WHERE user_id = :uid AND memory_type = :mtype AND content_hash = :hash LIMIT 1"),
                {"uid": user_id, "mtype": memory_type, "hash": content_hash},
            )
            if dup_check.fetchone():
                logger.debug("Skipping duplicate memory (hash match): %s", content[:80])
                return None

        now = datetime.now(timezone.utc)
        record = Memory(
            user_id=user_id,
            content=content,
            embedding=vector,
            memory_type=memory_type,
            metadata_=metadata,
            valid_from=valid_from or now,
            content_hash=content_hash,
            valid_at=valid_from or now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        query_embedding: list[float] | None = None,
        event_after: datetime | None = None,
        event_before: datetime | None = None,
        as_of: datetime | None = None,
    ) -> list[dict]:
        """Hybrid search: vector similarity + BM25 keyword search, merged via RRF.

        Args:
            query_embedding: Optional pre-computed embedding to avoid recomputation
            event_after: Filter episodes by extracted_timestamp >= this datetime
            event_before: Filter episodes by extracted_timestamp <= this datetime
            as_of: Time-travel query — return memories valid at this point in time.
                When None, only returns currently valid memories (valid_until IS NULL).
        """
        if query_embedding is not None:
            query_vector = query_embedding
        else:
            query_vector = await self._embedding.embed(query)

        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in query_vector):
            raise ValueError("Invalid vector data: must contain only numeric values")

        vector_str = f"[{','.join(str(float(v)) for v in query_vector)}]"

        filters = "user_id = :user_id"
        bm25_query = _sanitize_bm25_query(query) if self._pg_search else query
        params: dict = {"user_id": user_id, "limit": limit, "query_text": bm25_query}

        if memory_type:
            filters += " AND memory_type = :memory_type"
            params["memory_type"] = memory_type

        if created_after:
            filters += " AND created_at >= :created_after"
            params["created_after"] = created_after

        if created_before:
            filters += " AND created_at < :created_before"
            params["created_before"] = created_before

        if event_after:
            filters += " AND extracted_timestamp >= :event_after"
            params["event_after"] = event_after

        if event_before:
            filters += " AND extracted_timestamp <= :event_before"
            params["event_before"] = event_before

        # Time-travel filter
        if as_of is not None:
            filters += (
                " AND (valid_from IS NULL OR valid_from <= :as_of)"
                " AND (valid_until IS NULL OR valid_until > :as_of)"
            )
            params["as_of"] = as_of
        else:
            filters += " AND valid_until IS NULL"

        # Hybrid search: RRF fusion of vector and BM25 results
        candidate_limit = limit * 2 if self._pg_search else limit * 4

        if self._pg_search:
            bm25_cte = f"""
            bm25_ranked AS (
                SELECT id,
                       paradedb.score(id) AS bm25_score,
                       ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS bm25_rank
                FROM memories
                WHERE {filters}
                  AND id @@@ paradedb.parse(:query_text)
                ORDER BY bm25_score DESC
                LIMIT {candidate_limit}
            )"""
        else:
            bm25_cte = f"""
            bm25_ranked AS (
                SELECT id,
                       ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query_text)) AS bm25_score,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query_text)) DESC
                       ) AS bm25_rank
                FROM memories
                WHERE {filters}
                  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query_text)
                ORDER BY bm25_score DESC
                LIMIT {candidate_limit}
            )"""

        sql = text(
            f"""
            WITH vector_ranked AS (
                SELECT id, content, memory_type, metadata, created_at, extracted_timestamp,
                       1 - (embedding <=> '{vector_str}') AS vector_score,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> '{vector_str}') AS vector_rank
                FROM memories
                WHERE {filters}
                ORDER BY embedding <=> '{vector_str}'
                LIMIT {candidate_limit}
            ),
            {bm25_cte}
            SELECT v.id, v.content, v.memory_type, v.metadata, v.created_at,
                   v.extracted_timestamp,
                   v.vector_score,
                   COALESCE(b.bm25_score, 0) AS bm25_score,
                   (1.0 / ({RRF_K} + v.vector_rank))
                   + COALESCE(1.0 / ({RRF_K} + b.bm25_rank), 0) AS rrf_score
            FROM vector_ranked v
            LEFT JOIN bm25_ranked b ON v.id = b.id
            ORDER BY rrf_score DESC
            LIMIT :limit
        """
        )

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        results = [
            {
                "id": str(row.id),
                "content": self._maybe_decrypt(row.content),
                "memory_type": row.memory_type,
                "metadata": row.metadata,
                "created_at": row.created_at,
                "extracted_timestamp": row.extracted_timestamp,
                "score": round(float(row.rrf_score), 4),
                "vector_score": round(float(row.vector_score), 4),
                "bm25_score": round(float(row.bm25_score), 4),
            }
            for row in rows
        ]

        # Update access tracking asynchronously
        if results:
            await self._update_access_tracking(user_id, [r["id"] for r in results])

        return results

    def _maybe_decrypt(self, content: str) -> str:
        """Decrypt content if encryption is enabled and value is encrypted."""
        if not self._encryption or not _is_encrypted(content):
            return content
        try:
            envelope = json.loads(content)
            return self._encryption.decrypt(envelope)
        except Exception as e:
            logger.warning("Failed to decrypt search result content: %s", e)
            return content

    async def scored_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
        decay_rate: float = DEFAULT_DECAY_RATE,
        query_embedding: list[float] | None = None,
        event_after: datetime | None = None,
        event_before: datetime | None = None,
        exclude_types: list[str] | None = None,
        as_of: datetime | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        current_emotion: dict | None = None,
    ) -> list[dict]:
        """Cosine-based scored search with BM25 hybrid and recency/importance bonuses.

        Score = base_relevance × (1 + recency_bonus + importance_bonus)
        - base_relevance: min(cosine_similarity + bm25_hit*0.05, 1.0)
        - recency_bonus: 0~0.15, exponential decay with emotional arousal slowdown
        - importance_bonus: 0~0.15, from metadata importance (1-10), default 0.5

        Args:
            query_embedding: Optional pre-computed embedding to avoid recomputation
            event_after: Filter episodes by extracted_timestamp >= this datetime
            event_before: Filter episodes by extracted_timestamp <= this datetime
            as_of: Time-travel query — return memories valid at this point in time.
            created_after: Filter by created_at >= this datetime.
            created_before: Filter by created_at <= this datetime.
        """
        if query_embedding is not None:
            query_vector = query_embedding
        else:
            query_vector = await self._embedding.embed(query)

        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in query_vector):
            raise ValueError("Invalid vector data: must contain only numeric values")

        vector_str = f"[{','.join(str(float(v)) for v in query_vector)}]"

        filters = "user_id = :user_id"
        bm25_query = _sanitize_bm25_query(query) if self._pg_search else query
        params: dict = {"user_id": user_id, "limit": limit, "decay_rate": decay_rate, "query_text": bm25_query}

        if memory_type:
            filters += " AND memory_type = :memory_type"
            params["memory_type"] = memory_type

        if exclude_types:
            placeholders = ", ".join(f":excl_{i}" for i in range(len(exclude_types)))
            filters += f" AND memory_type NOT IN ({placeholders})"
            for i, t in enumerate(exclude_types):
                params[f"excl_{i}"] = t

        if event_after:
            filters += " AND extracted_timestamp >= :event_after"
            params["event_after"] = event_after

        if event_before:
            filters += " AND extracted_timestamp <= :event_before"
            params["event_before"] = event_before

        if created_after:
            filters += " AND created_at >= :created_after"
            params["created_after"] = created_after

        if created_before:
            filters += " AND created_at <= :created_before"
            params["created_before"] = created_before

        # Time-travel filter
        if as_of is not None:
            filters += (
                " AND (valid_from IS NULL OR valid_from <= :as_of)"
                " AND (valid_until IS NULL OR valid_until > :as_of)"
            )
            params["as_of"] = as_of
        else:
            filters += " AND valid_until IS NULL"

        # Exclude inactive trait stages from search results
        filters += " AND NOT (memory_type = 'trait' AND trait_stage IN ('trend', 'candidate', 'dissolved'))"

        # Emotion matching bonus SQL fragment
        if current_emotion and isinstance(current_emotion, dict):
            q_valence = float(current_emotion.get("valence", 0))
            q_arousal = float(current_emotion.get("arousal", 0))
            # Bonus: 0~0.10, based on 1 - normalized distance in valence-arousal space
            emotion_bonus_sql = (
                f"0.10 * GREATEST(0, 1.0 - SQRT("
                f"  POWER(COALESCE((metadata->'emotion'->>'valence')::float, 0) - {q_valence}, 2)"
                f"  + POWER(COALESCE((metadata->'emotion'->>'arousal')::float, 0) - {q_arousal}, 2)"
                f") / 2.83)"  # 2.83 = sqrt(2^2 + 1^2), max possible distance
            )
        else:
            emotion_bonus_sql = "0"

        candidate_limit = limit * 2 if self._pg_search else limit * 4

        if self._pg_search:
            bm25_cte = f"""
            bm25_ranked AS (
                SELECT id,
                       paradedb.score(id) AS bm25_score,
                       ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS bm25_rank
                FROM memories
                WHERE {filters}
                  AND id @@@ paradedb.parse(:query_text)
                ORDER BY bm25_score DESC
                LIMIT {candidate_limit}
            ),"""
        else:
            bm25_cte = f"""
            bm25_ranked AS (
                SELECT id,
                       ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query_text)) AS bm25_score,
                       ROW_NUMBER() OVER (
                           ORDER BY ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', :query_text)) DESC
                       ) AS bm25_rank
                FROM memories
                WHERE {filters}
                  AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query_text)
                ORDER BY bm25_score DESC
                LIMIT {candidate_limit}
            ),"""

        sql = text(
            f"""
            WITH vector_ranked AS (
                SELECT id, content, memory_type, metadata, created_at, extracted_timestamp,
                       access_count, last_accessed_at, trait_stage,
                       1 - (embedding <=> '{vector_str}') AS vector_score,
                       ROW_NUMBER() OVER (ORDER BY embedding <=> '{vector_str}') AS vector_rank
                FROM memories
                WHERE {filters}
                ORDER BY embedding <=> '{vector_str}'
                LIMIT {candidate_limit}
            ),
            {bm25_cte}
            hybrid AS (
                SELECT v.*,
                       COALESCE(b.bm25_score, 0) AS bm25_score,
                       -- RRF fusion as relevance signal
                       (1.0 / ({RRF_K} + v.vector_rank))
                       + COALESCE(1.0 / ({RRF_K} + b.bm25_rank), 0) AS rrf_score
                FROM vector_ranked v
                LEFT JOIN bm25_ranked b ON v.id = b.id
            )
            SELECT id, content, memory_type, metadata, created_at, extracted_timestamp,
                   access_count, last_accessed_at, trait_stage,
                   vector_score AS relevance,
                   bm25_score,
                   rrf_score,
                   -- recency_bonus: 0~0.15
                   0.15 * EXP(
                       -EXTRACT(EPOCH FROM (NOW() - created_at))
                       / (:decay_rate * (1 + COALESCE((metadata->'emotion'->>'arousal')::float, 0) * 0.5))
                   ) AS recency,
                   -- importance_bonus: 0~0.15
                   0.15 * COALESCE((metadata->>'importance')::float / 10.0, 0.5) AS importance,
                   -- emotion_match_bonus: 0~0.10
                   {emotion_bonus_sql} AS emotion_match,
                   -- final score: base_relevance × (1 + recency + importance + trait_boost + emotion_match)
                   LEAST(vector_score + CASE WHEN bm25_score > 0 THEN 0.05 ELSE 0 END, 1.0)
                   * (1.0
                      + 0.15 * EXP(
                          -EXTRACT(EPOCH FROM (NOW() - created_at))
                          / (:decay_rate * (1 + COALESCE((metadata->'emotion'->>'arousal')::float, 0) * 0.5))
                      )
                      + 0.15 * COALESCE((metadata->>'importance')::float / 10.0, 0.5)
                      + CASE
                          WHEN memory_type = 'trait' THEN
                              CASE trait_stage
                                  WHEN 'core'        THEN 0.25
                                  WHEN 'established' THEN 0.15
                                  WHEN 'emerging'    THEN 0.05
                                  ELSE 0
                              END
                          ELSE 0
                        END
                      + {emotion_bonus_sql}
                   ) AS score
            FROM hybrid
            ORDER BY score DESC
            LIMIT :limit
        """
        )

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        results = [
            {
                "id": str(row.id),
                "content": self._maybe_decrypt(row.content),
                "memory_type": row.memory_type,
                "metadata": row.metadata,
                "created_at": row.created_at,
                "extracted_timestamp": row.extracted_timestamp,
                "relevance": round(float(row.relevance), 4),
                "bm25_score": round(float(row.bm25_score), 4),
                "rrf_score": round(float(row.rrf_score), 4),
                "recency": round(float(row.recency), 4),
                "importance": round(float(row.importance), 4),
                "emotion_match": round(float(row.emotion_match), 4),
                "score": round(float(row.score), 4),
            }
            for row in rows
        ]

        # Update access tracking
        if results:
            await self._update_access_tracking(user_id, [r["id"] for r in results])

        return results

    async def _update_access_tracking(self, user_id: str, ids: list[str]) -> None:
        """Update access_count and last_accessed_at for retrieved memories."""
        if not ids:
            return
        try:
            placeholders = ", ".join(f":id_{i}" for i in range(len(ids)))
            params = {f"id_{i}": id_ for i, id_ in enumerate(ids)}
            params["user_id"] = user_id
            sql = text(f"""
                UPDATE memories
                SET access_count = access_count + 1,
                    last_accessed_at = NOW()
                WHERE id IN ({placeholders})
                  AND user_id = :user_id
            """)
            await self.db.execute(sql, params)
            await self.db.commit()
        except Exception as e:
            logger.warning("Failed to update access tracking: %s", e)
