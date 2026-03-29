-- Migration 002: Add OnlyFans media ID column to content_catalog
-- Run in Supabase SQL Editor at: supabase.com → your project → SQL Editor
-- This allows content pieces to be associated with OF Vault media IDs
-- alongside existing Fanvue media UUID column.

ALTER TABLE content_catalog
    ADD COLUMN IF NOT EXISTS of_media_id TEXT;

-- Index for fast lookup when selling PPV on OnlyFans
CREATE INDEX IF NOT EXISTS idx_content_catalog_of_media_id
    ON content_catalog(of_media_id)
    WHERE of_media_id IS NOT NULL;

-- Also add source column to distinguish live vs AI-generated content
ALTER TABLE content_catalog
    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'live'
    CHECK (source IN ('live', 'ai_generated'));

-- Index for filtering by source
CREATE INDEX IF NOT EXISTS idx_content_catalog_source
    ON content_catalog(source);

-- Verify
SELECT
    column_name,
    data_type,
    column_default
FROM information_schema.columns
WHERE table_name = 'content_catalog'
  AND column_name IN ('of_media_id', 'source', 'fanvue_media_uuid')
ORDER BY column_name;
