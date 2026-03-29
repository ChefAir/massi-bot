"""
Massi-Bot LLM - PPV Readiness Checker

Lightweight LLM call that decides if a fan is ready for the first PPV drop.
Runs after every message in WARMING/TENSION_BUILD states.
Uses the same OpenRouter/Grok client -- fast, cheap (~$0.001/call).

Decision criteria:
- Has the fan shown sexual interest or desire?
- Has the fan indicated they want to see more?
- Has there been enough rapport built (at least 2-3 exchanges)?
- Is the fan's energy high enough that a PPV would feel natural, not forced?
"""

import os
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_READINESS_MODEL = "x-ai/grok-4.1-fast"  # Same as main generator
_READINESS_TIMEOUT = 8.0  # Must be fast

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    _client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=_READINESS_TIMEOUT,
    )
    return _client


_READINESS_PROMPT = """You are a sales timing expert for an adult content creator's chat. Your ONLY job is to decide: should she drop exclusive content (PPV) RIGHT NOW?

Recent conversation (most recent last):
{conversation}

Current state: {state} (she has been chatting with him for {turn_count} messages)

Decision criteria - answer YES if ANY of these are true:
1. He expressed desire for her ("I want you", "I need you", "you're so hot", "I can't resist")
2. He described sexual scenarios or fantasies about her
3. He explicitly asked for content ("show me", "let me see", "I'm ready")
4. He's been sexually engaged for 2+ messages and the energy is high
5. The conversation has natural momentum toward intimacy

Answer YES if dropping content now would feel natural and exciting (not forced).
Answer NO only if he's still in casual small talk with no sexual energy yet.

Respond with EXACTLY one word: YES or NO"""


async def check_ppv_readiness(
    recent_messages: list[dict],
    state: str,
    turn_count: int,
) -> bool:
    """
    Check if the fan is ready for a PPV drop.

    Args:
        recent_messages: Last 4-6 messages as list of {role, content} dicts
        state: Current engine state ("warming" or "tension_build")
        turn_count: Number of messages exchanged so far

    Returns:
        True if PPV should drop now, False to continue building
    """
    client = _get_client()
    if client is None:
        # No API key -- fall back to engine's default timing
        return False

    # Need at least 2 messages to make a judgement
    if len(recent_messages) < 2:
        return False

    # Format conversation
    conv_lines = []
    for msg in recent_messages[-6:]:
        role_label = "Fan" if msg.get("role") in ("sub", "user") else "Her"
        content = msg.get("content", "")[:150]
        conv_lines.append(f"{role_label}: {content}")
    conversation = "\n".join(conv_lines)

    prompt = _READINESS_PROMPT.format(
        conversation=conversation,
        state=state,
        turn_count=turn_count,
    )

    try:
        completion = await client.chat.completions.create(
            model=_READINESS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=5,
            temperature=0.0,
        )
        answer = completion.choices[0].message.content.strip().upper()
        is_ready = answer.startswith("YES")
        logger.info(
            "PPV readiness check: %s (state=%s, turns=%d)",
            answer, state, turn_count,
        )
        return is_ready
    except Exception as exc:
        logger.warning(
            "PPV readiness check failed: %s -- defaulting to NO",
            str(exc)[:80],
        )
        return False
