-- Migration 006: Ebbinghaus Forgetting Curve
-- Adds recall_count to subscriber_memory for stability-based decay.
-- Memories recalled more often decay slower (exponential reinforcement).

-- Add recall_count column
ALTER TABLE subscriber_memory ADD COLUMN IF NOT EXISTS recall_count INT DEFAULT 0;

-- Helper RPC: touch memories on retrieval (increment recall_count + update last_accessed)
CREATE OR REPLACE FUNCTION touch_memory_recall(p_ids UUID[])
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE subscriber_memory
    SET recall_count = COALESCE(recall_count, 0) + 1,
        last_accessed = now()
    WHERE id = ANY(p_ids);
END;
$$;

-- Update the match_subscriber_memory RPC to use Ebbinghaus decay instead of linear recency.
-- Formula: R = exp(-age_days / (base_stability + recall_count))
-- This replaces the linear recency_decay in the Park et al. composite score.
CREATE OR REPLACE FUNCTION match_subscriber_memory(
    p_sub_id TEXT,
    p_query_emb vector(384),
    p_limit INT DEFAULT 4,
    p_threshold FLOAT DEFAULT 0.65
)
RETURNS TABLE (
    id UUID,
    fact TEXT,
    category TEXT,
    importance FLOAT,
    emotional_val FLOAT,
    original_quote TEXT,
    temporal_intent TEXT,
    recall_count INT,
    similarity FLOAT,
    composite_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        m.id,
        m.fact,
        m.category,
        m.importance,
        m.emotional_val,
        m.original_quote,
        m.temporal_intent,
        m.recall_count,
        1 - (m.embedding <=> p_query_emb) AS similarity,
        -- Park et al. composite with Ebbinghaus recency:
        -- 0.35 * ebbinghaus_recency + 0.30 * importance + 0.35 * cosine_similarity
        (
            0.35 * EXP(
                -EXTRACT(EPOCH FROM (now() - COALESCE(m.last_accessed, m.created_at))) / 86400.0
                / GREATEST(1.0 + COALESCE(m.recall_count, 0), 1.0)
            )
            + 0.30 * COALESCE(m.importance, 0.5)
            + 0.35 * (1 - (m.embedding <=> p_query_emb))
        ) AS composite_score
    FROM subscriber_memory m
    WHERE m.sub_id = p_sub_id
      AND (1 - (m.embedding <=> p_query_emb)) >= p_threshold
    ORDER BY composite_score DESC
    LIMIT p_limit;
END;
$$;
