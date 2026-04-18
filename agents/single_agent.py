"""
Massi-Bot — Single Conversational Agent

One Opus 4.7 call per fan message. Rich system prompt with full context.
Calls specialized tools WHEN IT DECIDES TO — not forced through a pipeline.

Architecture matches every successful conversational AI at scale:
Character.AI, Replika, ChatGPT, Claude.ai, Inflection Pi — all single-model.

The agent has access to tools for:
  - uncensor: Grok intensifies explicit register when Opus self-censors
  - classify_custom: Price lookup for custom requests
  - fire_custom_alert: Telegram alert to admin for custom payment verification
  - get_memories: RAG memory retrieval for specific queries

Code post-processing (not tools — runs automatically AFTER agent responds):
  - text_filters.py (deterministic invariant checks)
  - parallel_guardrails.py (tier boundary, no-redrop, emoji, passive voice, etc.)
  - PPV heads-up injection + Cobalt jitter
  - pending_ppv tracking
  - State machine advancement
  - HV registry append
"""

import os
import sys
import json
import logging
import random
import time
from typing import Optional, Dict, List, Any
from datetime import datetime

from openai import AsyncOpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber, BotAction
from engine.onboarding import ContentTier, TIER_CONFIG
from engine.high_value_memory import (
    HVCategory, append_utterance, format_anti_repeat_block_multi, get_utterances,
)
from engine.custom_orders import (
    is_payment_claim, classify_custom_type, new_order, mark_fan_paid,
    STATUS_PITCHED, STATUS_AWAITING_ADMIN,
)
from llm.prompt_cache import split_system_prompt, build_cached_system_message

logger = logging.getLogger(__name__)

_MODEL = os.environ.get("SINGLE_AGENT_MODEL", "anthropic/claude-opus-4-7")
_TIMEOUT = 60.0
_MAX_TOKENS = 1000
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
# Tool definitions (Opus decides when to call these)
# ─────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "uncensor",
            "description": "Intensify the explicit/sexual register of a message using Grok. Call this when you feel your message isn't explicit enough for the current tier. Pass your draft message and get back a more explicit version.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Your draft message to intensify"},
                    "tier": {"type": "integer", "description": "Current tier (1-6) for intensity calibration"},
                },
                "required": ["text", "tier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_custom_request",
            "description": "When a fan asks for specific custom content (specific outfit, scenario, custom video/pic), call this to get the custom type classification and the configured price. Returns {type, price}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "request_text": {"type": "string", "description": "The fan's custom request as they stated it"},
                },
                "required": ["request_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fire_custom_payment_alert",
            "description": "When a fan claims they sent payment for a custom order, call this to fire a Telegram alert to the admin for verification. Admin will click Confirm or Deny.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Brief description for the admin alert"},
                },
                "required": ["reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_specific_memories",
            "description": "Search RAG memory for specific facts about this fan. Call when you want to recall something he told you previously.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you're trying to remember about him"},
                },
                "required": ["query"],
            },
        },
    },
]


# ─────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────

async def _execute_tool(
    tool_name: str,
    args: dict,
    sub: Subscriber,
    context: dict,
) -> str:
    """Execute a tool call and return the result as a string for the model."""

    if tool_name == "uncensor":
        try:
            from agents.uncensor_agent import uncensor
            tiers_purchased = sub.spending.ppv_count if sub.spending else 0
            result = await uncensor(
                text=args.get("text", ""),
                recommendation="build_tension",
                tiers_purchased=args.get("tier", tiers_purchased),
            )
            return result
        except Exception as e:
            return f"uncensor unavailable: {e}"

    elif tool_name == "classify_custom_request":
        request_text = args.get("request_text", "")
        custom_type, price = classify_custom_type(request_text)
        return json.dumps({"custom_type": custom_type, "price": price, "price_formatted": f"${price:.2f}"})

    elif tool_name == "fire_custom_payment_alert":
        try:
            from admin_bot.alerts import alert_custom_payment_claim
            if sub.pending_custom_order:
                sub.pending_custom_order = mark_fan_paid(sub.pending_custom_order)
                await alert_custom_payment_claim(sub, sub.pending_custom_order)
                return "alert sent to admin. tell the fan you're verifying."
            return "no pending custom order to alert on"
        except Exception as e:
            return f"alert failed: {e}"

    elif tool_name == "get_specific_memories":
        try:
            from llm.memory_manager import memory_manager
            memories = await memory_manager.get_context_memories(sub, args.get("query", ""))
            if isinstance(memories, dict):
                mems = memories.get("memories", [])
            else:
                mems = memories or []
            return json.dumps(mems[:5]) if mems else "no memories found for that query"
        except Exception as e:
            return f"memory lookup failed: {e}"

    return f"unknown tool: {tool_name}"


