"""Database management - engine, session factory, initialization."""

import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = logging.getLogger(__name__)


class Database:
    """Async database manager with connection pooling."""

    pg_search_available: bool = False

    def __init__(self, url: str, pool_size: int = 10, echo: bool = False):
        self.engine = create_async_engine(url, pool_size=pool_size, echo=echo)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,  # 禁用自动flush，由代码显式控制事务提交时机
        )

    @asynccontextmanager
    async def session(self):
        """Context manager that yields a session with auto-commit/rollback."""
        async with self.session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def init(self) -> None:
        """Create pgvector extension and all tables, run idempotent migrations."""
        from pgvector.sqlalchemy import HALFVEC, Vector

        import neuromem.models as _models
        from neuromem.models.base import Base
        # Import all models to register them with Base.metadata
        import neuromem.models.memory  # noqa: F401
        import neuromem.models.kv  # noqa: F401
        import neuromem.models.conversation  # noqa: F401
        import neuromem.models.document  # noqa: F401
        import neuromem.models.graph  # noqa: F401
        import neuromem.models.trait_evidence  # noqa: F401
        import neuromem.models.memory_history  # noqa: F401
        import neuromem.models.reflection_cycle  # noqa: F401
        import neuromem.models.memory_source  # noqa: F401

        # Fix vector column dimensions: __declare_last__ runs at import time
        # with the default 1024, but _embedding_dims may have been updated
        # by NeuroMemory.__init__() to the actual provider dimensions.
        dims = _models._embedding_dims
        for table in Base.metadata.tables.values():
            for col in table.columns:
                if isinstance(col.type, (Vector, HALFVEC)):
                    if getattr(col.type, 'dim', None) != dims:
                        col.type = HALFVEC(dims)

        async with self.engine.begin() as conn:
            # Step 1: Create extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

            # Step 2: Detect table state + rename embeddings -> memories
            has_embeddings = (await conn.execute(
                text("SELECT to_regclass('embeddings') IS NOT NULL")
            )).scalar()
            has_memories = (await conn.execute(
                text("SELECT to_regclass('memories') IS NOT NULL")
            )).scalar()

            if has_embeddings and not has_memories:
                await conn.execute(text("ALTER TABLE embeddings RENAME TO memories"))
                logger.info("Renamed table 'embeddings' to 'memories'")
            elif has_embeddings and has_memories:
                raise RuntimeError("Both 'embeddings' and 'memories' tables exist")

            # Step 3: create_all (creates new tables + missing tables)
            await conn.run_sync(Base.metadata.create_all)

            # Step 4: ADD COLUMN IF NOT EXISTS (idempotent column additions)
            migration_columns = [
                # Bi-temporal timeline
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_at TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS invalid_at TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS expired_at TIMESTAMPTZ",
                # content_hash
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_hash VARCHAR(32)",
                # importance
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance REAL DEFAULT 0.5",
                # trait columns (12)
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_subtype VARCHAR(20)",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_stage VARCHAR(20)",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_confidence REAL",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_context VARCHAR(20)",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_parent_id UUID",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_reinforcement_count INTEGER DEFAULT 0",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_contradiction_count INTEGER DEFAULT 0",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_last_reinforced TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_first_observed TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_window_start TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_window_end TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_derived_from VARCHAR(20)",
                # Entity association
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS subject_entity_id UUID",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS object_entity_id UUID",
                # Conversation provenance
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source_episode_ids UUID[]",
                # Legacy migration compat
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by UUID",
            ]
            for col_sql in migration_columns:
                await conn.execute(text(col_sql))

            # Step 4b: Data backfill BEFORE constraint (idempotent)
            # Must convert legacy types before adding CHECK constraint
            # general -> fact
            await conn.execute(text(
                "UPDATE memories SET memory_type = 'fact' WHERE memory_type = 'general'"
            ))
            # insight -> trait(trend)
            await conn.execute(text("""
                UPDATE memories SET
                    memory_type = 'trait',
                    trait_stage = 'trend',
                    trait_window_start = created_at,
                    trait_window_end = created_at + interval '30 days'
                WHERE memory_type = 'insight'
            """))

            # Step 4c: Add CHECK constraint for memory_type (idempotent)
            await conn.execute(text("""
                DO $$ BEGIN
                  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_memory_type') THEN
                    ALTER TABLE memories ADD CONSTRAINT chk_memory_type CHECK (memory_type IN ('fact', 'episodic', 'trait', 'document'));
                  END IF;
                END $$;
            """))

            # Step 5: conversation_sessions add column
            await conn.execute(text(
                "ALTER TABLE conversation_sessions ADD COLUMN IF NOT EXISTS last_reflected_at TIMESTAMPTZ"
            ))

            # Step 6: Remaining data backfill (idempotent)
            # trait metadata -> dedicated columns
            await conn.execute(text("""
                UPDATE memories SET
                    trait_subtype = metadata->>'trait_subtype',
                    trait_stage = COALESCE(trait_stage, metadata->>'trait_stage'),
                    trait_confidence = (metadata->>'confidence')::float,
                    trait_context = metadata->>'context',
                    trait_reinforcement_count = COALESCE((metadata->>'reinforcement_count')::int, 0),
                    trait_contradiction_count = COALESCE((metadata->>'contradiction_count')::int, 0),
                    trait_derived_from = metadata->>'derived_from'
                WHERE memory_type = 'trait' AND trait_subtype IS NULL
                  AND metadata->>'trait_subtype' IS NOT NULL
            """))
            # content_hash backfill
            await conn.execute(text(
                "UPDATE memories SET content_hash = MD5(content) WHERE content_hash IS NULL"
            ))
            # valid_at backfill
            await conn.execute(text(
                "UPDATE memories SET valid_at = COALESCE(valid_from, created_at) WHERE valid_at IS NULL"
            ))

            # Step 7: halfvec migration
            pgvector_version = (await conn.execute(text(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            ))).scalar()

            can_halfvec = False
            col_type_was_vector = False
            if pgvector_version:
                parts = pgvector_version.split('.')[:2]
                can_halfvec = (int(parts[0]), int(parts[1])) >= (0, 7)

            if can_halfvec:
                col_type = (await conn.execute(text("""
                    SELECT udt_name FROM information_schema.columns
                    WHERE table_name = 'memories' AND column_name = 'embedding'
                """))).scalar()

                if col_type == 'vector':
                    col_type_was_vector = True
                    await conn.execute(text(
                        f"ALTER TABLE memories ALTER COLUMN embedding "
                        f"TYPE halfvec({dims}) USING embedding::halfvec({dims})"
                    ))
                    logger.info("Migrated embedding column to halfvec(%d)", dims)

            # Step 8: Index updates
            index_sqls = [
                # Trait indexes
                """CREATE INDEX IF NOT EXISTS idx_trait_stage_confidence
                   ON memories (user_id, trait_stage, trait_confidence DESC)
                   WHERE trait_stage NOT IN ('dissolved', 'trend')""",
                """CREATE INDEX IF NOT EXISTS idx_trait_parent
                   ON memories (trait_parent_id) WHERE trait_parent_id IS NOT NULL""",
                """CREATE INDEX IF NOT EXISTS idx_trait_context
                   ON memories (user_id, trait_context) WHERE trait_context IS NOT NULL""",
                """CREATE INDEX IF NOT EXISTS idx_trait_window
                   ON memories (trait_window_end)
                   WHERE trait_stage = 'trend' AND trait_window_end IS NOT NULL""",
                # Dedup index
                """CREATE INDEX IF NOT EXISTS idx_content_hash
                   ON memories (user_id, memory_type, content_hash)
                   WHERE content_hash IS NOT NULL""",
                # valid_at index
                """CREATE INDEX IF NOT EXISTS ix_mem_user_valid_at
                   ON memories (user_id, valid_at, invalid_at)""",
            ]
            for idx_sql in index_sqls:
                await conn.execute(text(idx_sql))

            # Step 9: Rebuild vector indexes after halfvec migration
            if can_halfvec and col_type_was_vector:
                old_indexes = (await conn.execute(text("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'memories'
                      AND indexdef LIKE '%vector_cosine_ops%'
                """))).fetchall()
                for idx in old_indexes:
                    await conn.execute(text(f"DROP INDEX IF EXISTS {idx.indexname}"))

                await conn.execute(text(f"""
                    CREATE INDEX IF NOT EXISTS idx_memories_hnsw
                    ON memories USING hnsw (embedding halfvec_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """))

            # v0.6.3: extraction status tracking columns (idempotent)
            for col_sql in [
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS extraction_status VARCHAR(20) DEFAULT 'pending'",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS extraction_error TEXT",
                "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS extraction_retries INTEGER DEFAULT 0",
            ]:
                await conn.execute(text(col_sql))
            # Migrate legacy extracted=true rows to extraction_status='done'
            await conn.execute(text(
                "UPDATE conversations SET extraction_status = 'done' "
                "WHERE extracted = true AND extraction_status = 'pending'"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_conversations_extraction_status "
                "ON conversations (user_id, extraction_status)"
            ))

        # Try to enable pg_search (graceful degradation)
        try:
            async with self.engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
                self.pg_search_available = True
                logger.info("pg_search extension enabled")
        except Exception as e:
            self.pg_search_available = False
            logger.info("pg_search not available, using tsvector fallback: %s", e)

        # Create BM25 index if pg_search is available
        if self.pg_search_available:
            try:
                async with self.engine.begin() as conn:
                    await conn.execute(text("""
                        CREATE INDEX IF NOT EXISTS idx_memories_bm25
                        ON memories
                        USING bm25 (id, content)
                        WITH (key_field='id')
                    """))
                    logger.info("BM25 index created on memories")
            except Exception as e:
                logger.warning("Failed to create BM25 index: %s", e)


    async def close(self) -> None:
        """Dispose engine and release all connections."""
        await self.engine.dispose()
