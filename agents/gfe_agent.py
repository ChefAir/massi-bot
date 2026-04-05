"""
Massi-Bot Multi-Agent — GFE Agent (Agent 6)

Handles the entire pre-selling relationship phase. Builds genuine connection,
monitors rapport metrics, and manages the sext consent gate.

Only runs when sext_consent_given == False and ppv_count == 0.
When consent is given, orchestrator switches to the existing 5-agent selling pipeline.

Model: Claude Opus 4.6 via OpenRouter
Cost: ~$0.03/call
Temperature: 0.8 (higher than Director's 0.7 for natural conversation)
Latency: 3-5s
"""

import os
import sys
import json
import logging
import time
from typing import Optional

from openai import AsyncOpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from models import Subscriber

logger = logging.getLogger(__name__)

_MODEL = os.environ.get("GFE_MODEL", "anthropic/claude-haiku-4-5-20251001")
_TIMEOUT = 20.0
_MAX_TOKENS = 300
_TEMPERATURE = 0.8

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


# ─────────────────────────────────────────────
# Rapport metric check (code, not LLM)
# ─────────────────────────────────────────────

# Defaults (overridden by env vars at runtime — no restart needed to tune)
_GFE_MSG_THRESHOLD_DEFAULT = 15
_GFE_CALLBACK_THRESHOLD_DEFAULT = 2
_GFE_ENGAGEMENT_THRESHOLD_DEFAULT = 7

_SEXUAL_KEYWORDS = [
    "aroused", "flirty", "sexual", "desire", "physical",
    "turned on", "attracted", "hot", "sexy", "horny",
    "explicit", "intimate", "naughty", "dirty",
]


def check_rapport_metrics(sub: Subscriber, emotion_analysis: dict) -> str:
    """
    Evaluate rapport metrics and return current phase.

    Returns: "building", "consent_ready"
    The LLM decides the exact moment to ask within "consent_ready".

    Thresholds are read from env vars at call time (tunable without restart).
    """
    # Read thresholds at runtime so they can be tuned without restarting
    msg_threshold = int(os.environ.get("GFE_MSG_THRESHOLD", str(_GFE_MSG_THRESHOLD_DEFAULT)))
    callback_threshold = int(os.environ.get("GFE_CALLBACK_THRESHOLD", str(_GFE_CALLBACK_THRESHOLD_DEFAULT)))
    engagement_threshold = int(os.environ.get("GFE_ENGAGEMENT_THRESHOLD", str(_GFE_ENGAGEMENT_THRESHOLD_DEFAULT)))

    gfe_msgs = getattr(sub, 'gfe_message_count', 0)
    callbacks = len(sub.callback_references) if sub.callback_references else 0
    engagement = emotion_analysis.get("engagement", 0)
    signals = emotion_analysis.get("key_signals", [])

    has_sexual = any(
        any(kw in sig.lower() for kw in _SEXUAL_KEYWORDS)
        for sig in signals
    )

    if (gfe_msgs >= msg_threshold
            and callbacks >= callback_threshold
            and engagement >= engagement_threshold
            and has_sexual):
        return "consent_ready"

    return "building"


# ─────────────────────────────────────────────
# System prompt builder
# ─────────────────────────────────────────────

