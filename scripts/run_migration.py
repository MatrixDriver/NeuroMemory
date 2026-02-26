"""Run database migration for P1 conversation embeddings."""

import asyncio
import asyncpg


async def run_migration():
    """Apply migration 002: add conversation embeddings."""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="neuromem",
        password="neuromem",
        database="neuromem",
    )

    try:
        # Read migration SQL
        with open("migrations/002_add_conversation_embeddings.sql") as f:
            sql = f.read()

        # Execute migration
        await conn.execute(sql)
        print("✅ Migration 002 applied successfully")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
