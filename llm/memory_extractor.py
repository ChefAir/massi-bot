"""
Massi-Bot LLM - Memory Extractor (U6 + U9 LLM upgrade)

Two extraction modes:
  1. LLM-based (primary): Sends the fan message + recent context to Haiku
     for full-sentence extraction with temporal intent. Preserves context
     like "wants to move to Medellin" vs stripping it to "from/in medellin".
  2. Regex-based (fallback): Pattern matching for when LLM is unavailable.

Extracted categories:
  - job/occupation     ("I'm a nurse", "I work in tech", "I run my own business")
  - location           ("I'm from Texas", "I live in NYC", "just moved to LA")
  - relationship       ("I'm going through a divorce", "single for a year", "she left")
  - emotional state    ("I've been really stressed", "today was rough", "I'm lonely")
  - hobbies/interests  ("I love fishing", "I go to the gym", "I play poker")
  - life events        ("my dog died", "I got promoted", "just got back from Vegas")
  - plans/goals        ("wants to move to Colombia", "saving up for a house")

Called by memory_manager after every message to build a personalized memory bank.
"""

import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# LLM-based extraction (primary)
# ─────────────────────────────────────────────

_LLM_EXTRACTION_PROMPT = """Extract personal facts from this fan message. Return ONLY facts the fan revealed about THEMSELVES.

CRITICAL RULES:
1. Preserve temporal context EXACTLY. If they say "want to move to X", write "Wants to move to X" — NOT "Lives in X".
2. Distinguish: currently lives in, used to live in, wants to move to, is visiting, is from originally.
3. Include the FULL context — "Wants to move to Medellin, Colombia in about a year" NOT just "Medellin".
4. Each fact must be a complete sentence that stands alone without the original message.
5. If the message contains NO personal facts (just greetings, questions, reactions), return an empty array.
6. Max 3 facts per message. Only genuinely personal disclosures.

Return JSON only:
{"facts": [{"fact": "full sentence", "category": "location|job|relationship|emotion|hobby|event|plan|preference", "temporal": "past|present|future|habitual"}]}

Examples:
- "I'm from the Bronx but I want to move to Medellin next year" →
  {"facts": [{"fact": "Originally from the Bronx, New York", "category": "location", "temporal": "present"}, {"fact": "Wants to move to Medellin, Colombia within the next year", "category": "plan", "temporal": "future"}]}
- "I work as a waitress at a restaurant in the Bronx" →
  {"facts": [{"fact": "Works as a waitress at a restaurant in the Bronx", "category": "job", "temporal": "present"}]}
- "haha yeah that's crazy" →
  {"facts": []}
- "I just made a million on crypto and I'm leaving next year" →
  {"facts": [{"fact": "Recently made a million dollars from cryptocurrency", "category": "event", "temporal": "past"}, {"fact": "Plans to leave within the next year", "category": "plan", "temporal": "future"}]}"""


