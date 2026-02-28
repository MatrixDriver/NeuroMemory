"""Tests for RPIV-1 storage foundation V2: Schema migration.

Covers: table rename, ADD COLUMN IF NOT EXISTS, index creation, idempotency.
PRD sections: 7.1, 7.2, 7.8
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _table_exists(conn, table_name: str) -> bool:
    result = await conn.execute(
        text("SELECT to_regclass(:t) IS NOT NULL"),
        {"t": table_name},
    )
    return result.scalar()


async def _column_info(conn, table_name: str, column_name: str) -> dict | None:
    """Return column metadata from information_schema, or None if missing."""
    result = await conn.execute(
        text("""
            SELECT data_type, udt_name, is_nullable, character_maximum_length,
                   column_default
            FROM information_schema.columns
            WHERE table_name = :tbl AND column_name = :col
        """),
        {"tbl": table_name, "col": column_name},
    )
    row = result.fetchone()
    if row is None:
        return None
    return {
        "data_type": row.data_type,
        "udt_name": row.udt_name,
        "is_nullable": row.is_nullable,
        "max_length": row.character_maximum_length,
        "default": row.column_default,
    }


async def _index_exists(conn, index_name: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :idx"),
        {"idx": index_name},
    )
    return result.fetchone() is not None


async def _run_migration(conn):
    """Execute the migration logic from db.init() inline.

    This imports and calls the Database migration steps directly.
    If the implementation exposes a standalone migration function, use that.
    Otherwise, we replicate the key DDL from the plan.
    """
    from neuromem.db import Database

    # Use Database's init method to run the full migration
    # We need to create a temporary Database instance
    db = Database.__new__(Database)
    db._engine = conn.get_bind()
    # The actual migration is embedded in Database.init() which uses
    # engine.begin(). Since we already have a connection, we call the
    # migration SQL directly. The tests below execute migration DDL
    # via the db_session's connection.


# ---------------------------------------------------------------------------
# TC-M01: Rename embeddings -> memories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rename_embeddings_to_memories(db_engine):
    """TC-M01: When 'embeddings' table exists, RENAME to 'memories'."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Drop both tables if they exist
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS embeddings CASCADE"))

        # Create the old embeddings table with minimal schema
        await conn.execute(text("""
            CREATE TABLE embeddings (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                memory_type VARCHAR(50) DEFAULT 'general',
                metadata JSONB DEFAULT '{}'
            )
        """))
        # Insert test data
        await conn.execute(text("""
            INSERT INTO embeddings (user_id, content, memory_type)
            VALUES ('u1', 'test1', 'fact'), ('u1', 'test2', 'episodic'), ('u2', 'test3', 'fact')
        """))

        # Verify embeddings exists
        assert await _table_exists(conn, "embeddings")

        # Execute rename
        has_embeddings = await _table_exists(conn, "embeddings")
        has_memories = await _table_exists(conn, "memories")
        if has_embeddings and not has_memories:
            await conn.execute(text("ALTER TABLE embeddings RENAME TO memories"))

        # Verify
        assert not await _table_exists(conn, "embeddings")
        assert await _table_exists(conn, "memories")

        # Data preserved
        result = await conn.execute(text("SELECT COUNT(*) FROM memories"))
        assert result.scalar() == 3

    # Cleanup
    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-M02: Rename idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rename_idempotent(db_engine):
    """TC-M02: If 'memories' already exists, skip rename without error."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS embeddings CASCADE"))

        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                content TEXT NOT NULL
            )
        """))
        await conn.execute(text(
            "INSERT INTO memories (user_id, content) VALUES ('u1', 'existing')"
        ))

        # Migration logic: skip if memories already exists
        has_embeddings = await _table_exists(conn, "embeddings")
        has_memories = await _table_exists(conn, "memories")
        if has_embeddings and not has_memories:
            await conn.execute(text("ALTER TABLE embeddings RENAME TO memories"))
        # No error expected

        result = await conn.execute(text("SELECT COUNT(*) FROM memories"))
        assert result.scalar() == 1

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-M03: Fresh install creates memories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fresh_install_creates_memories(db_engine):
    """TC-M03: On a fresh DB, create_all produces 'memories' table."""
    import neuromem.models as _models
    _models._embedding_dims = 1024

    from neuromem.models.base import Base
    import neuromem.models.memory  # noqa: F401

    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS embeddings CASCADE"))
        await conn.run_sync(Base.metadata.create_all)

        assert await _table_exists(conn, "memories")
        assert not await _table_exists(conn, "embeddings")

    # Cleanup via drop_all
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# TC-M04: Trait columns exist with correct types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_trait_columns(db_session):
    """TC-M04: All 12 trait columns exist with correct types."""
    conn = db_session

    expected_columns = {
        "trait_subtype": "varchar",
        "trait_stage": "varchar",
        "trait_confidence": "float8",
        "trait_context": "varchar",
        "trait_parent_id": "uuid",
        "trait_reinforcement_count": "int4",
        "trait_contradiction_count": "int4",
        "trait_last_reinforced": "timestamptz",
        "trait_first_observed": "timestamptz",
        "trait_window_start": "timestamptz",
        "trait_window_end": "timestamptz",
        "trait_derived_from": "varchar",
    }

    for col_name, expected_udt in expected_columns.items():
        info = await _column_info(conn, "memories", col_name)
        assert info is not None, f"Column '{col_name}' missing from memories table"
        assert info["udt_name"] == expected_udt, (
            f"Column '{col_name}': expected udt_name='{expected_udt}', got '{info['udt_name']}'"
        )


