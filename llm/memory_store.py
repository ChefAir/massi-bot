"""
Massi-Bot LLM - Memory Store (U8)

Persists and retrieves subscriber memory facts using Supabase pgvector.
Implements the Park et al. (2023) memory scoring system:
  score = recency_weight × importance × semantic_relevance

Schema (run once in Supabase SQL Editor):
─────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS subscriber_memory (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sub_id      TEXT NOT NULL,
    model_id    UUID,
    fact        TEXT NOT NULL,
    category    TEXT,                    -- job, location, relationship, emotion, hobby, event
    embedding   vector(384),
    importance  FLOAT DEFAULT 0.5,       -- 0.0–1.0, set by extractor
    emotional_val FLOAT DEFAULT 0.0,     -- -1.0–1.0 (negative to positive)
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
        -- Park et al. composite score: recency × importance × relevance
        (EXTRACT(EPOCH FROM NOW()) - EXTRACT(EPOCH FROM m.created_at)) / -86400.0 * 0.35
        + m.importance * 0.3
        + (1 - (m.embedding <=> p_query_emb)) * 0.35
    DESC
    LIMIT p_limit;
END;
$$;
─────────────────────────────────────────

Setup steps:
  1. Open Supabase Dashboard → SQL Editor
  2. Run the CREATE EXTENSION + CREATE TABLE + CREATE INDEX statements above
  3. Run the CREATE OR REPLACE FUNCTION statement
  4. pip3 install sentence-transformers
  5. The model downloads automatically on first use (~90MB, cached)
"""

import os
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def _is_sim_mode() -> bool:
    """Return True if running in simulation mode (no DB writes)."""
    return os.environ.get("UNITYLINK_SIM_MODE", "").lower() in ("true", "1", "yes")


# ─────────────────────────────────────────────
# Lazy imports — sentence-transformers is large,
# only load when actually needed
# ─────────────────────────────────────────────

_encoder = None
_supabase = None


_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_EMBEDDING_DIM = 1024 if "bge-m3" in _EMBEDDING_MODEL else 384


def _get_encoder():
    """Lazy-load the sentence-transformer model. Configurable via EMBEDDING_MODEL env var."""
    global _encoder
    if _encoder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _encoder = SentenceTransformer(_EMBEDDING_MODEL)
            logger.info("RAG memory encoder loaded: %s (%d-dim)", _EMBEDDING_MODEL, _EMBEDDING_DIM)
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG memory disabled. "
                           "Run: pip3 install sentence-transformers")
            return None
    return _encoder


def _get_supabase():
    """Lazy-load Supabase client."""
    global _supabase
    if _supabase is None:
        try:
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            if url and key:
                _supabase = create_client(url, key)
        except Exception as exc:
            logger.warning("Supabase not available for memory store: %s", exc)
    return _supabase


def prewarm_encoder():
    """Pre-load the sentence-transformer model at startup (avoids cold-start latency)."""
    enc = _get_encoder()
    if enc:
        logger.info("Encoder pre-warmed successfully")
    return enc is not None