async def extract_facts_llm(
    message: str,
    recent_context: list[str] = None,
) -> list[dict]:
    """
    Extract personal facts using an LLM (Haiku for cost efficiency).

    Returns list of dicts: [{"fact": str, "category": str, "temporal": str}]
    Returns empty list if LLM unavailable or no facts found.
    """
    if not message or len(message) < 8:
        return []

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return []

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=10.0,
        )

        user_content = f"Fan message: \"{message}\""
        if recent_context:
            context_block = "\n".join(f"- {m}" for m in recent_context[-5:])
            user_content = f"Recent conversation context:\n{context_block}\n\n{user_content}"

        completion = await client.chat.completions.create(
            model="anthropic/claude-haiku-4-5-20251001",
            messages=[
                {"role": "system", "content": _LLM_EXTRACTION_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=300,
            temperature=0.0,
        )

        raw = completion.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        facts = result.get("facts", [])

        # Validate structure
        validated = []
        for f in facts:
            if isinstance(f, dict) and f.get("fact") and len(f["fact"]) > 5:
                validated.append({
                    "fact": f["fact"],
                    "category": f.get("category", "general"),
                    "temporal": f.get("temporal", "present"),
                })

        if validated:
            logger.info("LLM extracted %d facts: %s",
                        len(validated), [f["fact"][:50] for f in validated])
        return validated

    except Exception as e:
        logger.warning("LLM fact extraction failed: %s — falling back to regex", str(e)[:80])
        return []

# ─────────────────────────────────────────────
# Pattern definitions
# ─────────────────────────────────────────────

_PATTERNS: list[tuple[str, str, list[str]]] = [
    # (category, description_template, regex_patterns)

    # Occupation
    ("job", "works as {match}", [
        r"i(?:'m| am) (?:a |an )?(\w+ (?:nurse|doctor|engineer|lawyer|teacher|manager|"
        r"driver|chef|developer|designer|cop|firefighter|soldier|pilot|mechanic|accountant|"
        r"professor|therapist|dentist|vet|pharmacist|plumber|electrician|realtor|broker))",
        r"i work (?:as |in |at )(?!out\b|up\b|hard\b|late\b|on\b|it\b)([^,\.!?]{4,40})",
        r"i run (?:my own )?([^,\.!?]{4,40}business[^,\.!?]{0,20})",
        r"i own (?:a |an )?(?!dog\b|cat\b|car\b|house\b|place\b)([^,\.!?]{4,40})",
        r"my job is ([^,\.!?]{4,40})",
        r"i(?:'m| am) self.employed (?:as |doing )?([^,\.!?]{0,30})",
    ]),

    # Location
    ("location", "from/in {match}", [
        r"i(?:'m| am) from ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"i live in ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"i(?:'m| am) in ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"just moved to ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"based in ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"here in ([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
    ]),

    # Relationship status
    ("relationship", "relationship: {match}", [
        r"(going through (?:a )?divorce)",
        r"(just got (?:out of|dumped|divorced|separated))",
        r"(single for \w+ (?:month|year|week))",
        r"(she left|he left|my ex)",
        r"(broken up|broke up|breakup)",
        r"(haven't dated in \w+)",
        r"(married but|in a relationship but|my wife)",
        r"(widowed|widow|lost my (?:wife|husband|partner))",
    ]),

    # Emotional state / stressors
    ("emotion", "feeling: {match}", [
        r"i(?:'ve| have) been (?:really |so |pretty )?(stressed|lonely|depressed|anxious|"
        r"exhausted|burned out|overwhelmed|struggling|going through it)",
        r"(today was (?:really |so |pretty )?(?:rough|hard|bad|tough|terrible|awful|long))",
        r"(i(?:'m| am) (?:really |so )?(?:stressed|lonely|exhausted|bored|lost|stuck|sad))",
        r"(nobody (?:gets|understands) me)",
        r"(feel like i(?:'m| am) (?:alone|invisible|not enough))",
    ]),

    # Hobbies and interests
    ("hobby", "into {match}", [
        r"i(?:\s+really)? love (\w+ing|\w+ \w+ing|(?:fishing|gaming|cooking|hiking|"
        r"hunting|surfing|climbing|cycling|running|golfing|boxing|wrestling|reading|"
        r"painting|drawing|photography|woodworking|gardening))",
        r"i(?:'m| am) (?:really )?into (?!you\b|it\b|that\b|this\b|her\b|him\b)([^,\.!?]{4,35})",
        r"i play ([^,\.!?]{3,30}(?:poker|golf|guitar|piano|drums|sports|ball|chess))",
        r"i go to (?:the )?gym",
        r"i watch (?!out\b|it\b)([^,\.!?]{3,30})",
        r"my hobby is ([^,\.!?]{4,40})",
    ]),

    # Life events
    ("event", "{match}", [
        r"(just got (?:a )?(?:promoted|raise|new job|fired|laid off))",
        r"(just (?:bought|got|closed on) (?:a |my )?(?:house|car|truck|boat|place))",
        r"(just (?:had|got) (?:a )?(?:baby|kid|son|daughter|puppy|dog))",
        r"(my (?:dog|cat|mom|dad|grandma|grandpa|friend) (?:died|passed))",
        r"(just (?:got back from|went to|was in) [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)",
        r"(celebrating|just had) (?:my )?(?:birthday|anniversary)",
        r"(going through (?:a )?(?:tough|hard|rough) (?:time|patch|period))",
    ]),
]


# ─────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────

def extract_facts(message: str) -> list[str]:
    """
    Extract personal disclosures from a fan message.

    Returns a list of formatted fact strings, e.g.:
      ["works as a nurse", "from Texas", "feeling: stressed"]
    Only returns facts that are substantive (>3 chars after stripping).
    """
    if not message or len(message) < 8:
        return []

    facts: list[str] = []

    for category, template, patterns in _PATTERNS:
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                if match.lastindex and match.lastindex >= 1:
                    matched_text = match.group(1).strip().lower()
                else:
                    matched_text = match.group(0).strip().lower()

                # Filter out trivially short matches
                if len(matched_text) < 4:
                    continue

                # Format the fact using the template
                fact = template.replace("{match}", matched_text)
                facts.append(fact)
                break  # One match per category per message

    return facts


def update_callback_references(sub, message: str) -> int:
    """
    Extract facts from the fan's message and add them to sub.callback_references.
    Deduplicates against existing references to avoid bloat.

    Returns number of new facts added.
    """
    new_facts = extract_facts(message)
    if not new_facts:
        return 0

    existing_lower = {r.lower() for r in sub.callback_references}
    added = 0

    for fact in new_facts:
        if fact.lower() not in existing_lower:
            sub.callback_references.append(fact)
            existing_lower.add(fact.lower())
            added += 1
            logger.debug("Memory extracted for sub %s: %s", sub.sub_id, fact)

    # Keep the list from growing unbounded (keep most recent 30)
    if len(sub.callback_references) > 30:
        sub.callback_references = sub.callback_references[-30:]

    return added


# ─────────────────────────────────────────────
# Persona self-identity extraction (U8 extension)
# Extracts facts from what the BOT said about herself
# ─────────────────────────────────────────────

_SELF_PATTERNS: list[tuple[str, str, list[str]]] = [
    ("daily_life", "{match}", [
        r"i (?:just|literally) (went to|came from|got back from|finished) (.+?)(?:\.|!|$)",
        r"i(?:'m| am) (?:currently|about to|going to) (.+?)(?:\.|!|$)",
    ]),
    ("hobby", "enjoys {match}", [
        r"i (?:love|really like|enjoy|am obsessed with|can't stop) (.+?)(?:\.|!|$)",
    ]),
    ("opinion", "thinks {match}", [
        r"i (?:think|feel like|believe|always say) (.+?)(?:\.|!|$)",
    ]),
    ("food", "food: {match}", [
        r"i (?:just (?:ate|had|made|cooked)|love eating|can't resist) (.+?)(?:\.|!|$)",
    ]),
]


def extract_persona_facts(bot_message: str) -> list[tuple[str, str]]:
    """Extract self-referential facts from bot's own message.
    Returns list of (category, fact) tuples."""
    if not bot_message or len(bot_message) < 10:
        return []

    facts = []
    for category, fmt, patterns in _SELF_PATTERNS:
        for pat in patterns:
            match = re.search(pat, bot_message, re.IGNORECASE)
            if match:
                detail = match.group(match.lastindex or 1).strip()
                if len(detail) > 3 and len(detail) < 80:
                    fact = fmt.replace("{match}", detail)
                    facts.append((category, fact))
                break  # One match per category
    return facts