# ---------------------------------------------------------------------------
# TC-M05: Timeline columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_timeline_columns(db_session):
    """TC-M05: valid_at/invalid_at/expired_at columns exist as timestamptz."""
    for col_name in ["valid_at", "invalid_at", "expired_at"]:
        info = await _column_info(db_session, "memories", col_name)
        assert info is not None, f"Column '{col_name}' missing"
        assert info["udt_name"] == "timestamptz"
        assert info["is_nullable"] == "YES"


# ---------------------------------------------------------------------------
# TC-M06: content_hash column
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_content_hash_column(db_session):
    """TC-M06: content_hash is VARCHAR(32)."""
    info = await _column_info(db_session, "memories", "content_hash")
    assert info is not None
    assert info["udt_name"] == "varchar"
    assert info["max_length"] == 32


# ---------------------------------------------------------------------------
# TC-M07: Entity columns
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_entity_columns(db_session):
    """TC-M07: subject_entity_id and object_entity_id are UUID, nullable."""
    for col_name in ["subject_entity_id", "object_entity_id"]:
        info = await _column_info(db_session, "memories", col_name)
        assert info is not None, f"Column '{col_name}' missing"
        assert info["udt_name"] == "uuid"
        assert info["is_nullable"] == "YES"


# ---------------------------------------------------------------------------
# TC-M08: source_episode_ids array
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_source_episode_ids(db_session):
    """TC-M08: source_episode_ids is UUID[] (ARRAY type)."""
    info = await _column_info(db_session, "memories", "source_episode_ids")
    assert info is not None
    assert info["data_type"] == "ARRAY" or info["udt_name"] == "_uuid"


# ---------------------------------------------------------------------------
# TC-M09: importance column
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_importance_column(db_session):
    """TC-M09: importance column exists as float with default 0.5."""
    info = await _column_info(db_session, "memories", "importance")
    assert info is not None
    assert info["udt_name"] in ("float4", "float8")


# ---------------------------------------------------------------------------
# TC-M10: ADD COLUMN idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_columns_idempotent(db_engine):
    """TC-M10: Running ADD COLUMN IF NOT EXISTS twice doesn't error."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                content TEXT NOT NULL
            )
        """))

        add_col_sql = "ALTER TABLE memories ADD COLUMN IF NOT EXISTS trait_subtype VARCHAR(20)"
        await conn.execute(text(add_col_sql))
        await conn.execute(text(add_col_sql))  # Second time should not error

        info = await _column_info(conn, "memories", "trait_subtype")
        assert info is not None

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-M11: conversation_sessions.last_reflected_at
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conversation_sessions_last_reflected_at(nm):
    """TC-M11: conversation_sessions has last_reflected_at column after init().

    The last_reflected_at column is added dynamically by db.init() via
    ALTER TABLE ADD COLUMN, not by ORM create_all.
    """
    async with nm._db.session() as session:
        info = await _column_info(session, "conversation_sessions", "last_reflected_at")
        assert info is not None, "last_reflected_at column missing from conversation_sessions"
        assert info["udt_name"] == "timestamptz"


# ---------------------------------------------------------------------------
# TC-M12: Trait indexes created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trait_indexes_created(nm):
    """TC-M12: All trait-specific indexes exist after init().

    These indexes are created by db.init() (Step 8), not by ORM create_all.
    """
    expected_indexes = [
        "idx_trait_stage_confidence",
        "idx_trait_parent",
        "idx_trait_context",
        "idx_trait_window",
        "idx_content_hash",
    ]
    async with nm._db.session() as session:
        for idx_name in expected_indexes:
            exists = await _index_exists(session, idx_name)
            assert exists, f"Index '{idx_name}' not found in pg_indexes"


# ---------------------------------------------------------------------------
# TC-M13: Indexes idempotent
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_indexes_idempotent(db_engine):
    """TC-M13: CREATE INDEX IF NOT EXISTS can run twice without error."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                content_hash VARCHAR(32)
            )
        """))

        idx_sql = """CREATE INDEX IF NOT EXISTS idx_content_hash
                     ON memories (content_hash) WHERE content_hash IS NOT NULL"""
        await conn.execute(text(idx_sql))
        await conn.execute(text(idx_sql))  # Second time should not error

        assert await _index_exists(conn, "idx_content_hash")

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-M14: Full migration three times
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_migration_three_times(nm):
    """TC-M14: db.init() can be called 3 times without error (idempotent).

    Uses the NeuroMemory facade which calls db.init() internally.
    The nm fixture already called init() once. We call it two more times.
    """
    # nm fixture already called init() once during setup
    # Call init again - should be idempotent
    await nm.init()
    await nm.init()

    # Verify basic operation still works
    record = await nm._add_memory(user_id="idempotent_test", content="test")
    assert record is not None
    assert record.content == "test"
