"""
Massi-Bot — High-Value Utterance Registry

Per-subscriber persistent log of bot messages at inflection points where
verbatim repetition = biggest bot tell. Unlike the sliding `recent_messages`
window, these entries persist across the entire subscriber relationship.

Categories are the decision points where the bot's exact wording matters most.
Each category has a hard cap of 30 entries; older entries are FIFO-evicted to
the archive (hash + timestamp only, no raw text) for future A/B analysis.

Usage in an agent:
    from engine.high_value_memory import (
        HVCategory, format_anti_repeat_block, append_utterance
    )

    # Before generating: inject anti-repeat context
    block = format_anti_repeat_block(sub, HVCategory.MONEY_READINESS_ASK)
    system_prompt += block

    # After generating: append the new message
    append_utterance(sub, HVCategory.MONEY_READINESS_ASK, generated_text)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from models import Subscriber

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Categories — all 9 active from day 1
# ─────────────────────────────────────────────

class HVCategory(str, Enum):
    """
    Categories of high-value bot utterances worth tracking verbatim.

    Each category represents an inflection point where a repeated phrasing
    would sound robotic to a human re-reading old messages.
    """
    # GFE-phase decision points
    MONEY_READINESS_ASK = "money_readiness_ask"           # "are you ready to spend money on me?"
    CONSENT_ASK_VULNERABILITY = "consent_ask_vulnerability"  # "I want to show you a side..."
    CONSENT_DECLINE_PIVOT = "consent_decline_pivot"       # "totally fair babe, no worries"
    FIRST_MESSAGE_WELCOME = "first_message_welcome"       # Opening line of a session
    RAPPORT_CHECK_IN = "rapport_check_in"                 # "tell me about yourself"
    FLIRTY_COMPLIMENT_OPENER = "flirty_compliment_opener" # First flirty opener
    CONTINUATION_PITCH = "continuation_pitch"             # $20 paywall message

    # Selling-phase decision points
    PPV_HEADS_UP = "ppv_heads_up"                         # "give me a couple minutes"
    PPV_POST_PURCHASE_REACTION = "ppv_post_purchase_reaction"  # "omg your reaction"
    SEXUAL_ESCALATION_BRIDGE = "sexual_escalation_bridge" # Tier-to-tier heat bridge
    OUTFIT_CONTINUITY_DEFENSE = "outfit_continuity_defense"  # "I put it back on for you"
    CUSTOM_PITCH = "custom_pitch"                         # Custom pricing + framing
    CUSTOM_REFUSE_TALKING = "custom_refuse_talking"       # "I don't vibe with talking"
    GOODBYE_RESPONSE = "goodbye_response"                 # Fan says "gotta go" — varied farewells
    RETURN_ACKNOWLEDGMENT = "return_acknowledgment"       # "welcome back" — varied greetings after gap
    SCENE_LEADERSHIP = "scene_leadership"                 # Edge-control + dominant commands. Repetition kills heat.
    CUSTOM_PAYMENT_RECEIVED = "custom_payment_received"   # "got it baby, I see your payment" variants
    CUSTOM_PAYMENT_DENIED = "custom_payment_denied"       # "hmm I don't see it come through" variants


# Hard cap per category. FIFO eviction after this.
MAX_ENTRIES_PER_CATEGORY = 30


# ─────────────────────────────────────────────
# Core helpers
# ─────────────────────────────────────────────

def _hash_utterance(text: str) -> str:
    """SHA-256 hash for archive entries (no raw text retained)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_utterances(sub: "Subscriber", category: HVCategory) -> list[str]:
    """Return the full list of active utterances for a category (may be empty)."""
    if not hasattr(sub, "high_value_utterances") or sub.high_value_utterances is None:
        sub.high_value_utterances = {}
    return sub.high_value_utterances.get(category.value, [])


