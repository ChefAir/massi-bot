"""
Massi-Bot LLM - Memory Manager (U8)

Orchestrates the full RAG memory lifecycle:
  1. Auto-extract facts every N exchanges (Mem0 pattern)
  2. Store embeddings to Supabase pgvector (memory_store)
  3. Retrieve relevant memories for current context
  4. Format retrieved memories for system prompt injection

Integration:
  - Called by llm_router.route() to inject memories into prompts
  - Also called by llm_router after each message to extract and store new facts

Usage in llm_router:
    from llm.memory_manager import memory_manager

    # Before building prompt:
    memories = await memory_manager.get_context_memories(sub, message)

    # After successful LLM response (every EXTRACT_EVERY_N messages):
    await memory_manager.maybe_extract_and_store(sub, message)

    # In build_system_prompt(), pass memories to inject into prompt.
"""

import os
import logging
from typing import Optional

from llm.memory_store import store_memory, retrieve_memories, retrieve_memories_with_metadata
from llm.memory_store import store_persona_fact, retrieve_persona_facts
from llm.memory_extractor import extract_facts, extract_facts_llm

logger = logging.getLogger(__name__)

EXTRACT_EVERY_N = 5  # Auto-extract after every 5 fan messages (Mem0 pattern)


class MemoryManager:
    """
    Thin orchestration layer over memory_store + memory_extractor.
    All methods are async and silently no-op if pgvector is unavailable.
    """

    def __init__(self):
        self._last_emotional_context: str = ""

    async def maybe_extract_and_store(
        self,
        sub,
        message: str,
        model_id: Optional[str] = None,
    ) -> int:
        """
        Extract facts from the fan's message and store them.
        Uses LLM extraction (Haiku) for full-context facts with temporal intent.
        Falls back to regex if LLM is unavailable.

        Returns number of new facts stored.
        """
        # Build recent context from conversation history
        recent_context = []
        if sub.recent_messages:
            for msg in sub.recent_messages[-6:]:
                role = "Fan" if msg.get("role") in ("sub", "user") else "Bot"
                content = msg.get("content", "")
                if content:
                    recent_context.append(f"{role}: {content}")

        # Primary: LLM-based extraction (full context preservation)
        llm_facts = await extract_facts_llm(message, recent_context)

        if llm_facts:
            stored = 0
            for f in llm_facts:
                ok = await store_memory(
                    sub_id=sub.sub_id,
                    fact=f["fact"],
                    category=f.get("category", "general"),
                    model_id=model_id,
                    original_quote=message,
                    temporal_intent=f.get("temporal", "present"),
                )
                if ok:
                    stored += 1
                    # Also update callback_references for backward compatibility
                    if f["fact"].lower() not in {r.lower() for r in sub.callback_references}:
                        sub.callback_references.append(f["fact"])
            if stored:
                logger.debug("MemoryManager: stored %d LLM-extracted facts for sub %s", stored, sub.sub_id)
            # Keep callback_references bounded
            if len(sub.callback_references) > 30:
                sub.callback_references = sub.callback_references[-30:]
            return stored

        # Fallback: regex-based extraction
        regex_facts = extract_facts(message)
        if not regex_facts:
            return 0

        stored = 0
        for fact in regex_facts:
            category = _infer_category(fact)
            ok = await store_memory(
                sub_id=sub.sub_id,
                fact=fact,
                category=category,
                model_id=model_id,
                original_quote=message,
            )
            if ok:
                stored += 1

        if stored:
            logger.debug("MemoryManager: stored %d regex-extracted facts for sub %s", stored, sub.sub_id)
        return stored

    async def get_context_memories(
        self,
        sub,
        current_message: str,
        limit: int = 4,
    ) -> list[str]:
        """
        Retrieve the most relevant memories for the current message.
        Returns up to `limit` fact strings, or [] if pgvector unavailable.

        Also computes emotional context from recent memory valence scores
        and stores it on self._last_emotional_context for use by format_for_prompt.

        These are injected into the system prompt as "Long-term memories".
        """
        self._last_emotional_context = ""
        if not current_message:
            return []

        rows = await retrieve_memories_with_metadata(
            sub_id=sub.sub_id,
            query=current_message,
            limit=limit,
        )

        if not rows:
            return []

        # U6: Compute overall emotional tone from retrieved memories
        valences = [r.get("emotional_val", 0.0) for r in rows if r.get("emotional_val") is not None]
        if valences:
            avg_valence = sum(valences) / len(valences)
            if avg_valence <= -0.5:
                self._last_emotional_context = (
                    "He's been going through a rough time recently. "
                    "Be extra nurturing and supportive."
                )
            elif avg_valence >= 0.5:
                self._last_emotional_context = (
                    "He's in a good place. Match his energy, be playful."
                )

        return [r["fact"] for r in rows if "fact" in r]

    def format_for_prompt(self, memories: list[str], emotional_context: str = "") -> str:
        """
        Format retrieved memories as a prompt-injectable block.
        Returns empty string if no memories.

        Memories may include temporal labels like [FUTURE] or [PAST].
        These help the LLM understand the context of each fact.
        """
        if not memories:
            return ""
        lines = "\n".join(f"  - {m}" for m in memories)
        block = (
            "Long-term memories (things he's shared with you over time).\n"
            "Labels: [FUTURE] = something he PLANS to do, [PAST] = something that already happened.\n"
            "No label = current/ongoing. Use these to reference his life accurately.\n"
            f"{lines}"
        )

        # Use auto-computed emotional context if none explicitly passed
        ctx = emotional_context or getattr(self, "_last_emotional_context", "")
        if ctx:
            block += f"\n\nEmotional note: {ctx}"
        return block


    async def maybe_store_persona_facts(self, bot_response: str, model_id: str = None) -> int:
        """Extract and store persona self-referential facts from bot response."""
        if not model_id:
            model_id = os.environ.get("FANVUE_MODEL_ID", "")
        if not model_id:
            return 0
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts(bot_response)
        stored = 0
        for category, fact in facts:
            if await store_persona_fact(model_id, fact, category):
                stored += 1
        if stored:
            logger.debug("MemoryManager: stored %d persona facts for model %s", stored, model_id)
        return stored

    async def get_persona_context(
        self,
        model_id: str = None,
        query: str = None,
        limit: int = 5,
    ) -> list[str]:
        """Get persona facts for system prompt injection. Uses semantic search if query provided."""
        if not model_id:
            model_id = os.environ.get("FANVUE_MODEL_ID", "")
        if not model_id:
            return []
        return await retrieve_persona_facts(model_id, query=query, limit=limit)

    async def maybe_generate_profile_summary(
        self,
        sub,
        model_id: Optional[str] = None,
    ) -> str:
        """
        Generate a concise profile summary from accumulated facts.
        Runs every 50 messages when 5+ facts exist.
        Returns cached summary if recently generated, or empty string.
        """
        # Only run every 50 messages
        if sub.message_count % 50 != 0 or sub.message_count == 0:
            # Check if we have a cached summary
            return getattr(sub, '_profile_summary', '')

        from llm.memory_store import count_memories
        fact_count = await count_memories(sub.sub_id)
        if fact_count < 5:
            return ''

        # Retrieve all relevant memories for summary
        all_facts = await retrieve_memories(
            sub_id=sub.sub_id,
            query="personal profile identity background",
            limit=15,
            threshold=0.40,
        )

        if not all_facts or len(all_facts) < 3:
            return ''

        # Generate summary via Haiku
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return ''

            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=10.0,
            )

            facts_block = "\n".join(f"- {f}" for f in all_facts)
            completion = await client.chat.completions.create(
                model="anthropic/claude-haiku-4-5-20251001",
                messages=[
                    {"role": "system", "content": (
                        "Summarize these facts about a person into a 2-3 sentence profile. "
                        "Write in third person. Include: name (if known), location, job, "
                        "relationship status, key interests, and emotional state. "
                        "Respect temporal labels: [FUTURE] = plans, [PAST] = history. "
                        "Be concise and natural."
                    )},
                    {"role": "user", "content": f"Facts:\n{facts_block}"},
                ],
                max_tokens=150,
                temperature=0.0,
            )

            summary = completion.choices[0].message.content.strip()
            sub._profile_summary = summary
            logger.info("Generated profile summary for sub %s: %s", sub.sub_id, summary[:80])
            return summary

        except Exception as e:
            logger.warning("Profile summary generation failed: %s", str(e)[:80])
            return ''


def _infer_category(fact: str) -> str:
    """Infer memory category from the fact string prefix set by memory_extractor."""
    fact_lower = fact.lower()
    if fact_lower.startswith("works as") or "job" in fact_lower[:20]:
        return "job"
    if fact_lower.startswith("from/in") or "location" in fact_lower[:20]:
        return "location"
    if fact_lower.startswith("relationship"):
        return "relationship"
    if fact_lower.startswith("feeling"):
        return "emotion"
    if fact_lower.startswith("into") or "hobby" in fact_lower[:20]:
        return "hobby"
    if any(w in fact_lower for w in ["wants to", "plans to", "going to", "saving for", "hoping to"]):
        return "plan"
    return "event"


# Singleton
memory_manager = MemoryManager()
