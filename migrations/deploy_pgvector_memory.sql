-- Massi-Bot pgvector Memory Store Migration
-- Implements Park et al. (2023) memory scoring for subscriber fact retrieval
-- Run in Supabase SQL Editor

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS subscriber_memory (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sub_id      TEXT NOT NULL,
    model_id    UUID,
    fact        TEXT NOT NULL,
    category    TEXT,                    -- job, location, relationship, emotion, hobby, event
    embedding   vector(384),
    importance  FLOAT DEFAULT 0.5,       -- 0.0-1.0, set by extractor
    emotional_val FLOAT DEFAULT 0.0,     -- -1.0-1.0 (negative to positive)
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_accessed TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS subscriber_memory_sub_id_idx
    ON subscriber_memory (sub_id);

CREATE INDEX IF NOT EXISTS subscriber_memory_embedding_idx
    ON subscriber_memory
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- RPC function for scored similarity search
CREATE OR REPLACE FUNCTION match_subscriber_memory(
    p_sub_id    TEXT,
    p_query_emb vector(384),
    p_limit     INT DEFAULT 5,
    p_threshold FLOAT DEFAULT 0.65
)
RETURNS TABLE (
    id UUID, fact TEXT, category TEXT,
    importance FLOAT, emotional_val FLOAT,
    created_at TIMESTAMPTZ, similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id, m.fact, m.category,
        m.importance, m.emotional_val,
        m.created_at,
        1 - (m.embedding <=> p_query_emb) AS similarity
    FROM subscriber_memory m
    WHERE m.sub_id = p_sub_id
      AND 1 - (m.embedding <=> p_query_emb) >= p_threshold
    ORDER BY
        -- Park et al. composite score: recency x importance x relevance
        (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM m.created_at)) / -86400.0 * 0.35
        + m.importance * 0.3
        + (1 - (m.embedding <=> p_query_emb)) * 0.35
    DESC
    LIMIT p_limit;
END;
$$;
