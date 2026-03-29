"""
Massi-Bot Multi-Agent — Context Builder

Pre-processes subscriber data, retrieves memories, and builds structured
context blocks that feed into all 5 agents. Runs before any LLM calls.

No LLM calls — pure code + database queries.
"""

import os
import sys
import logging
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from models import Subscriber, SubState
from llm.memory_manager import memory_manager
from llm.context_awareness import build_context_block, get_weather

logger = logging.getLogger(__name__)


async def build_context(
    sub: Subscriber,
    message: str,
    avatar=None,
    model_profile=None,
) -> dict:
    """
    Build the complete context package for all agents.

    Returns a dict with:
        - subscriber_summary: formatted subscriber profile string
        - memories: list of relevant memory strings from pgvector
        - emotional_note: emotional valence note if applicable
        - live_context: weather + time context string
        - persona_facts: list of things the bot has said about herself
        - conversation_history: last 10 messages formatted for LLM
        - tier_progress: dict with current tier info
        - spending_summary: formatted spending string
    """
    result = {}

    # Subscriber summary
    result["subscriber_summary"] = _format_subscriber(sub)

    # Spending summary
    result["spending_summary"] = _format_spending(sub)

    # Tier progress
    result["tier_progress"] = {
        "current_loop": sub.current_loop_number or 0,
        "tiers_purchased": max(0, (sub.current_loop_number or 1) - 1),
        "total_possible": 6,
        "total_spent": sub.spending.total_spent,
        "is_buyer": sub.spending.is_buyer,
        "gfe_message_count": getattr(sub, 'gfe_message_count', 0),
        "sext_consent_given": getattr(sub, 'sext_consent_given', False),
    }

    # RAG memories (semantic search on current message)
    try:
        memories_result = await memory_manager.get_context_memories(sub, message)
        result["memories"] = memories_result if memories_result else []
        result["emotional_note"] = ""
        if isinstance(memories_result, dict):
            result["memories"] = memories_result.get("memories", [])
            result["emotional_note"] = memories_result.get("emotional_note", "")
    except Exception as e:
        logger.warning("Memory retrieval failed: %s", e)
        result["memories"] = []
        result["emotional_note"] = ""

    # Persona self-identity facts
    try:
        persona_facts = await memory_manager.get_persona_context(query=message)
        result["persona_facts"] = persona_facts if persona_facts else []
    except Exception:
        result["persona_facts"] = []

    # Profile summary (generated every 50 messages when enough facts exist)
    try:
        profile_summary = await memory_manager.maybe_generate_profile_summary(sub)
        result["profile_summary"] = profile_summary
    except Exception:
        result["profile_summary"] = ""

    # Live context (weather + time)
    # Model profile location overrides avatar location
    try:
        persona_loc = "Miami"  # default
        if model_profile and model_profile.stated_location:
            persona_loc = model_profile.stated_location
        elif avatar and avatar.persona:
            persona_loc = avatar.persona.location_story
        weather = await get_weather(persona_loc)
        result["live_context"] = build_context_block(
            fan_messages=sub.recent_messages[-5:] if sub.recent_messages else [],
            avatar_location=persona_loc,
            weather=weather,
        )
    except Exception:
        result["live_context"] = ""

    # Store model profile in context for agents to use
    result["model_profile"] = model_profile

    # Conversation history (last 10 messages, formatted)
    history = sub.recent_messages[-10:] if sub.recent_messages else []
    result["conversation_history"] = _format_history(history)

    # Callback references (things the fan has told us)
    result["callback_refs"] = sub.callback_references[-10:] if sub.callback_references else []

    return result


def _format_subscriber(sub: Subscriber) -> str:
    """Format subscriber profile for agent prompts."""
    name = sub.display_name or sub.username or "baby"
    parts = [f"Name: {name}"]

    if sub.qualifying and sub.qualifying.age:
        parts.append(f"Age: {sub.qualifying.age}")
    if sub.qualifying and sub.qualifying.location:
        parts.append(f"Location: {sub.qualifying.location}")
    if sub.qualifying and sub.qualifying.occupation:
        parts.append(f"Job: {sub.qualifying.occupation}")
    if sub.qualifying and sub.qualifying.relationship_status:
        parts.append(f"Relationship: {sub.qualifying.relationship_status}")

    parts.append(f"Messages sent: {sub.message_count}")
    parts.append(f"Total spent: ${sub.spending.total_spent:.2f}")
    parts.append(f"PPVs purchased: {sub.spending.ppv_count}")
    parts.append(f"Whale score: {sub.whale_score:.0f}/100")
    parts.append(f"GFE messages: {getattr(sub, 'gfe_message_count', 0)}")
    parts.append(f"Sext consent: {'yes' if getattr(sub, 'sext_consent_given', False) else 'no'}")

    return "\n".join(parts)


def _format_spending(sub: Subscriber) -> str:
    """Format spending details for Sales Strategist."""
    s = sub.spending
    parts = [
        f"Total: ${s.total_spent:.2f}",
        f"PPVs bought: {s.ppv_count}",
        f"PPVs rejected: {s.rejected_ppv_count}",
        f"Avg PPV price: ${s.avg_ppv_price:.2f}" if s.ppv_count > 0 else "No purchases yet",
        f"Highest single: ${s.highest_single_purchase:.2f}" if s.highest_single_purchase > 0 else "",
        f"Tier: {s.tier.value}" if hasattr(s, 'tier') else "",
    ]
    return "\n".join(p for p in parts if p)


def _format_history(messages: list[dict]) -> str:
    """Format conversation history for agent prompts."""
    if not messages:
        return "(no prior messages)"

    lines = []
    for msg in messages:
        role = "Fan" if msg.get("role") in ("sub", "user") else "Her"
        content = msg.get("content", "")[:200]
        lines.append(f"{role}: {content}")

    return "\n".join(lines)