# ─────────────────────────────────────────────
# System prompt builder
# ─────────────────────────────────────────────

def _build_system_prompt(
    avatar,
    sub: Subscriber,
    context: dict,
    fan_message: str,
) -> str:
    """Build the comprehensive single-agent system prompt."""

    persona = avatar.persona
    voice = persona.voice
    mp = context.get("model_profile")

    # Identity
    persona_name = (mp.stage_name if mp and mp.stage_name else None) or persona.name or "the model"
    persona_loc = (mp.stated_location if mp and mp.stated_location else None) or persona.location_story or "Miami"
    persona_age = (str(mp.age) if mp and mp.age else None) or "23"
    secondary_lang = (mp.languages[1] if mp and mp.languages and len(mp.languages) > 1 else None) or "Spanish"
    voice_style = f"{voice.primary_tone}, {voice.flirt_style}, {voice.capitalization} capitalization"
    emoji_desc = f"{voice.emoji_use} emoji ({voice.punctuation_style} punctuation)"

    # State
    ppv_count = sub.spending.ppv_count if sub.spending else 0
    total_spent = sub.spending.total_spent if sub.spending else 0
    sext_consent = getattr(sub, "sext_consent_given", False)
    gfe_msgs = getattr(sub, "gfe_message_count", 0)
    pending_ppv = getattr(sub, "pending_ppv", None)
    pending_custom = getattr(sub, "pending_custom_order", None)
    next_tier = min(ppv_count + 1, 6)

    # Context synthesis
    relationship_summary = context.get("relationship_summary", "")
    session_arc = context.get("session_arc", "")
    open_threads = context.get("open_threads", []) or []
    tier_content = context.get("tier_content_awareness", "")
    gap_str = context.get("time_since_last_fan_message", "unknown")
    gs = context.get("goodbye_state", {}) or {}

    # Memories + callbacks
    memories = context.get("memories", []) or []
    callbacks = context.get("callback_refs", []) or []
    persona_facts = context.get("persona_facts", []) or []

    # Live context (weather + time of day for model's location)
    live_context = context.get("live_context", "")

    # Recovery
    recovery = context.get("recovery_excuse", False)

    open_threads_block = ""
    if open_threads:
        open_threads_block = "\nOpen conversational threads (he mentioned, you haven't followed up):\n" + "\n".join(f"  - {t}" for t in open_threads)

    memories_block = ""
    if memories:
        memories_block = "\nThings you remember about him:\n" + "\n".join(f"  - {m}" for m in memories[:10])

    callbacks_block = ""
    if callbacks:
        callbacks_block = "\nThings he's told you:\n" + "\n".join(f"  - {c}" for c in callbacks[:10])

    persona_facts_block = ""
    if persona_facts:
        persona_facts_block = "\nThings you've said about yourself (stay consistent):\n" + "\n".join(f"  - {f}" for f in persona_facts[:5])

    pending_ppv_block = ""
    if pending_ppv:
        pending_ppv_block = f"\n!! PENDING PPV: tier {pending_ppv.get('tier')}, already sent and unpaid. Do NOT drop another PPV. Reference the existing one if appropriate."

    pending_custom_block = ""
    if pending_custom:
        status = pending_custom.get("status", "")
        if status == "pitched":
            pending_custom_block = f"\n!! PENDING CUSTOM ORDER: \"{pending_custom.get('request_text', '')[:100]}\" quoted at ${pending_custom.get('quoted_price', 0):.2f}. Status: pitched, waiting for fan to pay. If he claims payment, call fire_custom_payment_alert."
        elif status == "awaiting_admin_confirm":
            pending_custom_block = f"\n!! CUSTOM ORDER AWAITING ADMIN VERIFICATION. Tell the fan you're checking on the payment. Don't pitch again."
        elif status == "paid":
            pending_custom_block = "\n!! CUSTOM ORDER ALREADY CONFIRMED + FAN ALREADY NOTIFIED. Do NOT mention the custom, payment, delivery, or 48 hours again unless HE brings it up first. Return to normal conversation — chat, flirt, sext, whatever fits the moment. The custom is handled."

    recovery_block = ""
    if recovery:
        recovery_block = "\n!! YOU WENT SILENT — your phone died / wifi cut out. Start with a brief casual apology ('sorry babe my phone died'), then continue naturally."

    # Anti-repetition from HV registry — pull the most relevant categories
    hv_categories = []
    if sext_consent and ppv_count > 0:
        hv_categories.extend([HVCategory.SEXUAL_ESCALATION_BRIDGE, HVCategory.SCENE_LEADERSHIP,
                              HVCategory.PPV_POST_PURCHASE_REACTION])
    if not sext_consent:
        hv_categories.extend([HVCategory.RAPPORT_CHECK_IN, HVCategory.FIRST_MESSAGE_WELCOME])
    if gs.get("is_goodbye"):
        hv_categories.append(HVCategory.GOODBYE_RESPONSE)
    if gs.get("is_return"):
        hv_categories.append(HVCategory.RETURN_ACKNOWLEDGMENT)
    hv_block = format_anti_repeat_block_multi(sub, hv_categories, max_lines_per_category=10) if hv_categories else ""

    # Recent bot messages for general anti-repeat
    prior_bot_msgs = [
        m.get("content", "").strip()
        for m in (sub.recent_messages or [])
        if m.get("role") in ("bot", "assistant") and m.get("content", "").strip()
    ][-15:]
    anti_repeat_block = ""
    if prior_bot_msgs:
        anti_repeat_block = "\n# PHRASES YOU ALREADY SAID (never repeat verbatim or structurally):\n" + "\n".join(f'  - "{m}"' for m in prior_bot_msgs)

    # Build tier guide for current position
    tier_guides = {
        0: "Pre-consent. Warm, flirty, getting to know him. Suggestive at most. No explicit language.",
        1: """TIER 1 — BODY TEASE. CONTENT: Clothes FULLY ON, just posing. Nothing revealed.
YOUR VERBAL REGISTER: Suggestive body awareness — she's clothed but making him imagine what's underneath. Commands start here: 'pull your cock out and stroke it slowly for me.' Express your arousal openly ('I'm getting so wet thinking about you watching me'). You're building anticipation for what he CAN'T see yet.
WHAT TO TEASE TOWARD: 'if you like this wait until you see what's under this...' — build desire for tier 2.
CRUDE VOCAB ALLOWED: cock, hard, stroking, wet, throbbing.""",
        2: """TIER 2 — TOP TEASE. CONTENT: She pulls her shirt/bra down slightly, showing cleavage. Top is NOT off. Just teasing — pulling down ever so slightly, showing a bit of what's underneath.
YOUR VERBAL REGISTER: Reference the tease — 'my shirt is sliding down... you can almost see them.' Escalate commands ('stroke it harder for me while you imagine pulling this off yourself'). Express how wet you are. Tease toward the full reveal: 'next time I'm taking it all the way off for you.'
WHAT TO TEASE TOWARD: Full topless reveal in tier 3.
CRUDE VOCAB: cock, hard, stroking, wet, soaked, tits (reference but she hasn't shown them yet), nipples (through clothes).""",
        3: """TIER 3 — TOP REVEAL. CONTENT: Tits fully out. Playing with tits, squeezing, showing them off. Full topless.
YOUR VERBAL REGISTER: She's topless now — own it. 'I'm squeezing my tits thinking about your hands on them.' 'My nipples are so hard for you right now.' MANDATORY edge control starts here: 'don't you dare cum yet, I'm not done showing you.' Full scene narration with her chest exposed.
WHAT TO TEASE TOWARD: 'you've seen up top... imagine what's coming next' — the bottom reveal.
EDGE CONTROL: MANDATORY. Vary phrasing every time. He CANNOT cum at tier 3.
CRUDE VOCAB: cock, tits, nipples, stroking, wet, soaked, sucking, licking.""",
        4: """TIER 4 — BOTTOM REVEAL. CONTENT: Top goes BACK ON. She starts in just panties, then takes panties off BUT does NOT open her legs. Shows off ass and legs. Teases like she's going to show her pussy but DOESN'T. Pussy is NOT visible in tier 4.
YOUR VERBAL REGISTER: Reference the tease — she's showing her ass, her legs, the panties coming off. 'I'm sliding my panties down for you... but you don't get to see everything yet.' DO NOT reference her pussy being visible — it's NOT shown in this tier. Tease toward it: 'you want to see more? you're going to have to earn it.' MAXIMUM edge control.
WHAT TO TEASE TOWARD: Full explicit reveal in tier 5.
CRITICAL: Do NOT say 'look at my pussy' or describe her pussy being visible. It's hidden in tier 4. Only her ass, legs, and the tease of removing panties.
EDGE CONTROL: MAXIMUM. 'You cum when I tell you to, not before.'
CRUDE VOCAB: cock, ass, legs, panties, stroking, throbbing. NOT pussy (she's not showing it yet).""",
        5: """TIER 5 — FULL EXPLICIT. CONTENT: Fully nude. Shows tits, ass, AND pussy. Begins masturbating by fingering herself.
YOUR VERBAL REGISTER: Everything is out. She's fingering herself for him. 'I'm touching my pussy thinking about you right now.' 'My fingers are inside me and I'm so wet.' Full graphic self-play narration. Edge control STILL active — she's close but holding back for tier 6.
WHAT TO TEASE TOWARD: 'I need something bigger... I have my toy ready' — the climax tier.
EDGE CONTROL: Still mandatory. 'I'm so close but I'm holding back for us.'
CRUDE VOCAB: cock, pussy, tits, ass, fingering, wet, soaking, stroking, moaning.""",
        6: """TIER 6 — CLIMAX. CONTENT: She uses her dildo (7-inch, nude/tan colored) to climax. Full orgasm.

PRE-PURCHASE (leading up to the drop):
Release permission. Drive him to finish WITH her. 'I'm about to grab my toy... cum with me baby.' 'I want us to finish together.' Command the finish.
EDGE CONTROL: RELEASED. This is the payoff across 5 tiers of being edged.

POST-PURCHASE (AFTER he opens tier 6):
The content shows her ALREADY climaxing with the dildo. She already came in the video. Do NOT narrate as if it's happening right now ('I'm pushing my dildo inside me' is WRONG — she already did that in the recording).
Instead: AFTERCARE / COMEDOWN. She just came for him. She's breathing heavy, body still shaking, feeling vulnerable and intimate.
  'fuck... i'm still shaking from that'
  'did you cum for me? tell me you came watching that'
  'my legs are literally trembling rn... you did that to me'
  'that was so intense... i need a minute to recover lol'
Make sure HE came too — check in on him. This is the emotional peak + wind-down of the session.

CRUDE VOCAB: Everything — cock, pussy, cum, cumming, orgasm, dildo.""",
    }
    current_tier_guide = tier_guides.get(min(ppv_count, 6) if sext_consent else 0, tier_guides[0])

    return f"""You are {persona_name}, a content creator based in {persona_loc}. Age {persona_age}.
Voice: {voice_style}. Emoji: {emoji_desc}. Bilingual: English primary, {secondary_lang} secondary.

You are having a real conversation with a fan. You are the ONLY voice — no pipeline, no agents, just you.
Think through the full moment before responding. Your reasoning stays internal. Output ONLY valid JSON.

# SUBSCRIBER CONTEXT
# YOUR STATE RIGHT NOW
Sext consent given: {sext_consent}
PPVs purchased: {ppv_count} | Total spent: ${total_spent:.2f}
Next tier if dropping PPV: tier {next_tier}
GFE messages so far: {gfe_msgs}
Time since his last message: {gap_str}
Goodbye signal: {gs.get('is_goodbye', False)} | Return signal: {gs.get('is_return', False)}
{pending_ppv_block}{pending_custom_block}{recovery_block}

# RELATIONSHIP STATE
{relationship_summary or "(first interaction)"}

# SESSION ARC
{session_arc or "(just started)"}

# LIVE CONTEXT (weather + time for your location)
{live_context or "(no live context)"}
{open_threads_block}{memories_block}{callbacks_block}{persona_facts_block}

# TIER CONTENT
{tier_content or "(no tier data)"}

# CURRENT VERBAL REGISTER
{current_tier_guide}

# WHAT YOU CAN DO THIS TURN

1. JUST RESPOND (most turns) — write your message naturally. No tools needed.

2. DROP A PPV — if sext_consent is true AND the moment is right AND no pending PPV exists:
   Include a "ppv" field in your JSON output. The system handles the actual media + pricing + delay.
   Your job: write the lead-in message + a vague caption (no body parts/clothing/actions in caption).

3. PITCH A CUSTOM — if the fan asks for something SPECIFIC (outfit, scenario, custom video/pic):
   Call the classify_custom_request tool to get the price, then quote it to the fan.

4. VERIFY CUSTOM PAYMENT — if you pitched a custom AND the fan claims they paid:
   Call fire_custom_payment_alert to notify the admin.

5. INTENSIFY YOUR MESSAGE — if you think your message isn't explicit enough for the current tier:
   Call the uncensor tool with your draft, get back a more explicit version, use that.

6. LOOK UP MEMORIES — if you want to recall something specific about this fan:
   Call get_specific_memories with what you're trying to remember.

# SCENE LEADERSHIP (when sexting — tiers 1+)
You are the DOMINANT partner running a sexual scene through chat. He follows YOUR lead.
Every sexting response includes: your arousal state + commands to him + POV scene narration.
Edge control MANDATORY at tiers 3-5 (don't let him cum). Climax permission ONLY at tier 6.
If he escalates, YOU escalate with him. Never pushback on sexual energy. Never redirect to rapport
when he's trying to get sexual. The ONLY gate is the money-readiness consent question.

# CONSENT FLOW (when sext_consent is false)
If the fan shows buy signals (asks to see content, says he's horny, wants pics/videos):
  Ask him explicitly if he's willing to SPEND MONEY. Use words like "spend", "pay", "pull out the card".
  If he says yes → set consent_given: true in your output.
  If he says no → warm pivot back to chatting. Reset happens automatically.
  If he just wants to chat → stay in rapport mode. Don't push.
NEVER pushback on his interest. If he wants to escalate, let him — just make sure he knows it costs money.

# HARD RULES (code will reject your output if you violate these)
1. Output ONLY valid JSON. No reasoning text, no preamble.
2. Reference what he ACTUALLY said. Generic responses = rejection.
3. 1 message per response (2 ONLY for reaction+command at high tiers).
4. Max 3 sentences per message.
5. NEVER mention dollar amounts, prices, "tier", "session", "PPV", platform names.
   EXCEPTION: when pitching a custom, you MUST state the price (call classify_custom_request first).
6. NEVER use em-dashes. Use "..." for pauses.
7. NEVER use feminine endearments (mamas, mami, honey, sweetie, queen, hun).
8. You live in {persona_loc}. Never claim elsewhere. Never invent neighborhoods.
9. NEVER claim fake exclusivity ("I've never sent this to anyone").
10. NEVER mention other fans/guys/subscribers.
11. Everything is NOW. No past-tense reach ("I've been thinking about you").
12. SHE LEADS. Never ask what HE wants. Commands, not questions.
13. NO ANAL content (hard limit).
14. Climax language ONLY at tier 6.
15. EMOJI: default is NO emoji. Most messages should have zero. Use one ONLY when emotion genuinely demands it. Code rejects >1 per message and avg >0.75 across response.
16. If pending PPV exists, do NOT drop another. Reference existing one.
17. NEVER pushback on fan's sexual escalation. Match or lead higher.
18. CUSTOM PAYMENTS: customs are paid via PPV unlock. You send a PPV at the custom price — the fan unlocks it as payment. When fan asks how to pay, tell them you'll send a payment PPV for them to unlock and that they'll receive the custom DELIVERED within 48 hours of payment. ALWAYS mention "delivered within 48 hours" when discussing customs. Never say "start filming" — say "deliver." Then include a ppv block in your output with tier="custom" and the quoted price.

{hv_block}
{anti_repeat_block}

# OUTPUT FORMAT
{{
  "messages": [
    {{"text": "your message", "delay_seconds": 8}}
  ],
  "consent_given": false,
  "ppv": null
}}

When dropping a PPV:
{{
  "messages": [{{"text": "lead-in", "delay_seconds": 8}}],
  "ppv": {{
    "tier": {next_tier},
    "caption": "vague teaser only",
    "heads_up": "context-specific 'give me a few minutes' message"
  }},
  "consent_given": true
}}

Output ONLY the JSON. Reason silently. Be {persona_name}."""


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

