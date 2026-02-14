-- Migration: Fix vector dimensions to support variable embedding sizes
-- Description: Recreate vector columns without fixed dimensions
-- Version: 0.2.1
-- Date: 2026-02-14

-- For conversations table: Recreate embedding column
-- Step 1: Drop index
DROP INDEX IF EXISTS idx_conversations_embedding;

-- Step 2: Drop and recreate column
ALTER TABLE conversations DROP COLUMN IF EXISTS embedding;
ALTER TABLE conversations ADD COLUMN embedding vector;

-- Step 3: Recreate index
CREATE INDEX IF NOT EXISTS idx_conversations_embedding
ON conversations USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100)
WHERE embedding IS NOT NULL;

-- Note 1: Existing conversation data will lose embeddings (will be regenerated on next add_message)
-- Note 2: embeddings table should already support dynamic dimensions via __declare_last__
-- Note 3: After this migration, you can use any embedding dimension (384, 1024, 1536, etc.)