def _embed(text: str) -> Optional[list[float]]:
    """Generate a 384-dim embedding for the given text."""
    enc = _get_encoder()
    if enc is None:
        return None
    try:
        vec = enc.encode(text, normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


def _embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Generate 384-dim embeddings for multiple texts in one batch call."""
    enc = _get_encoder()
    if enc is None:
        return [None] * len(texts)
    try:
        vecs = enc.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vecs]
    except Exception as exc:
        logger.warning("Batch embedding failed: %s", exc)
        return [None] * len(texts)


# ─────────────────────────────────────────────
# Importance scoring by category
# ─────────────────────────────────────────────

_CATEGORY_IMPORTANCE: dict[str, float] = {
    "emotion": 0.9,       # Emotional disclosures — highest impact on GFE
    "event": 0.85,        # Life events — highly personal
    "relationship": 0.8,  # Relationship status — strong GFE hook
    "job": 0.6,           # Occupation — useful for flattery/conversation
    "location": 0.5,      # Location — moderate usefulness
    "hobby": 0.55,        # Hobbies — good conversation fuel
}


def _importance_for_category(category: str) -> float:
    return _CATEGORY_IMPORTANCE.get(category, 0.5)


# ─────────────────────────────────────────────
# Emotional valence scoring (U6)
# ─────────────────────────────────────────────

def _estimate_emotional_valence(fact: str, category: str) -> float:
    """Estimate emotional valence from -1.0 (very negative) to 1.0 (very positive)."""
    lower = fact.lower()

    # Strong negative signals
    if any(w in lower for w in [
        "died", "death", "funeral", "cancer", "hospital",
        "fired", "lost my", "divorce", "breakup", "depressed", "suicidal",
    ]):
        return -0.8
    # Moderate negative
    if any(w in lower for w in [
        "stressed", "lonely", "sad", "rough day", "struggling",
        "tired", "overwhelmed", "anxious", "worried",
    ]):
        return -0.5
    # Moderate positive
    if any(w in lower for w in [
        "promoted", "new job", "excited", "happy", "great day",
        "love", "amazing", "blessed", "grateful",
    ]):
        return 0.6
    # Strong positive
    if any(w in lower for w in [
        "married", "engaged", "baby", "won", "graduated", "dream job", "best day",
    ]):
        return 0.8
    # Category-based defaults
    if category == "emotion":
        return -0.3  # Emotions disclosed tend to be negative (loneliness, stress)
    return 0.0


# ─────────────────────────────────────────────
# Store + retrieve
# ─────────────────────────────────────────────

async def store_memory(
    sub_id: str,
    fact: str,
    category: str = "general",
    model_id: Optional[str] = None,
    emotional_val: float = 0.0,
    original_quote: Optional[str] = None,
    temporal_intent: str = "present",
) -> bool:
    """
    Store a memory fact with its embedding.

    Returns True if stored successfully (or refreshed a duplicate), False if skipped/failed.
    Silently skips if encoder or Supabase is unavailable.

    Deduplication (U5): Before inserting, checks if a semantically similar fact
    already exists (cosine similarity > 0.85). If found, refreshes last_accessed
    on the existing row instead of inserting a duplicate.
    """
    if _is_sim_mode():
        logger.debug("Sim mode: skipping memory store for sub %s", sub_id)
        return False

    sb = _get_supabase()
    if sb is None:
        return False

    embedding = _embed(fact)
    if embedding is None:
        return False

    importance = _importance_for_category(category)

    # U6: Auto-score emotional valence if not explicitly provided
    emotional_val = emotional_val or _estimate_emotional_valence(fact, category)

    # U5: Dedup + contradiction check
    try:
        dedup_result = sb.rpc("match_subscriber_memory", {
            "p_sub_id": sub_id,
            "p_query_emb": embedding,
            "p_limit": 3,
            "p_threshold": 0.60,  # Broader search for contradiction detection
        }).execute()

        if dedup_result.data:
            for existing in dedup_result.data:
                sim = existing.get("similarity", 0)
                existing_cat = existing.get("category", "")
                existing_fact = existing.get("fact", "")
                existing_id = existing.get("id")

                # Near-duplicate (sim > 0.78): refresh instead of inserting
                if sim > 0.78:
                    sb.table("subscriber_memory").update({
                        "last_accessed": datetime.now().isoformat()
                    }).eq("id", existing_id).execute()
                    logger.debug("Dedup: refreshed existing memory for sub %s: %s", sub_id, fact[:40])
                    return True

                # Contradiction detection (same category, moderate similarity 0.60-0.78)
                # Same topic but different content = likely a life update
                if (existing_cat == category
                        and category in ("location", "job", "relationship")
                        and 0.60 <= sim < 0.78):
                    # Mark old fact as superseded by updating its importance to near-zero
                    try:
                        sb.table("subscriber_memory").update({
                            "importance": 0.05,
                            "fact": f"[SUPERSEDED] {existing_fact}",
                        }).eq("id", existing_id).execute()
                        logger.info(
                            "Contradiction detected for sub %s: '%s' superseded by '%s'",
                            sub_id, existing_fact[:40], fact[:40],
                        )
                    except Exception:
                        pass  # Non-critical
    except Exception:
        pass  # Dedup/contradiction check failed, proceed with insert

    try:
        insert_data = {
            "sub_id": sub_id,
            "model_id": str(model_id) if model_id else None,
            "fact": fact,
            "category": category,
            "embedding": embedding,
            "importance": importance,
            "emotional_val": emotional_val,
        }
        if original_quote:
            insert_data["original_quote"] = original_quote
        if temporal_intent and temporal_intent != "present":
            insert_data["temporal_intent"] = temporal_intent
        sb.table("subscriber_memory").insert(insert_data).execute()
        logger.debug("Stored memory for sub %s: [%s] %s", sub_id, category, fact[:60])
        return True
    except Exception as exc:
        logger.warning("Memory store failed for sub %s: %s", sub_id, exc)
        return False


async def retrieve_memories(
    sub_id: str,
    query: str,
    limit: int = 5,
    threshold: float = 0.65,
) -> list[str]:
    """
    Retrieve the most relevant memory facts for a given query.

    Uses Supabase RPC to run the composite Park et al. scoring:
      score = 0.35×recency + 0.30×importance + 0.35×relevance

    Returns list of fact strings, most relevant first.
    Falls back to empty list on any failure.
    """
    sb = _get_supabase()
    if sb is None:
        return []

    query_embedding = _embed(query)
    if query_embedding is None:
        return []

    try:
        result = sb.rpc("match_subscriber_memory", {
            "p_sub_id": sub_id,
            "p_query_emb": query_embedding,
            "p_limit": limit,
            "p_threshold": threshold,
        }).execute()

        rows = result.data or []
        # Update last_accessed + increment recall_count for Ebbinghaus forgetting curve
        ids = [r["id"] for r in rows if "id" in r]
        if ids:
            try:
                sb.rpc("touch_memory_recall", {"p_ids": ids}).execute()
            except Exception:
                # Fallback if RPC not deployed yet
                try:
                    sb.table("subscriber_memory").update({
                        "last_accessed": datetime.now().isoformat()
                    }).in_("id", ids).execute()
                except Exception:
                    pass  # Non-critical

        facts = []
        for r in rows:
            if "fact" not in r:
                continue
            fact = r["fact"]
            # Enrich with temporal context if available
            temporal = r.get("temporal_intent", "")
            if temporal and temporal != "present":
                fact = f"[{temporal.upper()}] {fact}"
            facts.append(fact)
        return facts

    except Exception as exc:
        logger.warning("Memory retrieve failed for sub %s: %s", sub_id, exc)
        return []


async def retrieve_memories_with_metadata(
    sub_id: str,
    query: str,
    limit: int = 5,
    threshold: float = 0.65,
) -> list[dict]:
    """
    Retrieve memories with full metadata (fact, category, emotional_val, etc.).

    Returns list of dicts with keys: id, fact, category, importance, emotional_val,
    created_at, similarity. Falls back to empty list on any failure.
    """
    sb = _get_supabase()
    if sb is None:
        return []

    query_embedding = _embed(query)
    if query_embedding is None:
        return []

    try:
        result = sb.rpc("match_subscriber_memory", {
            "p_sub_id": sub_id,
            "p_query_emb": query_embedding,
            "p_limit": limit,
            "p_threshold": threshold,
        }).execute()

        rows = result.data or []
        # Update last_accessed + increment recall_count for Ebbinghaus forgetting curve
        ids = [r["id"] for r in rows if "id" in r]
        if ids:
            try:
                sb.rpc("touch_memory_recall", {"p_ids": ids}).execute()
            except Exception:
                # Fallback if RPC not deployed yet
                try:
                    sb.table("subscriber_memory").update({
                        "last_accessed": datetime.now().isoformat()
                    }).in_("id", ids).execute()
                except Exception:
                    pass  # Non-critical

        return rows

    except Exception as exc:
        logger.warning("Memory retrieve (metadata) failed for sub %s: %s", sub_id, exc)
        return []


async def count_memories(sub_id: str) -> int:
    """Return how many memory facts are stored for this subscriber."""
    sb = _get_supabase()
    if sb is None:
        return 0
    try:
        result = sb.table("subscriber_memory") \
            .select("id", count="exact") \
            .eq("sub_id", sub_id) \
            .execute()
        return result.count or 0
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Persona self-identity memory (U8 extension)
# Stores facts the bot generates about "herself"
# ─────────────────────────────────────────────

async def store_persona_fact(model_id: str, fact: str, category: str = "general") -> bool:
    """Store a fact about the persona (what the bot said about herself)."""
    if _is_sim_mode():
        logger.debug("Sim mode: skipping persona fact store")
        return False

    sb = _get_supabase()
    if sb is None:
        return False
    embedding = _embed(fact)
    if embedding is None:
        return False
    try:
        sb.table("persona_memory").insert({
            "model_id": str(model_id),
            "fact": fact,
            "category": category,
            "embedding": embedding,
        }).execute()
        logger.debug("Stored persona fact for model %s: %s", model_id, fact[:60])
        return True
    except Exception as exc:
        logger.warning("Persona memory store failed: %s", exc)
        return False


async def retrieve_persona_facts(
    model_id: str,
    query: Optional[str] = None,
    limit: int = 5,
) -> list[str]:
    """
    Retrieve persona facts for injection into system prompt.

    If query is provided, uses semantic search via match_persona_memory RPC.
    Otherwise falls back to recency-based retrieval.
    """
    sb = _get_supabase()
    if sb is None:
        return []

    # Semantic retrieval if query provided and embedding available
    if query:
        query_embedding = _embed(query)
        if query_embedding:
            try:
                result = sb.rpc("match_persona_memory", {
                    "p_model_id": str(model_id),
                    "p_query_emb": query_embedding,
                    "p_limit": limit,
                    "p_threshold": 0.50,
                }).execute()
                if result.data:
                    return [r["fact"] for r in result.data if "fact" in r]
            except Exception:
                pass  # Fall through to recency-based retrieval

    # Fallback: recency-based retrieval
    try:
        result = sb.table("persona_memory") \
            .select("fact") \
            .eq("model_id", str(model_id)) \
            .order("last_used", desc=True) \
            .limit(limit) \
            .execute()
        return [r["fact"] for r in (result.data or []) if "fact" in r]
    except Exception as exc:
        logger.warning("Persona memory retrieve failed: %s", exc)
        return []