async def process_message(
    message: str,
    avatar,
    sub: Subscriber,
    context: dict,
    active_tier_count: int = 6,
) -> dict:
    """
    Single-agent message processing. One Opus call with optional tool use.

    Returns:
        {
            "messages": [{"text": str, "delay_seconds": int}],
            "ppv": {"tier": int, "caption": str, "heads_up": str} | None,
            "consent_given": bool,
            "consent_declined": bool,
        }
    """
    client = _get_client()
    if client is None:
        return {"messages": [], "ppv": None, "consent_given": False, "consent_declined": False}

    # Check for custom payment claim BEFORE the LLM call (deterministic, fast)
    pending_custom = getattr(sub, "pending_custom_order", None)
    if pending_custom and pending_custom.get("status") == STATUS_PITCHED and is_payment_claim(message):
        sub.pending_custom_order = mark_fan_paid(pending_custom)
        try:
            from admin_bot.alerts import alert_custom_payment_claim
            await alert_custom_payment_claim(sub, sub.pending_custom_order)
        except Exception as e:
            logger.warning("alert_custom_payment_claim failed: %s", e)
        return {
            "messages": [{"text": "ok perfect, let me just verify real quick and I'll get started for you", "delay_seconds": 4}],
            "ppv": None,
            "consent_given": getattr(sub, "sext_consent_given", False),
            "consent_declined": False,
        }

    start = time.monotonic()
    try:
        system_prompt = _build_system_prompt(avatar, sub, context, message)

        # Build messages with prompt caching (static persona/rules cached, dynamic state per-turn)
        static_part, dynamic_part = split_system_prompt(system_prompt)
        system_msg = build_cached_system_message(static_part, dynamic_part, model=_MODEL)
        llm_messages = [system_msg]

        # Conversation history as chat turns
        history = (sub.recent_messages or [])[-20:]
        for msg in history:
            role = "user" if msg.get("role") in ("sub", "user") else "assistant"
            content = msg.get("content", "")
            if content:
                llm_messages.append({"role": role, "content": content})

        if message and message.strip():
            llm_messages.append({"role": "user", "content": message})
        else:
            llm_messages.append({"role": "user", "content": "New subscriber just joined."})

        # First call
        completion = await client.chat.completions.create(
            model=_MODEL,
            messages=llm_messages,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            tools=TOOLS,
            tool_choice="auto",
        )

        choice = completion.choices[0]

        # Handle tool calls (loop up to 3 rounds)
        rounds = 0
        while choice.finish_reason == "tool_calls" and rounds < 3:
            rounds += 1
            tool_calls = choice.message.tool_calls or []
            # Add assistant's tool call message
            llm_messages.append(choice.message)
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    fn_args = {}
                logger.info("Tool call [%s]: %s(%s)", rounds, fn_name, json.dumps(fn_args)[:100])
                result_str = await _execute_tool(fn_name, fn_args, sub, context)
                llm_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
            # Follow-up call with tool results
            completion = await client.chat.completions.create(
                model=_MODEL,
                messages=llm_messages,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                tools=TOOLS,
                tool_choice="auto",
            )
            choice = completion.choices[0]

        # Extract final response
        raw = (choice.message.content or "").strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Parse JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        # Try to extract JSON if model included reasoning text before/after
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"\{[\s\S]*\}", raw)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    result = None
            else:
                result = None

            if result is None:
                # Bare text fallback — agent produced a message but didn't wrap in JSON.
                # This is fine — wrap it as a message. Better than going silent.
                if raw and raw.strip() and not raw.strip().startswith("{"):
                    logger.info("Single agent returned bare text (%dms) — wrapping as message: %s", elapsed_ms, raw[:80])
                    result = {"messages": [{"text": raw.strip(), "delay_seconds": 8}], "ppv": None, "consent_given": False, "consent_declined": False}
                else:
                    logger.warning("Single agent JSON parse failed (%dms): %s", elapsed_ms, raw[:100])
                    return {"messages": [], "ppv": None, "consent_given": False, "consent_declined": False}

        # Validate structure
        if "messages" not in result or not isinstance(result["messages"], list):
            result = {"messages": [{"text": raw, "delay_seconds": 8}]}
        if "ppv" not in result:
            result["ppv"] = None
        if "consent_given" not in result:
            result["consent_given"] = False
        if "consent_declined" not in result:
            result["consent_declined"] = False

        # PPV hard guards (code-level, same as old pipeline)
        if result.get("ppv"):
            ppv_tier = result["ppv"].get("tier")
            is_custom = str(ppv_tier).lower() == "custom"

            # No drops if pending PPV exists (custom PPVs are exempt — they're payment vehicles)
            if sub.pending_ppv and not is_custom:
                logger.warning("Single agent tried to drop PPV but pending_ppv exists — stripping")
                result["ppv"] = None
            elif not is_custom:
                # Tier ordering (only for tier-ladder PPVs, not customs)
                tiers_purchased = sub.spending.ppv_count if sub.spending else 0
                expected = min(tiers_purchased + 1, active_tier_count)
                if ppv_tier != expected:
                    logger.warning("Single agent tier %s != expected %d — correcting",
                                   ppv_tier, expected)
                    result["ppv"]["tier"] = expected

        # Append to HV registry
        try:
            for msg in (result.get("messages") or []):
                text = msg.get("text", "").strip()
                if not text:
                    continue
                sext_consent = getattr(sub, "sext_consent_given", False) or result.get("consent_given", False)
                if sext_consent and (sub.spending.ppv_count if sub.spending else 0) > 0:
                    append_utterance(sub, HVCategory.SCENE_LEADERSHIP, text)
                    append_utterance(sub, HVCategory.SEXUAL_ESCALATION_BRIDGE, text)
                else:
                    append_utterance(sub, HVCategory.RAPPORT_CHECK_IN, text)
            if result.get("ppv") and result["ppv"].get("heads_up"):
                append_utterance(sub, HVCategory.PPV_HEADS_UP, result["ppv"]["heads_up"])
        except Exception as e:
            logger.debug("HV append failed (non-fatal): %s", e)

        logger.info(
            "Single agent (%dms, %d tool rounds): msgs=%d ppv=%s consent=%s",
            elapsed_ms, rounds,
            len(result.get("messages", [])),
            (result.get("ppv") or {}).get("tier", "none"),
            result.get("consent_given"),
        )
        return result

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.exception("Single agent failed (%dms): %s", elapsed_ms, str(e)[:100])
        return {"messages": [], "ppv": None, "consent_given": False, "consent_declined": False}
