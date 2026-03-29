-- Migration 003: Add context fields to subscriber_memory
-- Supports LLM-based fact extraction with temporal intent + verbatim quotes
-- Non-destructive: adds nullable columns, existing data unaffected

ALTER TABLE subscriber_memory ADD COLUMN IF NOT EXISTS original_quote TEXT;
ALTER TABLE subscriber_memory ADD COLUMN IF NOT EXISTS temporal_intent TEXT DEFAULT 'present';

-- Update the RPC function to return the new fields
CREATE OR REPLACE FUNCTION match_subscriber_memory(
    p_sub_id    TEXT,
    p_query_emb vector(384),
    p_limit     INT DEFAULT 5,
    p_threshold FLOAT DEFAULT 0.65
)
RETURNS TABLE (
    id UUID, fact TEXT, category TEXT,
    importance FLOAT, emotional_val FLOAT,
    created_at TIMESTAMPTZ, similarity FLOAT,
    original_quote TEXT, temporal_intent TEXT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id, m.fact, m.category,
        m.importance, m.emotional_val,
        m.created_at,
        1 - (m.embedding <=> p_query_emb) AS similarity,
        m.original_quote, m.temporal_intent
    FROM subscriber_memory m
    WHERE m.sub_id = p_sub_id
      AND 1 - (m.embedding <=> p_query_emb) >= p_threshold
    ORDER BY
        -- Park et al. composite score: recency × importance × relevance
        (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM m.created_at)) / -86400.0 * 0.35
        + m.importance * 0.3
        + (1 - (m.embedding <=> p_query_emb)) * 0.35
    DESC
    LIMIT p_limit;
END;
$$;