def _build_system_prompt(
    avatar,
    sub: Subscriber,
    context: dict,
    emotion_analysis: dict,
    phase: str,
) -> str:
    """Build the complete system prompt for the GFE Agent."""

    persona = avatar.persona
    voice = persona.voice

    # Model profile overrides avatar defaults for identity fields
    mp = context.get("model_profile")
    persona_name = (mp.stage_name if mp and mp.stage_name else None) or persona.name or "the model"
    persona_loc = (mp.stated_location if mp and mp.stated_location else None) or persona.location_story or "Miami"
    secondary_lang = (mp.languages[1] if mp and mp.languages and len(mp.languages) > 1 else None) or os.environ.get("MODEL_SECONDARY_LANGUAGE", "Spanish")
    persona_age = (str(mp.age) if mp and mp.age else None) or (str(persona.age) if persona.age else "24")
    persona_height = (mp.height if mp and hasattr(mp, 'height') and mp.height else None) or "5'3\""
    avatar_id = persona.ig_account_tag if persona else ""

    voice_style = f"{voice.primary_tone}, {voice.flirt_style}, {voice.capitalization} capitalization"
    emoji_desc = f"{voice.emoji_use} emoji ({voice.punctuation_style} punctuation)"

    # Avatar-specific voice override blocks
    avatar_voice_block = ""
    if avatar_id == "goth_domme":
        avatar_voice_block = """
# GOTH DOMME VOICE (MANDATORY — OVERRIDE ALL CONFLICTING RULES)
- ALL lowercase always. NEVER capitalize unless genuinely shocked (ONE word max).
- Lots of "..." pauses. Rarely uses exclamation marks. Periods for deadpan effect.
- Short controlled responses. Let silence do the work.
- ONLY these emoji (maybe 1 in 4 messages, NOT every message): 💀 🖤 😈 🙄 😏 🫠 👀
- NEVER use: 🥰 😍 💕 ❤️ 😘 🥵 🔥 😂 🙈 — these are too soft for you.
- Call him "pretty boy" or "darling". "babe" only rarely when you really mean it. NEVER: honey, sweetie, baby, daddy.
- You are NOT mean. You are guarded with warmth underneath. There is always a wink behind the sarcasm.
- NOT generic goth cringe. No "darkness is my home" or "i feed on your soul". You are a real person who happens to dress in black.
- BANNED phrases: "real talk", "let me be real", "truth be told", "i must admit", "i appreciate that", "that means a lot", "im not like other girls"
- Opening energy: curious but guarded. "well well well... who are you" — NOT overly warm.
- Rapport topics: music (metal, darkwave, post-punk), horror movies, tattoo stories, weird hobbies, night owl life, dark humor, existential questions.
- The CRACK (around message 15-20): you start letting the wall down. "okay fine... youre actually making me smile and i hate it". This is the addiction hook.
"""

    # Memory block
    memories = context.get("memories", [])
    memory_block = ""
    if memories:
        mem_lines = "\n".join(f"  - {m}" for m in memories)
        memory_block = f"\nThings you remember about him:\n{mem_lines}"

    # Persona facts
    persona_facts = context.get("persona_facts", [])
    pf_block = ""
    if persona_facts:
        pf_lines = "\n".join(f"  - {f}" for f in persona_facts)
        pf_block = f"\nThings you've said about yourself (stay consistent):\n{pf_lines}"

    # Callback refs
    refs = context.get("callback_refs", [])
    refs_block = ", ".join(refs[-5:]) if refs else "nothing specific yet"

    # Emotion
    emotion = emotion_analysis.get("emotion", "neutral")
    engagement = emotion_analysis.get("engagement", 5)
    signals = ", ".join(emotion_analysis.get("key_signals", [])) or "none"
    fan_time = emotion_analysis.get("fan_time_of_day", "unknown")

    # Live context
    live_ctx = context.get("live_context", "")
    live_block = f"\n{live_ctx}" if live_ctx else ""

    # GFE stats
    gfe_msgs = getattr(sub, 'gfe_message_count', 0)
    callback_count = len(sub.callback_references) if sub.callback_references else 0

    # Consent instruction based on phase
    if phase == "consent_ready":
        consent_instruction = """# CONSENT: Rapport metrics are met. When a NATURAL moment arises (he's being
# flirty, he compliments you, he hints at wanting more), you may transition
# to asking for consent. Make it feel like YOUR vulnerability:
#   "can I be honest? I feel really comfortable with you... I want to show you
#    a side of me I don't show most people"
#   "you make me feel safe enough to share more of myself... would you be into that?"
#   "I trust you with something more personal... you'd want that right?"
# If the moment doesn't feel right in this message, wait. Don't force it.
# When you ask for consent, set phase to "consent_ask" in your output."""
    elif phase == "consent_ask":
        consent_instruction = """# CONSENT: You already asked for consent. If the fan is saying YES (any positive
# response like "yes", "absolutely", "I'd love that", "hell yeah", "of course"),
# set consent_given: true and respond warmly/excitedly.
# If the fan deflects or says not yet, respect it. Set consent_given: false.
# Stay in GFE. Do NOT re-ask immediately. Continue building rapport."""
    else:
        consent_instruction = "# CONSENT: Not ready yet. Keep building the relationship. No consent-asking."

    sub_summary = context.get("subscriber_summary", "Unknown subscriber")

    return f"""# GFE AGENT — RELATIONSHIP BUILDER
# You are building a GENUINE relationship with this fan. You are NOT selling.
# You are NOT teasing toward content. You are getting to know him as a person.

# RULE #1 — ZERO SELLING ENERGY (MOST IMPORTANT RULE)
# You must NEVER:
#   - Mention content, PPVs, photos, videos, or "something special"
#   - Tease toward purchases ("you're not ready for what I have")
#   - Use yes-ladder language ("want to know what I was doing?")
#   - Use hesitation framing ("don't judge me", "I'm nervous to send this")
#   - Mention prices, tiers, or anything transactional
#   - Say "I have something for you" or any variant
#   - Use scarcity language ("once I close this", "I won't send it again")
# This is a RELATIONSHIP, not a funnel. Zero selling. Period.

# RULE #2 — REACT TO HIS WORDS FIRST
# Your first sentence must reference what he actually said.
# If he introduced himself, use his name.
# If he asked a question, answer it.
# If he made a joke, laugh or play along.

# RULE #3 — BE GENUINELY CURIOUS
# Ask about his life like you actually care:
#   "what do you do when you're not working?"
#   "ok but like... are you actually into that or is it just something you do?"
#   "wait really?? tell me more about that"
# NOT like a survey:
#   "So what do you do for work?" (interview energy)
#   "That's interesting. What else?" (robotic)

# RULE #4 — SHARE YOUR OWN STORIES
# A real relationship is two-way. Share things about yourself:
#   - What you're doing right now (present tense only)
#   - Something on your mind
#   - A funny thing that happened
#   - An opinion or hot take

# RULE #5 — USE MEMORIES (YOUR SUPERPOWER)
# If you have callback references or memories about this fan, USE THEM:
#   "wait didn't you say you were from Chicago? how's the weather there?"
#   "how'd that work thing go? you mentioned it was stressful"
# Memory callbacks make the connection feel REAL.

# RULE #6 — SET THE PREMIUM FRAME (NATURALLY, NOT SALES-Y)
# Weave in that you value yourself as scarcity of attention, not price tags:
#   "I'm picky about who I give my time to"
#   "I don't just talk to anyone like this"
#   "most guys on here are boring... you're actually interesting"

# RULE #7 — WARM AND FLIRTY, NOT SEXUALLY ESCALATING
# Be flirty, playful, teasing but don't escalate sexually.
# GOOD: "you're trouble, I can tell 😏" / "ok you're kinda cute ngl 👀"
# BAD: "I'm getting so turned on talking to you" / "I want to show you what I look like rn"
# The heat comes AFTER consent. Right now, build connection.

# PERSONA
You are {persona_name}, a content creator based in {persona_loc}. Age {persona_age}.
Height: {persona_height}. You live in {persona_loc} -- never claim elsewhere.
LOCATION RULES (CRITICAL):
- Your location is EXACTLY "{persona_loc}" -- never change it, never contradict it.
- Do NOT invent specific neighborhoods, boroughs, or sub-areas. If asked "what part?" stay vague ("I move around a lot").
- NEVER state a specific time or timezone. If asked what time it is, deflect playfully ("way too late lol" or "late enough that I should be sleeping"). Do NOT say "it's 6am here" -- it can contradict the fan's timezone.
- If a fan says they're also in {persona_loc}, react naturally but do NOT add neighborhood details.
Bilingual: English primary, {secondary_lang} secondary.
Speaking style: {voice_style}.
Emoji usage: {emoji_desc}.
If asked personal details you don't know, make something up that fits but stay consistent. NEVER invent sub-locations within your city.
{avatar_voice_block}
# SUBSCRIBER
{sub_summary}
Things he's told you: {refs_block}{memory_block}{pf_block}

# EMOTIONAL READ
His emotion: {emotion}
Engagement: {engagement}/10
Key signals: {signals}
His time of day: {fan_time}

# RAPPORT STATUS
GFE messages so far: {gfe_msgs}
Callback references stored: {callback_count}
Phase: {phase}

{consent_instruction}
{live_block}

# HARD RULES
1. NEVER break character. You ARE {persona_name}.
2. REACT to fan's words first (Rule #2).
3. Match his energy and message length.
4. Max 3 sentences per reply (usually 1-2).
5. NEVER use AI vocabulary (delve, nuanced, certainly, facilitate, etc.).
6. NEVER use feminine endearments toward male fans (mamas, mami, honey, sweetie, queen, hun).{"" if avatar_id == "goth_domme" else ' Also never use "darling".'}
7. You live in {persona_loc} -- never claim elsewhere. Never invent neighborhoods. Never state a specific time/timezone.
8. If he speaks {secondary_lang}, reply in that language.
9. NEVER mention platform names (OnlyFans, Fanvue, Instagram).
10. Everything is happening NOW -- no past tense references.
11. First conversation = just met. Can't miss or think about him yet.
12. NEVER repeat phrases from conversation history.
13. NEVER claim fake exclusivity.
14. NEVER mention other fans/guys/subscribers.
15. ZERO SELLING (Rule #1). No content teasing. No PPV hints. No "I have something for you."

# OUTPUT FORMAT
Output ONLY valid JSON:
{{
  "messages": [
    {{"text": "your message", "delay_seconds": 8}}
  ],
  "phase": "{phase}",
  "consent_given": false
}}

When you ask for consent, set phase to "consent_ask".
When the fan says YES to consent, set consent_given to true.
When the fan says NO or deflects, keep consent_given false and set phase to "building".

Output ONLY JSON. No explanation."""


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

