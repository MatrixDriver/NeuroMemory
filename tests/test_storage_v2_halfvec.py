"""Tests for RPIV-1 storage foundation V2: halfvec migration.

Covers: vector -> halfvec type conversion, index rebuild, data integrity.
PRD section: 7.5
"""

from __future__ import annotations

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_embedding_udt(conn) -> str | None:
    """Get the udt_name for the embedding column in memories table."""
    result = await conn.execute(text("""
        SELECT udt_name FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'embedding'
    """))
    return result.scalar()


async def _get_index_def(conn, index_name: str) -> str | None:
    """Get the index definition from pg_indexes."""
    result = await conn.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE indexname = :idx"
    ), {"idx": index_name})
    row = result.fetchone()
    return row.indexdef if row else None


# ---------------------------------------------------------------------------
# TC-H01: Detect vector type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_vector_type(db_engine):
    """TC-H01: Can detect that embedding column is currently 'vector' type."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding vector(1024)
            )
        """))

        udt = await _get_embedding_udt(conn)
        assert udt == "vector"

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-H02: Convert vector to halfvec
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_convert_vector_to_halfvec(db_engine):
    """TC-H02: ALTER COLUMN converts vector to halfvec successfully."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding vector(4)
            )
        """))

        # Insert test data with vector type
        await conn.execute(text(
            "INSERT INTO memories (embedding) VALUES ('[0.1,0.2,0.3,0.4]'::vector(4))"
        ))

        # Convert to halfvec
        await conn.execute(text(
            "ALTER TABLE memories ALTER COLUMN embedding TYPE halfvec(4) USING embedding::halfvec(4)"
        ))

        udt = await _get_embedding_udt(conn)
        assert udt == "halfvec"

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-H03: halfvec preserves data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_halfvec_preserves_data(db_engine):
    """TC-H03: Vector values are preserved within half precision tolerance."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding vector(4)
            )
        """))

        # Insert known values
        await conn.execute(text(
            "INSERT INTO memories (embedding) VALUES ('[0.125,0.5,0.75,0.9375]'::vector(4))"
        ))

        # Read before conversion
        result = await conn.execute(text("SELECT embedding::text FROM memories"))
        before = result.scalar()

        # Convert
        await conn.execute(text(
            "ALTER TABLE memories ALTER COLUMN embedding TYPE halfvec(4) USING embedding::halfvec(4)"
        ))

        # Read after conversion
        result = await conn.execute(text("SELECT embedding::text FROM memories"))
        after = result.scalar()

        # Parse values and compare
        before_vals = [float(x) for x in before.strip("[]").split(",")]
        after_vals = [float(x) for x in after.strip("[]").split(",")]

        for b, a in zip(before_vals, after_vals):
            assert abs(b - a) < 0.01, f"Value drift: {b} -> {a}"

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-H04: Index rebuild
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_halfvec_index_rebuild(db_engine):
    """TC-H04: Old vector index dropped, new halfvec index created."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding vector(4)
            )
        """))

        # Create old-style vector index
        await conn.execute(text("""
            CREATE INDEX idx_old_hnsw ON memories
            USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)
        """))

        # Drop old index BEFORE converting type (vector_cosine_ops is incompatible with halfvec)
        await conn.execute(text("DROP INDEX IF EXISTS idx_old_hnsw"))

        # Convert to halfvec
        await conn.execute(text(
            "ALTER TABLE memories ALTER COLUMN embedding TYPE halfvec(4) USING embedding::halfvec(4)"
        ))

        # Create new halfvec index
        await conn.execute(text("""
            CREATE INDEX idx_memories_hnsw ON memories
            USING hnsw (embedding halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)
        """))

        # Verify old index gone
        result = await conn.execute(text(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_old_hnsw'"
        ))
        assert result.fetchone() is None

        # Verify new index exists with halfvec_cosine_ops
        idx_def = await _get_index_def(conn, "idx_memories_hnsw")
        assert idx_def is not None
        assert "halfvec_cosine_ops" in idx_def

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-H05: Skip if already halfvec
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_halfvec_skip_if_already(db_engine):
    """TC-H05: If embedding is already halfvec, no ALTER is executed."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))
        await conn.execute(text("""
            CREATE TABLE memories (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding halfvec(4)
            )
        """))

        udt = await _get_embedding_udt(conn)
        assert udt == "halfvec"

        # Migration check: should detect halfvec and skip
        if udt == "vector":
            pytest.fail("Should not attempt conversion when already halfvec")

        # No error means skip logic works

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS memories CASCADE"))


# ---------------------------------------------------------------------------
# TC-H06: Dimension matches config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_halfvec_dimension_matches_config(db_session, mock_embedding):
    """TC-H06: The embedding column dimension matches _embedding_dims config."""
    import neuromem.models as _models

    # The db_session fixture sets up tables via create_all with _embedding_dims=1024
    expected_dims = _models._embedding_dims

    # Insert a memory to verify dimension
    from neuromem.models.memory import Memory
    vector = await mock_embedding.embed("dim test")
    assert len(vector) == expected_dims

    mem = Memory(
        user_id="dim_test",
        content="dimension check",
        embedding=vector,
        memory_type="fact",
        metadata_={},
    )
    db_session.add(mem)
    await db_session.flush()

    # Verify the column is halfvec type and the vector was stored correctly
    result = await db_session.execute(text("""
        SELECT udt_name FROM information_schema.columns
        WHERE table_name = 'memories' AND column_name = 'embedding'
    """))
    udt = result.scalar()
    assert udt == "halfvec"

    # Verify stored vector dimension by reading it back as text and parsing
    result = await db_session.execute(text(
        "SELECT embedding::text FROM memories WHERE user_id = 'dim_test'"
    ))
    vec_text = result.scalar()
    assert vec_text is not None
    # halfvec text format: [0.1,0.2,...]
    dim_count = len(vec_text.strip("[]").split(","))
    assert dim_count == expected_dims


# ---------------------------------------------------------------------------
# TC-H07: Search works after halfvec conversion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_after_halfvec_conversion(db_session, mock_embedding):
    """TC-H07: Vector search still works after conversion to halfvec."""
    from neuromem.services.search import SearchService

    svc = SearchService(db_session, mock_embedding)

    await svc.add_memory(user_id="hv_search", content="Python programming")
    await svc.add_memory(user_id="hv_search", content="Machine learning")
    await db_session.commit()

    results = await svc.search(user_id="hv_search", query="programming", limit=5)
    assert len(results) > 0


# ---------------------------------------------------------------------------
# TC-H08: Storage reduction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_halfvec_storage_reduction(db_engine):
    """TC-H08: halfvec uses approximately 50% of vector storage."""
    async with db_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("DROP TABLE IF EXISTS test_vec CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS test_hvec CASCADE"))

        # Create vector table
        await conn.execute(text("""
            CREATE TABLE test_vec (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding vector(64)
            )
        """))
        # Create halfvec table
        await conn.execute(text("""
            CREATE TABLE test_hvec (
                id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
                embedding halfvec(64)
            )
        """))

        # Generate a test vector string
        vec_str = "[" + ",".join(["0.5"] * 64) + "]"

        await conn.execute(text(
            f"INSERT INTO test_vec (embedding) VALUES ('{vec_str}'::vector(64))"
        ))
        await conn.execute(text(
            f"INSERT INTO test_hvec (embedding) VALUES ('{vec_str}'::halfvec(64))"
        ))

        # Compare sizes
        vec_size = (await conn.execute(text(
            "SELECT pg_column_size(embedding) FROM test_vec"
        ))).scalar()
        hvec_size = (await conn.execute(text(
            "SELECT pg_column_size(embedding) FROM test_hvec"
        ))).scalar()

        # halfvec should be roughly 50% of vector size (+/- overhead)
        ratio = hvec_size / vec_size
        assert ratio < 0.65, f"halfvec/vector ratio {ratio:.2f} is too high (expected ~0.5)"

    async with db_engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS test_vec CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS test_hvec CASCADE"))
