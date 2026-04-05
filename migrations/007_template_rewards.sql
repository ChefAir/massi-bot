-- Migration 007: Contextual Bandit Template Rewards
-- Tracks per-template success/failure counts for Thompson Sampling selection.

CREATE TABLE IF NOT EXISTS template_rewards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_hash TEXT NOT NULL,
    avatar_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    time_period TEXT NOT NULL DEFAULT '',
    successes INT DEFAULT 0,
    failures INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_template_rewards_lookup
    ON template_rewards(template_hash, avatar_id, state, time_period);

CREATE INDEX IF NOT EXISTS idx_template_rewards_avatar_state
    ON template_rewards(avatar_id, state, time_period);