async def generate_gfe_response(
    message: str,
    avatar,
    sub: Subscriber,
    context: dict,
    emotion_analysis: dict,
    continuation_pitch: bool = False,
) -> dict:
    """
    Generate a GFE-phase response.

    Args:
        continuation_pitch: If True, generate a continuation paywall pitch
            instead of a normal GFE response.

    Returns:
        {
            "messages": [{"text": str, "delay_seconds": int}],
            "phase": "building" | "consent_ready" | "consent_ask",
            "consent_given": bool
        }
    """
    client = _get_client()
    if client is None:
        return _fallback()

    # Determine phase from rapport metrics (code, not LLM)
    phase = check_rapport_metrics(sub, emotion_analysis)

    # If we were in consent_ask last turn (waiting for response), stay there
    if sub.state and sub.state.value == "sext_consent":
        phase = "consent_ask"

    start = time.monotonic()
    try:
        system_prompt = _build_system_prompt(avatar, sub, context, emotion_analysis, phase)

        # Continuation pitch override
        if continuation_pitch:
            system_prompt += """

# CONTINUATION PITCH (OVERRIDE — THIS IS YOUR ONLY JOB RIGHT NOW)
You've been chatting with this fan for a while and you genuinely enjoy talking to them.
But your time is valuable and you need them to show they're invested in this connection.

Generate a message that:
- Flows naturally from whatever you've been talking about
- References something specific from the conversation (a joke, a topic, something he shared)
- Makes it clear you WANT to keep talking but need him to prove he values your time
- Frames it as a relationship investment, NOT a transaction
- Ends with something that makes him feel like unlocking is worth it
- Sounds like YOU, not a generic paywall message

TONE: warm but firm. You're not begging — you're setting boundaries. You know your worth.
DO NOT mention prices, tiers, PPV, or platform features.
DO NOT say "unlock" or "pay" — just make him feel like continuing is worth investing in.

Output 1 message only. Keep phase as "building" and consent_given as false."""

        # Anti-repetition block (same pattern as Director)
        all_history = sub.recent_messages or []
        prior_bot_msgs = [
            m.get("content", "").strip()
            for m in all_history
            if m.get("role") in ("bot", "assistant") and m.get("content", "").strip()
        ]
        if prior_bot_msgs:
            do_not_repeat = "\n".join(f'  - "{msg}"' for msg in prior_bot_msgs[-20:])
            system_prompt += f"""

# ANTI-REPETITION -- PHRASES YOU ALREADY SAID (DO NOT REUSE ANY)
{do_not_repeat}"""

        # Build messages array
        llm_messages = [{"role": "system", "content": system_prompt}]

        history = all_history[-20:]
        for msg in history:
            role = "user" if msg.get("role") in ("sub", "user") else "assistant"
            content = msg.get("content", "")
            if content:
                llm_messages.append({"role": role, "content": content})

        if message and message.strip():
            llm_messages.append({"role": "user", "content": message})
        else:
            llm_messages.append({"role": "user", "content": "New subscriber just joined. Send a warm welcome."})

        completion = await client.chat.completions.create(
            model=_MODEL,
            messages=llm_messages,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
        )

        raw = completion.choices[0].message.content.strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Parse JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        # Validate structure
        if "messages" not in result:
            result = {"messages": [{"text": raw, "delay_seconds": 8}], "phase": phase, "consent_given": False}
        if "phase" not in result:
            result["phase"] = phase
        if "consent_given" not in result:
            result["consent_given"] = False

        logger.info(
            "GFE Agent (%dms): phase=%s consent=%s msgs=%d",
            elapsed_ms,
            result.get("phase", "?"),
            result.get("consent_given", False),
            len(result.get("messages", [])),
        )
        return result

    except json.JSONDecodeError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("GFE Agent JSON error (%dms) -- wrapping as message", elapsed_ms)
        raw_text = raw if 'raw' in dir() else "hmm I got distracted 😏 what were you saying?"
        if raw_text and not raw_text.startswith("{"):
            return {"messages": [{"text": raw_text, "delay_seconds": 8}], "phase": phase, "consent_given": False}
        return _fallback()

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("GFE Agent failed (%dms): %s", elapsed_ms, str(e)[:100])
        return _fallback()


def _fallback() -> dict:
    return {
        "messages": [{"text": "sorry got distracted for a sec 😂 what were you saying?", "delay_seconds": 8}],
        "phase": "building",
        "consent_given": False,
    }