def append_utterance(
    sub: "Subscriber",
    category: HVCategory,
    text: str,
) -> None:
    """
    Append a new utterance to the category. Triggers FIFO eviction to archive
    if the category has reached MAX_ENTRIES_PER_CATEGORY.

    Safe to call repeatedly with the same text — dedups silently.
    """
    if not text or not text.strip():
        return

    text = text.strip()

    # Ensure dicts exist
    if not hasattr(sub, "high_value_utterances") or sub.high_value_utterances is None:
        sub.high_value_utterances = {}
    if not hasattr(sub, "high_value_utterances_archive") or sub.high_value_utterances_archive is None:
        sub.high_value_utterances_archive = {}

    current = sub.high_value_utterances.setdefault(category.value, [])

    # Dedup — don't re-append the exact same string
    if text in current:
        return

    current.append(text)

    # FIFO eviction into archive
    while len(current) > MAX_ENTRIES_PER_CATEGORY:
        evicted = current.pop(0)
        archive_bucket = sub.high_value_utterances_archive.setdefault(category.value, [])
        archive_bucket.append({
            "hash": _hash_utterance(evicted),
            "ts": datetime.now().isoformat(),
        })

    logger.debug(
        "HV registry: appended to %s (size=%d) for sub %s",
        category.value, len(current), getattr(sub, "sub_id", "?")[:8],
    )


def format_anti_repeat_block(
    sub: "Subscriber",
    category: HVCategory,
    max_lines: int = 30,
) -> str:
    """
    Format the anti-repeat prompt block for a category.

    Returns an empty string if no prior utterances exist for this category
    (first-time generation — no anti-repeat needed).
    """
    utterances = get_utterances(sub, category)
    if not utterances:
        return ""

    # Show most recent first (fresher memories are more salient for anti-repeat)
    recent = list(reversed(utterances))[:max_lines]
    bullet_list = "\n".join(f'  - "{u}"' for u in recent)

    return f"""

# HIGH-VALUE ANTI-REPEAT — {category.value}
# Every message you've previously sent this fan in this category.
# NEVER echo any of these. Use completely different structure, metaphor, emoji pattern.
# This is a critical inflection point — repetition = biggest bot tell.
{bullet_list}"""


def format_anti_repeat_block_multi(
    sub: "Subscriber",
    categories: list[HVCategory],
    max_lines_per_category: int = 20,
) -> str:
    """Format anti-repeat blocks for multiple categories at once."""
    blocks = []
    for cat in categories:
        block = format_anti_repeat_block(sub, cat, max_lines=max_lines_per_category)
        if block:
            blocks.append(block)
    return "".join(blocks)


def classify_phase_to_categories(phase: str, buy_signal_active: bool = False) -> list[HVCategory]:
    """
    Map a GFE/selling phase string to the HV categories relevant for that phase.
    Agents use this to inject only the categories that matter for their current decision.
    """
    if phase == "consent_ask" or (phase == "consent_ready" and buy_signal_active):
        return [HVCategory.MONEY_READINESS_ASK, HVCategory.CONSENT_ASK_VULNERABILITY]
    if phase == "consent_ready":
        return [HVCategory.CONSENT_ASK_VULNERABILITY]
    if phase == "continuation_pitch":
        return [HVCategory.CONTINUATION_PITCH]
    # GFE building
    return [
        HVCategory.RAPPORT_CHECK_IN,
        HVCategory.FLIRTY_COMPLIMENT_OPENER,
        HVCategory.FIRST_MESSAGE_WELCOME,
    ]


def reset_after_decline(sub: "Subscriber") -> None:
    """
    Called when a fan explicitly declines to spend money during consent.
    Resets counters so the continuation paywall doesn't hit them mid-rapport-rebuild.

    Does NOT reset the HV utterance registry itself — that's a relationship history,
    not a counter.
    """
    sub.gfe_message_count = 0
    sub.ppv_heads_up_count = 0
    sub.last_consent_decline_at_msg_count = 0
    # Continuation tracking: we don't have a dedicated counter, but gfe_message_count
    # IS the continuation trigger (paywall fires at ~30 GFE messages in current system)
    logger.info(
        "HV: reset_after_decline for sub %s — GFE counters zeroed",
        getattr(sub, "sub_id", "?")[:8],
    )
