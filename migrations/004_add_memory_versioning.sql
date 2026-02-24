-- Migration 004: Add memory versioning columns for time-travel queries
-- Description: Adds valid_from, valid_until, version, superseded_by to embeddings
-- Version: 0.6.0
-- Date: 2026-02-24

-- Add versioning columns (idempotent)
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS superseded_by UUID;

-- Add index for time-range queries
CREATE INDEX IF NOT EXISTS ix_emb_user_valid ON embeddings (user_id, valid_from, valid_until);

-- Backfill: set valid_from = created_at for existing memories
UPDATE embeddings SET valid_from = created_at WHERE valid_from IS NULL;
