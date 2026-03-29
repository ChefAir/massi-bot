-- Persona self-identity memory table
-- Stores facts the bot generates about "herself" for consistency
CREATE TABLE IF NOT EXISTS persona_memory (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    model_id    UUID NOT NULL,
    fact        TEXT NOT NULL,
    category    TEXT,           -- hobby, daily_life, opinion, food, fashion, fitness, relationship_view
    embedding   vector(384),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    last_used   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS persona_memory_model_id_idx
    ON persona_memory (model_id);

CREATE INDEX IF NOT EXISTS persona_memory_embedding_idx
    ON persona_memory
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);
