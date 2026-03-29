-- Migration 001: Add profile fields to models table
-- Run in: Supabase Dashboard → SQL Editor
-- Purpose: Support model profile onboarding flow via Telegram bot

ALTER TABLE models
  ADD COLUMN IF NOT EXISTS telegram_id BIGINT,
  ADD COLUMN IF NOT EXISTS fanvue_model_id TEXT,
  ADD COLUMN IF NOT EXISTS profile_json JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS onboarding_complete BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS notes TEXT;

-- Index for fast lookup by telegram_id
CREATE INDEX IF NOT EXISTS idx_models_telegram_id ON models(telegram_id);
