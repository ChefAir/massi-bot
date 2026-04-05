"""
Massi-Bot LLM - Conversation Validator (Reasoning Layer)

Uses Claude Opus 4 as a reasoning model to validate Grok's responses
before they're sent to subscribers. Catches:
  - Logical inconsistencies (contradicting previous statements)
  - Tier boundary violations (describing nudity beyond what's been shown)
  - Topic repetition (looping back to same subject)
  - Ignoring what the fan actually said
  - Platform name leaks (OnlyFans, Fanvue, Instagram)
  - Filler phrase usage
  - Premature escalation past content tier

Architecture:
  Grok generates → Claude validates → PASS or FIX instruction → Grok regenerates

Cost: ~$0.01 per validation call ($15/$75 per M tokens)
Latency: 1-3 seconds (invisible within the 10-30s response delay)
"""

import os
import time
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Validator client (Claude via OpenRouter)
# ─────────────────────────────────────────────

_VALIDATOR_MODEL = os.environ.get("LLM_VALIDATOR_MODEL", "anthropic/claude-haiku-4-5-20251001")
_VALIDATOR_TIMEOUT = 10.0  # seconds — must be fast

_validator_client: Optional[AsyncOpenAI] = None


def _get_validator_client() -> Optional[AsyncOpenAI]:
    """Lazy-init the validator client. Uses same OpenRouter API key."""
    global _validator_client
    if _validator_client is not None:
        return _validator_client

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None

    _validator_client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=_VALIDATOR_TIMEOUT,
    )
    return _validator_client


# ─────────────────────────────────────────────
# Tier boundary descriptions for validator
# ─────────────────────────────────────────────

_TIER_DESCRIPTIONS = {
    0: "NOTHING shown yet. She is fully clothed. She must NOT describe removing clothing or nudity. FORBIDDEN words/concepts: nipples, bare chest, topless, panties off, naked, nude, pussy, ass bare, fingering, touching herself.",
    1: "Tier 1 SENT: Clothed body tease (curves through clothing). She can tease about what's underneath but must NOT say she's taking anything off. FORBIDDEN: nipples visible, topless, bare breasts, any nudity below waist, fingering, touching herself.",
    2: "Tier 2 SENT: Cleavage/bra peeking out, shirt pulled down. Top is still ON — she must NOT say it's coming off or being removed (that's tier 3). She can reference what's visible (cleavage, bra). FORBIDDEN: top coming off, removing top, nudity below waist, pussy, fingering.",
    3: "Tier 3 SENT: Topless/bare chest shown. She can be explicit about her top half but bottom is still covered. FORBIDDEN: nudity below waist fully visible, fingering explicitly.",
    4: "Tier 4 SENT: Bottoms off. She can describe her full body but she has NOT shown self-play or toys. FORBIDDEN: self-play with toys, climax descriptions.",
    5: "Tier 5 SENT: Full nudity + fingering + playing with tits shown. She can be very explicit about self-touching. But NO toys and NO climax. FORBIDDEN: toys, dildo, vibrator, climax, orgasm, riding toy.",
    6: "Tier 6 SENT: Everything shown — toys, riding, climax, maximum explicitness. Aftercare mode. No restrictions.",
}


# ─────────────────────────────────────────────
# Build validator prompt
# ─────────────────────────────────────────────

