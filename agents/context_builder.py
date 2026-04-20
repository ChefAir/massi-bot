"""
Massi-Bot — Context Builder

Pre-processes subscriber data, retrieves memories, and builds structured
context blocks that feed into the single agent. Runs before any LLM calls.

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

    # Tier progress — prefer ppv_count (actual purchases) over current_loop_number (send counter)
    # because simulated purchases / webhook delays can leave current_loop out of sync with reality.
    ppv_count_actual = sub.spending.ppv_count if sub.spending else 0
    tiers_purchased_code = max(0, (sub.current_loop_number or 1) - 1)
    tiers_purchased = max(ppv_count_actual, tiers_purchased_code)
    result["tier_progress"] = {
        "current_loop": sub.current_loop_number or 0,
        "tiers_purchased": tiers_purchased,
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

    # ─────────────────────────────────────────────
    # SYNTHESIS FIELDS (new) — prose summaries the Director uses to reason about the moment
    # ─────────────────────────────────────────────
    try:
        result["relationship_summary"] = _format_relationship_summary(sub)
    except Exception as e:
        logger.debug("relationship_summary failed: %s", e)
        result["relationship_summary"] = ""

    try:
        result["session_arc"] = _format_session_arc(sub)
    except Exception as e:
        logger.debug("session_arc failed: %s", e)
        result["session_arc"] = ""

    try:
        result["open_threads"] = _extract_open_threads(sub)
    except Exception as e:
        logger.debug("open_threads failed: %s", e)
        result["open_threads"] = []

    try:
        result["tier_content_awareness"] = _format_tier_content_awareness(sub, model_profile)
    except Exception as e:
        logger.debug("tier_content_awareness failed: %s", e)
        result["tier_content_awareness"] = ""

    return result


def _format_relationship_summary(sub: Subscriber) -> str:
    """
    Prose synthesis of the relationship state at this moment.
    What tier are we on, how much has he paid, what's his buying rhythm, what patterns exist.
    """
    lines = []

    # Session position
    session_num = getattr(sub, "current_session_number", 1) or 1
    ppv_count = sub.spending.ppv_count if sub.spending else 0
    total_spent = sub.spending.total_spent if sub.spending else 0
    # Tier position within CURRENT session
    tier_position = (ppv_count % 6) + 1  # Next tier he'd see
    tiers_left_in_session = max(0, 6 - (ppv_count % 6))
    lines.append(
        f"Session {session_num}. Next tier to sell: tier {min(tier_position, 6)} of 6. "
        f"{tiers_left_in_session} tiers remaining in this session if he completes. "
        f"Total spent: ${total_spent:.2f}."
    )

    # Buying rhythm
    if ppv_count > 0:
        avg_ppv = sub.spending.avg_ppv_price if sub.spending else 0
        highest = sub.spending.highest_single_purchase if sub.spending else 0
        rejected = sub.spending.rejected_ppv_count if sub.spending else 0
        lines.append(
            f"He has bought {ppv_count} PPV(s). Avg price: ${avg_ppv:.2f}. "
            f"Highest single: ${highest:.2f}. Rejected PPVs: {rejected}."
        )

    # Pending PPV
    pending = getattr(sub, "pending_ppv", None)
    if pending:
        try:
            sent_at = datetime.fromisoformat(pending.get("sent_at", "").replace("Z", "+00:00"))
            if sent_at.tzinfo is not None:
                sent_at = sent_at.replace(tzinfo=None)
            mins_ago = int((datetime.now() - sent_at).total_seconds() / 60)
            lines.append(
                f"PENDING PPV: tier {pending.get('tier')}, sent {mins_ago} min ago, not yet paid."
            )
        except Exception:
            lines.append(f"PENDING PPV: tier {pending.get('tier')}, not yet paid.")

    # Goodbye pattern
    patterns = getattr(sub, "goodbye_patterns", []) or []
    if patterns:
        dep_count = len(patterns)
        gaps = [p.get("gap_hours") for p in patterns if p.get("gap_hours") is not None]
        avg_gap = round(sum(gaps) / len(gaps), 1) if gaps else None
        with_ppv = [p for p in patterns if p.get("tier_pending")]
        open_rate = None
        if with_ppv:
            opened = sum(1 for p in with_ppv if p.get("opened_ppv_on_return"))
            open_rate = round(opened / len(with_ppv) * 100)
        summary = f"He has said 'brb/gotta go' {dep_count} time(s)."
        if avg_gap is not None:
            summary += f" Avg gap: {avg_gap}h."
        if open_rate is not None:
            summary += f" He opens pending PPVs on return {open_rate}% of the time."
        lines.append(summary)

    # Custom request streak
    streak = getattr(sub, "custom_request_streak", 0)
    if streak > 0:
        lines.append(f"He has asked for a custom {streak} time(s) consecutively (3+ = allow custom pitch).")

    # Objection / brokey state
    tier_no = getattr(sub, "tier_no_count", 0)
    if tier_no > 0:
        lines.append(f"He has pushed back on price {tier_no} time(s) this session (3+ = GFE kick).")

    return " ".join(lines) if lines else "First interaction — no history yet."


def _format_session_arc(sub: Subscriber) -> str:
    """
    Prose timeline of the current session. When did it start, what's happened.
    """
    recent = sub.recent_messages or []
    if not recent:
        return "Conversation hasn't started yet."

    # First message in history is our approximation of session start
    first = recent[0] if recent else {}
    first_content = first.get("content", "")[:60]
    msg_count = len(recent)

    ppv_count = sub.spending.ppv_count if sub.spending else 0
    total = sub.spending.total_spent if sub.spending else 0

    lines = [
        f"Conversation has {msg_count} message(s) in recent history, starting with fan saying '{first_content}'.",
    ]
    if ppv_count > 0:
        lines.append(f"So far he has bought {ppv_count} tier(s) for ${total:.2f}.")
    else:
        lines.append("No PPVs bought yet in this session.")

    # Crash recovery flag
    if getattr(sub, "last_crash_time", None):
        lines.append("Note: bot went silent at some point and is recovering — apologize naturally if it fits.")

    return " ".join(lines)


def _extract_open_threads(sub: Subscriber) -> list[str]:
    """
    Surface conversational topics the fan opened that the bot hasn't circled back to.
    Heuristic: look at fan messages from 2-10 turns ago that mentioned specific topics,
    check if bot's subsequent messages referenced them.

    Returns a list of short prose descriptions of unclosed threads (max 3).
    """
    messages = sub.recent_messages or []
    if len(messages) < 4:
        return []

    # Look at fan messages from positions -10 to -3 (skip the very latest 2 turns)
    fan_history = [m for m in messages[-10:-2] if m.get("role") in ("sub", "user")]
    if not fan_history:
        return []

    # Recent bot messages for "has she responded to this" check
    recent_bot_text = " ".join(
        m.get("content", "").lower()
        for m in messages[-5:]
        if m.get("role") in ("bot", "assistant")
    )

    # Simple topic markers: words the fan said that might be worth following up on
    topic_keywords = [
        "work", "job", "coding", "tired", "stressed", "busy", "traveling", "home",
        "dog", "cat", "pet", "family", "sister", "brother", "mom", "dad",
        "gym", "workout", "food", "eat", "hungry", "cooking",
        "weekend", "vacation", "trip", "party", "friends",
        "bed", "sleep", "morning", "night",
        "music", "movie", "show", "book", "game",
        "beer", "drink", "coffee", "wine",
    ]

    open_threads = []
    seen_topics = set()

    for msg in fan_history:
        content = msg.get("content", "").lower()
        for kw in topic_keywords:
            if kw in content and kw not in seen_topics and kw not in recent_bot_text:
                # Fan mentioned this topic, bot hasn't touched it in the last 5 bot msgs
                snippet = content[:80].replace("\n", " ")
                open_threads.append(f"He mentioned '{kw}' earlier: '{snippet}...' — you never followed up on this")
                seen_topics.add(kw)
                if len(open_threads) >= 3:
                    return open_threads

    return open_threads


def _format_tier_content_awareness(sub: Subscriber, model_profile) -> str:
    """
    Tell the Director what's ACTUALLY IN each tier so she can sext toward real content,
    not wave vaguely at "proceed with caution."

    Uses TIER_CONFIG from engine/onboarding.py — canonical source.
    """
    try:
        from onboarding import ContentTier, TIER_CONFIG
    except Exception:
        return ""

    tier_order = [
        ContentTier.TIER_1_BODY_TEASE,
        ContentTier.TIER_2_TOP_TEASE,
        ContentTier.TIER_3_TOP_REVEAL,
        ContentTier.TIER_4_BOTTOM_REVEAL,
        ContentTier.TIER_5_FULL_EXPLICIT,
        ContentTier.TIER_6_CLIMAX,
    ]

    ppv_count = sub.spending.ppv_count if sub.spending else 0
    current_tier_idx = min(ppv_count, 5)  # 0-indexed into tier_order

    lines = [f"CURRENT TIER POSITION: {current_tier_idx + 1} of 6 (next drop = tier {min(current_tier_idx + 1, 6)})"]
    lines.append("TIER CONTENT MAP (what's actually in each bundle):")
    for i, tier in enumerate(tier_order):
        cfg = TIER_CONFIG.get(tier, {})
        marker = ">>> CURRENT" if i == current_tier_idx else ""
        lines.append(
            f"  T{i+1} ${cfg.get('price', 0):.2f} — {cfg.get('name', '')}: "
            f"{cfg.get('description', '')} {marker}"
        )
    lines.append(
        "Use this to sext toward the REAL content of the current/next tier — "
        "not generic 'proceed with caution' vibes."
    )
    return "\n".join(lines)


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
