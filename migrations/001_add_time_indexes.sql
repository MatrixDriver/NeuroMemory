-- Migration: Add time indexes for embeddings and preferences
-- Description: Add BRIN and composite B-tree indexes for efficient time-based queries
-- Date: 2026-02-10

-- BRIN index for time series data (saves 99% space, efficient for range queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_created_at_brin
ON embeddings USING BRIN (created_at)
WITH (pages_per_range = 128);

-- Composite B-tree index for multi-column filtering and sorting
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_tenant_user_created
ON embeddings(tenant_id, user_id, created_at DESC);

-- Preferences table time index (optional, for preference history queries)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_preferences_created_at_brin
ON preferences USING BRIN (created_at)
WITH (pages_per_range = 128);

-- Verify indexes were created
SELECT
    indexname,
    tablename,
    indexdef
FROM pg_indexes
WHERE indexname IN (
    'idx_embeddings_created_at_brin',
    'idx_embeddings_tenant_user_created',
    'idx_preferences_created_at_brin'
)
ORDER BY tablename, indexname;