def _build_validator_prompt(
    proposed_response: str,
    fan_message: str,
    recent_history: list[dict],
    tier_level: int,
    persona_location: str,
    persona_name: str,
    topics_mentioned: list[str],
) -> str:
    """Build the validation prompt for Claude."""

    tier_desc = _TIER_DESCRIPTIONS.get(tier_level, _TIER_DESCRIPTIONS[0])

    # Format recent conversation for context
    history_lines = []
    for msg in recent_history[-8:]:
        role = "Fan" if msg.get("role") in ("sub", "user") else "Her"
        history_lines.append(f"  {role}: {msg.get('content', '')[:120]}")
    history_block = "\n".join(history_lines) if history_lines else "  (no prior messages)"

    topics_block = ", ".join(topics_mentioned[-5:]) if topics_mentioned else "none yet"

    return f"""You are a conversation quality validator for a content creator chatbot. Your job is to catch logical errors, inconsistencies, and rule violations BEFORE a message is sent to a real subscriber.

CONTEXT:
- Creator name: {persona_name}, based in {persona_location}
- Current content tier: {tier_desc}
- Topics already discussed: {topics_block}

RECENT CONVERSATION:
{history_block}

FAN'S LATEST MESSAGE:
  "{fan_message}"

PROPOSED RESPONSE TO VALIDATE:
  "{proposed_response}"

CHECK ALL OF THESE (reject on ANY failure):
1. ADDRESSES FAN'S MESSAGE: Does the response react to what the fan actually said? If the fan asked a question, does it answer it? If the fan expressed confusion or frustration, does it acknowledge that?
2. TIER BOUNDARY: Does the response describe nudity or actions beyond what's been shown at the current tier? (e.g., saying "panties sliding off" when she's still clothed = FAIL)
3. NO CONTRADICTIONS: Does the response contradict anything said earlier in the conversation? (e.g., claiming to be from a different city, or referencing something that didn't happen) CRITICAL: She lives in {persona_location} — if she claims to be from or in ANY other city, that's an AUTOMATIC FAIL.
4. NO TOPIC LOOPING: Does the response loop back to a topic already discussed (like repeatedly mentioning the same video/photo/outfit)?
5. NO PLATFORM NAMES: Does it mention OnlyFans, Fanvue, Instagram, or any platform by name?
6. NO FILLER PHRASES: Does it use generic filler like "adulting is hard", "the grind", "hustle", "why is business so lonely"?
7. LOGICAL SENSE: Does the response make logical sense in context? Would a real person say this in this situation?
8. NOT ROBOTIC: Does it sound like a real woman talking, not a scripted bot? Watch for: repeating exact phrases, sounding like a sales pitch, or generic responses that could apply to anyone.
9. TIME CONSISTENCY: If the fan mentioned morning/waking up/starting their day, the response must NOT contain sleep references (goodnight, sleep well, dream of me, sweet dreams). If the fan mentioned night/going to bed, the response must NOT contain morning references (good morning, starting the day). Mismatched time-of-day references are an AUTOMATIC FAIL.

Respond with EXACTLY one of:
- "PASS" — if the response passes ALL checks
- "FIX: [specific 1-sentence instruction for what to change]" — if any check fails

Be strict. Real money depends on this being convincing."""


# ─────────────────────────────────────────────
# Main validation function
# ─────────────────────────────────────────────

async def validate_response(
    proposed_response: str,
    fan_message: str,
    recent_history: list[dict],
    tier_level: int = 0,
    persona_location: str = "Miami",
    persona_name: str = "the model",
    topics_mentioned: Optional[list[str]] = None,
) -> tuple[bool, Optional[str]]:
    """
    Validate a proposed LLM response using Claude as a reasoning layer.

    Args:
        proposed_response: The text Grok generated.
        fan_message: What the fan said (to check if response addresses it).
        recent_history: Recent conversation messages [{role, content}].
        tier_level: Current PPV tier (0-6) for content boundary checking.
        persona_location: Where the persona claims to be from.
        persona_name: The persona's name.
        topics_mentioned: List of topics already discussed (for dedup).

    Returns:
        (is_valid, fix_instruction)
        - (True, None) if response passes validation
        - (False, "FIX: ...") if response needs regeneration
    """
    client = _get_validator_client()
    if client is None:
        # No API key — skip validation, pass through
        logger.debug("Validator client not available — skipping validation")
        return True, None

    start = time.monotonic()
    try:
        prompt = _build_validator_prompt(
            proposed_response=proposed_response,
            fan_message=fan_message,
            recent_history=recent_history,
            tier_level=tier_level,
            persona_location=persona_location,
            persona_name=persona_name,
            topics_mentioned=topics_mentioned or [],
        )

        completion = await client.chat.completions.create(
            model=_VALIDATOR_MODEL,
            messages=[
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
            temperature=0.0,  # Deterministic for validation
        )

        result = completion.choices[0].message.content.strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.upper().startswith("PASS"):
            logger.info("Validator PASS (%dms)", elapsed_ms)
            return True, None
        elif result.upper().startswith("FIX"):
            fix_instruction = result[4:].strip().lstrip(":").strip()
            logger.info("Validator FIX (%dms): %s", elapsed_ms, fix_instruction[:100])
            return False, fix_instruction
        else:
            # Unexpected format — treat as pass to avoid blocking
            logger.warning("Validator unexpected response (%dms): %s", elapsed_ms, result[:100])
            return True, None

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Validator error (%dms): %s — skipping validation", elapsed_ms, str(exc)[:100])
        # On error, pass through — don't block the message
        return True, None
