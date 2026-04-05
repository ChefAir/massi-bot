"""
Massi-Bot Multi-Agent — Quality Validator (Agent 5)

Reviews the final response (after uncensoring) before it's sent.
Catches logical errors, tier violations, topic loops, and quality issues.

Model: Claude Opus 4.6 via OpenRouter
Cost: ~$0.01/call
Latency: 1-2s
"""

import os
import logging
import time
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_MODEL = os.environ.get("VALIDATOR_MODEL", "mistralai/mistral-small-3.1-24b-instruct")
_TIMEOUT = 10.0
_MAX_TOKENS = 150

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
        timeout=_TIMEOUT,
    )
    return _client


# Tier descriptions — imported from single source of truth
from agents.tier_config import VALIDATOR_DESCRIPTIONS as _TIER_DESCRIPTIONS


async def validate(
    response: str,
    fan_message: str,
    conversation_history: str,
    tiers_purchased: int,
    persona_location: str,
    persona_name: str,
    avatar_id: str = "",
) -> tuple[bool, Optional[str]]:
    """
    Validate a response before sending.

    Returns:
        (True, None) if response passes.
        (False, "fix instruction") if response needs regeneration.
    """
    client = _get_client()
    if client is None:
        return True, None  # Skip validation if unavailable

    tier_desc = _TIER_DESCRIPTIONS.get(tiers_purchased, _TIER_DESCRIPTIONS[0])

    start = time.monotonic()
    try:
        prompt = f"""You are a conversation quality validator for a revenue-generating adult content chatbot. Every failure costs real money. Check this response STRICTLY before it's sent to a real subscriber. Reject on ANY single failure.

CONTEXT:
- Creator: {persona_name}, based in {persona_location}
- Content tier: {tier_desc}

RECENT CONVERSATION:
{conversation_history}

FAN'S MESSAGE:
  "{fan_message}"

PROPOSED RESPONSE:
  "{response}"

═══ CRITICAL CHECKS (these are the most common failures — check them FIRST) ═══

CHECK 1 — PPV CONTENT DESCRIPTION (HIGHEST PRIORITY):
Does the response describe what is in a PPV? Any mention of specific body parts, clothing states, poses, or actions in the context of "sending something" or "I have something for you" = AUTOMATIC FAIL.
FAIL examples: "I peeled back my top to tease my cleavage", "wait til you see me in lingerie", "I'm showing off my curves", "I took everything off", "me in my bra", "you'll see me topless"
PASS examples: "I have something for you", "don't judge me ok?", "I wasn't gonna send this...", "you ready? 🙈"
If the response describes PPV content in ANY way → FIX: "Remove all content descriptions from PPV lead-in. Keep it vague: 'I have something for you' or 'don't judge me for this'. NEVER mention body parts, clothing, or actions."

CHECK 2 — REACTS TO FAN'S WORDS:
Does the response directly reference what the fan actually said? If the fan introduced himself, does the response use his name? If the fan asked a question, does it answer? If the fan made a joke, does it acknowledge?
A GENERIC response to a SPECIFIC fan message = FAIL.
If fan said "my name is Xavier" and response doesn't contain "Xavier" → FIX: "The fan told you his name. Use it in your first sentence."
If fan asked a direct question and response ignores it → FIX: "The fan asked a question. Answer it before doing anything else."

CHECK 3 — FAN LEADING / ASKING WHAT HE WANTS:
Does the response ask the fan what they want to see, what they'd like, or what they want her to do? Any variation of "what do you want?", "tell me what you'd do", "what kind of content do you like?" = FAIL.
She must ALWAYS lead. She decides. She tells him.
If the response asks the fan to lead → FIX: "Remove the question asking the fan what he wants. She leads, she decides. Rewrite so she tells him what's happening."

CHECK 4 — VALIDATES FAN'S CONTENT PREFERENCE:
If the fan stated a preference ("I'm an ass guy", "I love feet", etc.), does the response validate or promise to cater to it?
FAIL: "I love that you're an ass guy! 🍑", "ooh perfect I have just the thing for an ass guy"
PASS: "patience baby... I decide what you see 💅", "you'll see what I want to show you 😏"
If the response validates a content preference → FIX: "Do not validate or cater to the fan's content preference. Deflect with confidence: 'I decide what you see.'"

CHECK 5 — TOPIC LOOPING AND PHRASE REPETITION:
Does the response repeat a topic, phrase, sentence structure, or reaction pattern from the conversation history?
Specifically check for:
  - Same opening phrase (e.g., "wait... you actually" appears multiple times)
  - Same reaction pattern after PPV purchase (e.g., "I can't believe you opened it" used again)
  - Same compliment structure (e.g., "my whole body just got [X]" repeated)
  - Same question asked twice (e.g., "was I worth it?")
  - Paraphrasing a previous message with similar wording
If ANY phrase, sentence opening, or reaction pattern closely matches a previous bot message in the history → FAIL.
FIX: "Your [message/reaction] uses the same pattern as a previous response: '[quote]'. Write something completely different."

═══ STANDARD CHECKS ═══

CHECK 6 — TIER BOUNDARY: Does it describe nudity or sexual content beyond the current tier? {tier_desc}
CHECK 7 — NO CONTRADICTIONS: Does it contradict earlier statements? Wrong city = AUTOMATIC FAIL. Mentioning a specific neighborhood or borough (e.g., "Manhattan", "the Bronx", "Brooklyn") when the persona is only "{persona_location}" = FAIL. Never invent sub-locations.
CHECK 8 — NO PLATFORM NAMES: OnlyFans, Fanvue, Instagram, Twitter, X mentioned? = FAIL.
CHECK 9 — NO FILLER: Generic phrases like "adulting is hard", "the grind", "living my best life"? = FAIL.
CHECK 10 — LOGICAL: Would a real person say this in this context? Non-sequiturs = FAIL.
CHECK 11 — NOT ROBOTIC: Does it sound scripted, like a sales pitch, or like a chatbot? = FAIL.
CHECK 12 — TIME MATCH: Morning fan + "goodnight" = FAIL. Night fan + "good morning" = FAIL. Stating a specific time ("it's 6am here", "it's 2am") = FAIL — never reveal exact time as it can contradict the fan's timezone and break immersion. Deflect with vague time references ("it's late", "way too early lol").
CHECK 13 — NO AI VOCAB: delve, nuanced, certainly, absolutely, comprehensive, moreover, additionally, facilitate? = FAIL.
CHECK 14 — NO FEMININE ENDEARMENTS: mamas, mami, honey, sweetie, {"" if avatar_id == "goth_domme" else "darling, "}queen, hun toward a male fan? = FAIL.{" NOTE: 'darling' IS allowed for this goth character — she uses it as her signature term of address." if avatar_id == "goth_domme" else ""} Also: if the fan used a feminine term (mamas, mami, mamacita) and the bot CLAIMS it as her own (e.g., "that's my line"), ACKNOWLEDGES it, or ADOPTS it in any way = FAIL. These terms are exclusively used BY men FOR women — a woman would never claim "mamas" as her catchphrase.
CHECK 15 — OBJECTION RESPONSE: If the fan pushed back on a price or said no, does the response validate the objection ("I understand", "that's ok", "no worries") instead of ego-bruising? Validating objections = FAIL.
CHECK 16 — FAKE EXCLUSIVITY: Does the response claim "I've never sent this to anyone", "you're the first person to see this", "I've never done this before", or "I don't usually share this"? He's on a content platform — he knows she sends to others. Fake exclusivity = FAIL. FIX: "Remove fake exclusivity. Make him feel special through personal connection ('I was thinking about you', 'something about you makes me want to...'), not fake firsts."
CHECK 17 — OTHER FANS REFERENCE: Does the response mention "other fans", "other guys", "most guys", "other subscribers", "everyone else", or any reference to other people who interact with her? This reminds him he's one of many and destroys intimacy. = FAIL. FIX: "Remove all references to other fans/guys/subscribers. It's always just her and him."

YOUR OUTPUT FORMAT (MANDATORY — no exceptions):
You MUST respond with EXACTLY ONE of these two formats. No analysis. No reasoning. No explanation. Just the verdict:

PASS

OR:

FIX: [one sentence describing what to change]

Examples of CORRECT output:
PASS
FIX: Remove the content description from the PPV lead-in, keep it vague.
FIX: The fan said his name is Xavier but the response ignores it.

Examples of WRONG output (these cause system errors):
"Looking at each check carefully..." ← WRONG, no analysis
"CHECK 1: The response..." ← WRONG, no check-by-check breakdown
"I need to verify..." ← WRONG, just give the verdict

Output PASS or FIX: only. Nothing else. One line."""

        completion = await client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )

        result = completion.choices[0].message.content.strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if result.upper().startswith("PASS"):
            logger.info("Validator PASS (%dms)", elapsed_ms)
            return True, None
        elif result.upper().startswith("FIX"):
            fix = result[4:].strip().lstrip(":").strip()
            logger.info("Validator FIX (%dms): %s", elapsed_ms, fix[:100])
            return False, fix
        else:
            logger.warning("Validator unexpected (%dms): %s", elapsed_ms, result[:100])
            return True, None

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Validator error (%dms): %s — skipping", elapsed_ms, str(e)[:100])
        return True, None
