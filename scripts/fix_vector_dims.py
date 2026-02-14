"""Fix vector dimensions in database to support variable embedding sizes."""

import asyncio
import asyncpg


async def fix_vector_dimensions():
    """Apply migration 003: fix vector dimensions."""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="neuromemory",
        password="neuromemory",
        database="neuromemory",
    )

    try:
        # Read migration SQL
        with open("migrations/003_fix_vector_dimensions.sql") as f:
            sql = f.read()

        # Execute migration
        await conn.execute(sql)
        print("✅ Migration 003 applied successfully")

        # Verify the changes
        result = await conn.fetchrow("""
            SELECT
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
            FROM pg_catalog.pg_attribute a
            WHERE a.attrelid = 'conversations'::regclass
            AND a.attname = 'embedding'
        """)
        print(f"✅ conversations.embedding type: {result['data_type']}")

        result = await conn.fetchrow("""
            SELECT
                pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
            FROM pg_catalog.pg_attribute a
            WHERE a.attrelid = 'embeddings'::regclass
            AND a.attname = 'embedding'
        """)
        print(f"✅ embeddings.embedding type: {result['data_type']}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(fix_vector_dimensions())
