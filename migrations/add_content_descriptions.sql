-- Add content description columns to content_catalog
-- Run via Supabase SQL Editor
ALTER TABLE content_catalog
  ADD COLUMN IF NOT EXISTS bundle_context TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS clothing_description TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS location_description TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS mood TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS tease_hint TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS key_detail TEXT DEFAULT '';
