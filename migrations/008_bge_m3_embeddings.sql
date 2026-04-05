-- Migration 008: BGE-M3 Embedding Upgrade (384-dim -> 1024-dim)
--
-- Upgrades from all-MiniLM-L6-v2 (384-dim, ~56 MTEB) to BGE-M3 (1024-dim, ~70+ MTEB).
-- This provides ~15-20 point retrieval quality improvement.
--
-- IMPORTANT: After running this migration, you MUST re-embed all existing memories.
-- Run the re-embedding script: python3 setup/reembed_memories.py
--
-- If you want to keep using MiniLM (384-dim), set EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
-- in your .env and do NOT run this migration.

-- Alter subscriber_memory embedding column to 1024 dimensions
ALTER TABLE subscriber_memory ALTER COLUMN embedding TYPE vector(1024);

-- Alter persona_memory embedding column to 1024 dimensions
ALTER TABLE persona_memory ALTER COLUMN embedding TYPE vector(1024);

-- Drop and recreate IVFFlat indices for new dimension
DROP INDEX IF EXISTS idx_subscriber_memory_embedding;
CREATE INDEX idx_subscriber_memory_embedding ON subscriber_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

DROP INDEX IF EXISTS idx_persona_memory_embedding;
CREATE INDEX IF NOT EXISTS idx_persona_memory_embedding ON persona_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Update the match_subscriber_memory RPC parameter type
CREATE OR REPLACE FUNCTION match_subscriber_memory(
    p_sub_id TEXT,
    p_query_emb vector(1024),
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
