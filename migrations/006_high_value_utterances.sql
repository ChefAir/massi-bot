-- Migration 006: High-Value Utterance Registry
-- ─────────────────────────────────────────────
-- NO SCHEMA CHANGE REQUIRED.
--
-- The HV registry fields live inside the existing `qualifying_data` JSONB column
-- on the subscribers table:
--   qualifying_data.high_value_utterances         Dict[category_name, list[str]]
--   qualifying_data.high_value_utterances_archive Dict[category_name, list[{hash, ts}]]
--   qualifying_data.ppv_heads_up_count            int
--   qualifying_data.ppv_threshold_jitter          int | null
--   qualifying_data.last_consent_decline_at_msg_count int | null
--
-- Persistence layer (persistence/subscriber_store.py) already reads/writes these
-- fields. JSONB accepts arbitrary keys, so no ALTER TABLE needed.
--
-- This file exists as documentation of the schema contract. If at 10K+ subs
-- the JSONB column grows large, we can migrate to dedicated columns later.

-- Verification query (run in Supabase SQL Editor to confirm shape after first write):
-- SELECT
--     id,
--     qualifying_data->'high_value_utterances' AS hv,
--     qualifying_data->'ppv_heads_up_count' AS heads_up_count,
--     qualifying_data->'ppv_threshold_jitter' AS threshold_jitter
-- FROM subscribers
-- WHERE qualifying_data ? 'high_value_utterances'
-- LIMIT 5;

SELECT 'Migration 006: no schema change required — all HV fields live in qualifying_data JSONB' AS status;
