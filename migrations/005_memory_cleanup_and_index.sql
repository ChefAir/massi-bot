-- Migration 005: Memory cleanup function + subscriber lookup index
-- Run in Supabase SQL Editor

-- ═══════════════════════════════════════════════════════════════
-- F-09: Memory cleanup function
-- Deletes old low-importance memories that haven't been accessed recently.
-- Run monthly via Supabase scheduled function or manually.
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION cleanup_old_memories()
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM subscriber_memory
    WHERE created_at < NOW() - INTERVAL '180 days'
      AND importance < 0.5
      AND last_accessed < NOW() - INTERVAL '90 days'
      AND fact NOT LIKE '[SUPERSEDED]%';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Also clean up superseded facts older than 30 days
    DELETE FROM subscriber_memory
    WHERE fact LIKE '[SUPERSEDED]%'
      AND created_at < NOW() - INTERVAL '30 days';

    GET DIAGNOSTICS deleted_count = deleted_count + ROW_COUNT;

    RETURN deleted_count;
END;
$$;

-- ═══════════════════════════════════════════════════════════════
-- F-23: Composite index for subscriber lookup
-- The most common query: WHERE platform=X AND platform_user_id=Y AND model_id=Z
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_subscribers_lookup
    ON subscribers(platform, platform_user_id, model_id);

-- ═══════════════════════════════════════════════════════════════
-- F-28: Embedding index on persona_memory for semantic retrieval
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS persona_memory_embedding_idx
    ON persona_memory
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- Semantic search function for persona facts
CREATE OR REPLACE FUNCTION match_persona_memory(
    p_model_id  TEXT,
    p_query_emb vector(384),
    p_limit     INT DEFAULT 5,
    p_threshold FLOAT DEFAULT 0.50
)
RETURNS TABLE (
    id UUID, fact TEXT, category TEXT,
    created_at TIMESTAMPTZ, similarity FLOAT
)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        pm.id, pm.fact, pm.category,
        pm.created_at,
        1 - (pm.embedding <=> p_query_emb) AS similarity
    FROM persona_memory pm
    WHERE pm.model_id = p_model_id::UUID
      AND 1 - (pm.embedding <=> p_query_emb) >= p_threshold
    ORDER BY similarity DESC
    LIMIT p_limit;
END;
$$;
