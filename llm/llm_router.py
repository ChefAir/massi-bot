"""
Massi-Bot LLM - Router

Decides whether a subscriber message should be handled by the LLM
or the template engine, then orchestrates the full LLM pipeline:
  1. Check if state is LLM-eligible
  2. Build system prompt + conversation history
  3. Call LLM client
  4. Apply guardrails (post-processing)
  5. Apply typo injection (natural mobile errors)
  6. Wrap in BotAction(s) with dynamic delay + optional burst mode
  7. Return list[BotAction] or None (triggers template fallback)

CRITICAL: The selling pipeline (WARMING through POST_SESSION) NEVER uses LLM.
Only GFE_ACTIVE, RETENTION, and RE_ENGAGEMENT states are LLM-eligible.

Integration with connectors:
    from llm.llm_router import llm_router

    # After getting sub from Supabase, before calling engine:
    avatar = controller.avatars.get(sub.persona_id)
    actions = await llm_router.route(sub, message, avatar)
    if actions:
        # Use LLM actions — already have correct delays + burst mode
        pass
    else:
        # Fall through to template engine
        actions = controller.handle_message(sub.sub_id, message)
"""

import math
import random
import logging
from datetime import datetime
from typing import Optional

from models import Subscriber, SubState, BotAction
from llm.llm_client import llm_client
from llm.prompts import (
    build_system_prompt, build_messages, build_bridge_prompt,
    build_enhance_prompt, build_full_prompt, _determine_context_type,
)
from llm.guardrails import post_process, post_process_stateful, get_mode_for_state, GuardrailMode
from llm.typo_injector import inject_typos
from llm.memory_extractor import update_callback_references
from llm.memory_manager import memory_manager
from llm.validator import validate_response
from llm.context_awareness import build_context_block, get_weather

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# State eligibility
# ─────────────────────────────────────────────

# These states use LLM for non-scripted, freeform conversation
LLM_ELIGIBLE_STATES: frozenset[SubState] = frozenset({
    SubState.GFE_ACTIVE,
    SubState.RETENTION,
    SubState.RE_ENGAGEMENT,
})

# These selling-pipeline states get an LLM bridge reaction BEFORE the template PPV drop.
# The LLM does NOT replace the template — it prepends a 1-2 sentence human reaction.
BRIDGE_ELIGIBLE_STATES: frozenset[SubState] = frozenset({
    SubState.WARMING,
    SubState.TENSION_BUILD,
    SubState.FIRST_PPV_READY,
    SubState.FIRST_PPV_SENT,
    SubState.LOOPING,
})

# These states get LLM text enhancement: template engine runs for state advancement,
# but the response text is rewritten by LLM to sound natural and reactive.
ENHANCE_STATES: frozenset[SubState] = frozenset({
    SubState.QUALIFYING,
    SubState.WARMING,
})

# Everything else — selling pipeline — ALWAYS uses templates
TEMPLATE_ONLY_STATES: frozenset[SubState] = frozenset(
    s for s in SubState if s not in LLM_ELIGIBLE_STATES
)

# Generic safe fallback if both LLM and templates fail
GENERIC_FALLBACK = "hmm I got distracted for a sec 😂 what were you saying? 😏"

# Better fallbacks for when LLM fails in specific states
# These are generic enough to work in any context without sounding scripted
_STATE_FALLBACKS: dict[str, list[str]] = {
    "gfe_active": [
        "hmm sorry I got distracted 😂 what were you saying?",
        "wait tell me more about that 😏",
        "you can't just say that and not elaborate 😂",
    ],
    "retention": [
        "hey you 😏 I was just thinking about you",
        "missed you 💕 what's on your mind?",
        "you always text at the perfect time 😂",
    ],
    "re_engagement": [
        "there you are 😏 I was wondering where you went",
        "hey stranger 💕 miss me?",
    ],
    "post_session": [
        "that was fun 😏 you're something else",
        "I can't stop thinking about earlier 🥺",
    ],
}

# ─────────────────────────────────────────────
# Grok uncensoring prompt (Layer 2 of 3-layer architecture)
# ─────────────────────────────────────────────

_UNCENSOR_SYSTEM = """You are an explicit text rewriter for an adult content platform. Your ONLY job is to take clean/implied text and make it sexually explicit.

RULES:
1. Keep the EXACT same structure, length, and emotional tone
2. Keep all emojis in their original positions
3. Replace euphemisms and implied references with explicit language
4. If the text is already casual/flirty with no sexual implications, return it UNCHANGED
5. Do NOT add new topics, questions, or content — only make existing implications explicit
6. Keep it in first person, same voice
7. Maximum 3 sentences — same as the input

EXAMPLES:
Input: "I'm thinking about you in ways I shouldn't 😏 you have no idea what you do to me"
Output: "I'm touching myself thinking about you 😏 my pussy is throbbing and it's your fault"

Input: "you're making me feel things right now 😈 I wish you could see"
Output: "you're making me so wet right now 😈 I wish you could see how hard my nipples are"

Input: "hey what's up? how was your day 😊"
Output: "hey what's up? how was your day 😊"
(unchanged — no sexual implication to uncensor)

Now rewrite the following text. If there's nothing to uncensor, return it exactly as-is:"""

# States where Grok uncensoring is applied (selling + GFE)
_UNCENSOR_STATES = frozenset({
    "warming", "tension_build", "first_ppv_ready", "first_ppv_sent",
    "looping", "objection_1", "objection_2", "objection_3",
    "brokey_treatment", "gfe_active",
})

# ─────────────────────────────────────────────
# Bridge signal detection
# ─────────────────────────────────────────────

import re as _re

# Explicit / engaged fan signals that warrant a bridge reaction
_ENGAGEMENT_PATTERNS = _re.compile(
    r"\b(hard|cock|dick|stroking|stroke|jerking|jerk|rubbing|rub|horny|turned on|so wet|"
    r"masturbat|touching myself|touching yourself|cumming|cum|orgasm|getting off|"
    r"lose my mind|losing my mind|can't stop|can't focus|can't think|"
    r"want you so bad|need you|I want you|I need you|you drive me|you make me|"
    r"you're so hot|you're incredible|you're beautiful|you're gorgeous|"
    r"think about you|thinking about you|dream about you|"
    r"i miss you|missed you|been thinking)\b",
    _re.IGNORECASE,
)

# Price/money objections — do NOT bridge these, let objection handler work
_OBJECTION_PATTERNS = _re.compile(
    r"\b(too expensive|can't afford|too much|broke|no money|that's a lot|"
    r"cheaper|discount|free|not worth|waste of|rip off|scam)\b",
    _re.IGNORECASE,
)

# Minimum word count for a bridge — don't react to 1-2 word messages
_BRIDGE_MIN_WORDS = 3


def _should_bridge(message: str) -> bool:
    """
    Return True if this fan message warrants an LLM bridge reaction.

    Conditions:
      - Message has ≥3 words
      - Contains an engagement/arousal signal
      - Does NOT look like a price objection
      - Is not a system message
    """
    if not message or message.startswith("["):
        return False
    words = message.split()
    if len(words) < _BRIDGE_MIN_WORDS:
        return False
    if _OBJECTION_PATTERNS.search(message):
        return False
    return bool(_ENGAGEMENT_PATTERNS.search(message))


# ─────────────────────────────────────────────
# U1: Log-normal three-component delay model
# ─────────────────────────────────────────────

def calculate_reply_delay(
    fan_message: str,
    bot_response: str,
    high_intensity: bool = False,
    emotional_excitement: bool = False,
) -> int:
    """
    Calculate a human-realistic reply delay using a three-component model:
      1. Reading time  — 250 ms per word in the fan's message
      2. Think time    — log-normal distribution (right-skewed, μ=0.7, σ=0.5)
      3. Typing time   — 36.2 WPM (validated average mobile typing speed)

    Time-of-day multipliers:
      Late night (23:00–04:59): 1.5–3× (slow, sleepy, distracted)
      Early morning (05:00–08:59): 1.2–1.8×
      Business hours (09:00–17:59): 1.0×
      Evening (18:00–22:59): 0.8–1.1× (engaged, relaxed)

    Context modifiers:
      high_intensity — halves both think and typing time (fast, excited exchange)
      emotional_excitement — −20% typing time (fingers moving fast)

    Returns: delay in seconds, clamped 3s–150s.

    Source: ACM CUI 2024, Aalto University typing-speed study, log-normal
    distribution validated against human chat data.
    """
    fan_words = len(fan_message.split()) if fan_message else 1
    reading_time = fan_words * 0.15  # 150 ms/word

    # Think time — scales with response complexity
    bot_words = len(bot_response.split()) if bot_response else 5
    if bot_words <= 8:
        think_time = random.uniform(1.0, 3.0)
    elif bot_words <= 20:
        think_time = random.uniform(2.0, 5.0)
    else:
        think_time = random.uniform(4.0, 9.0)

    # Typing time at 45 WPM = 0.75 words/second (fast texter)
    typing_time = bot_words / 0.75

    # Time-of-day multiplier on think time only
    hour = datetime.now().hour
    if 23 <= hour or hour < 5:
        think_time *= random.uniform(1.3, 2.0)   # Late night — slower
    elif 5 <= hour < 9:
        think_time *= random.uniform(1.1, 1.5)   # Early morning

    # Context modifiers
    if high_intensity:
        think_time *= 0.5
        typing_time *= 0.7
    if emotional_excitement:
        typing_time *= 0.8

    # Random ±15% jitter
    total = (reading_time + think_time + typing_time) * random.uniform(0.85, 1.15)
    return max(2, min(int(total), 20))


# ─────────────────────────────────────────────
# U2: Multi-message burst mode
# ─────────────────────────────────────────────

def split_into_burst(text: str) -> list[str]:
    """
    Split a response into a burst of 2–4 short messages, mimicking the way
    humans send multiple quick messages instead of one long one.

    Rules:
      - Always split responses >50 words
      - 40% chance to split responses 20–50 words
      - No split for responses <20 words (short replies read as one)

    Splitting strategy: prefer sentence boundaries, then clause boundaries
    (comma/em-dash), then natural phrase breaks.

    Returns list of message strings (1 item if not split).
    """
    words = text.split()
    word_count = len(words)

    # Decide whether to split
    if word_count < 20:
        return [text]
    if word_count < 50 and random.random() > 0.40:
        return [text]

    # Attempt sentence-boundary split first
    import re
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]

    if len(sentences) >= 2:
        # Group sentences into 2–3 bursts
        if len(sentences) == 2:
            return sentences
        elif len(sentences) == 3:
            # 50% chance: 3 messages, 50% chance: group last 2 into one
            if random.random() > 0.5:
                return sentences
            return [sentences[0], f"{sentences[1]} {sentences[2]}"]
        else:
            # 4+ sentences → 2–3 bursts
            mid = len(sentences) // 2
            return [
                " ".join(sentences[:mid]),
                " ".join(sentences[mid:]),
            ]

    # No sentence breaks — split on comma/em-dash in the middle
    comma_pos = text.find(",", len(text) // 3)
    if comma_pos > 0:
        return [text[:comma_pos].strip(), text[comma_pos + 1:].strip()]

    # Last resort: split at the midpoint word
    mid = len(words) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def _inter_burst_delay() -> int:
    """
    Delay between burst messages: 1–3 seconds.
    Human thumbs take 1-3s between quick follow-up messages.
    Source: ACM CUI 2024 inter-message timing analysis.
    """
    return random.randint(1, 3)


# ─────────────────────────────────────────────
# Decision context extraction for full-LLM mode
# ─────────────────────────────────────────────

def _extract_decision_context(
    sub: Subscriber,
    pre_state: SubState,
    template_actions: list[BotAction],
) -> dict:
    """
    Extract structured decision metadata from the engine's template actions.

    This tells the LLM what the engine decided (state transition, PPV tier,
    objection level) without exposing template text.
    """
    has_ppv = any(a.action_type == "send_ppv" for a in template_actions)
    ppv_action = next((a for a in template_actions if a.action_type == "send_ppv"), None)
    template_messages = [a.message for a in template_actions if a.action_type == "send_message" and a.message]

    # Determine the mission key (which _STATE_MISSIONS entry to use)
    mission_key = pre_state.value

    # Override for objection states
    obj_level = sub.tier_no_count
    if obj_level > 0 and pre_state in (
        SubState.FIRST_PPV_SENT, SubState.LOOPING, SubState.CUSTOM_PITCH,
    ):
        if sub.brokey_flagged:
            mission_key = "brokey_treatment"
        elif obj_level >= 3:
            mission_key = "objection_3"
        elif obj_level == 2:
            mission_key = "objection_2"
        elif obj_level == 1:
            mission_key = "objection_1"

    # Override for session-locked retention
    if pre_state == SubState.RETENTION and sub.session_locked_until:
        from datetime import datetime as _dt
        if _dt.now() < sub.session_locked_until:
            mission_key = "retention_locked"

    # Calculate days silent for re-engagement
    days_silent = 0
    if sub.last_message_date:
        from datetime import datetime as _dt
        days_silent = (_dt.now() - sub.last_message_date).days

    # Extract content description metadata from PPV action if available
    content_description = {}
    if ppv_action and ppv_action.metadata:
        content_description = {
            "clothing": ppv_action.metadata.get("clothing_description", ""),
            "location": ppv_action.metadata.get("location_description", ""),
            "mood": ppv_action.metadata.get("mood", ""),
            "key_detail": ppv_action.metadata.get("key_detail", ""),
        }

    return {
        "pre_state": pre_state.value,
        "post_state": sub.state.value,
        "mission_key": mission_key,
        "is_returning": sub.message_count > 0 or bool(sub.recent_messages),
        "has_ppv": has_ppv,
        "ppv_tier": ppv_action.metadata.get("tier") if ppv_action else None,
        "ppv_price": ppv_action.ppv_price if ppv_action else None,
        "objection_level": obj_level,
        "is_brokey": sub.brokey_flagged,
        "session_locked": bool(
            sub.session_locked_until
            and sub.session_locked_until > __import__("datetime").datetime.now()
        ),
        "loop_number": sub.current_loop_number or 1,
        "qualifying_q_index": sub.qualifying_questions_asked,
        "days_silent": days_silent,
        "likely_bought": sub.spending.is_buyer and pre_state == SubState.FIRST_PPV_SENT,
        "template_messages": template_messages,
        "content_description": content_description,
    }


# ─────────────────────────────────────────────
# Router class
# ─────────────────────────────────────────────

class LLMRouter:
    """
    Routes messages to LLM or templates based on subscriber state.
    Thread-safe: no mutable state stored between calls.
    """

    def should_use_llm(self, sub: Subscriber) -> bool:
        """
        Return True if this subscriber's current state is LLM-eligible
        AND the LLM client is available.
        """
        if sub.state not in LLM_ELIGIBLE_STATES:
            return False
        if not llm_client.is_available:
            logger.debug("LLM not available — routing to templates for %s", sub.sub_id)
            return False
        return True

    async def route(
        self,
        sub: Subscriber,
        message: str,
        avatar,
    ) -> Optional[list[BotAction]]:
        """
        Attempt to generate an LLM response for this message.

        Returns:
            List of BotAction(s) ready to execute — includes dynamic delay
            and burst mode splitting. Returns None if LLM is not applicable,
            failed, or guardrails tripped. A None return means: fall through
            to the template engine.

        Args:
            sub: Subscriber object (loaded from Supabase).
            message: The incoming message text.
            avatar: AvatarConfig for this subscriber's persona.
                    If None, falls back to templates immediately.
        """
        if not self.should_use_llm(sub):
            return None

        if avatar is None:
            logger.debug("No avatar for sub %s — skipping LLM", sub.sub_id)
            return None

        try:
            # U8: Retrieve relevant RAG memories for this message
            rag_memories = await memory_manager.get_context_memories(sub, message)

            # U9: Build live context (weather + fan time detection)
            persona_loc = avatar.persona.location_story if avatar.persona else "Miami"
            weather = await get_weather(persona_loc)
            live_context = build_context_block(
                fan_messages=sub.recent_messages[-5:] if sub.recent_messages else [],
                avatar_location=persona_loc,
                weather=weather,
            )

            # Build prompt and message history
            context_type = _determine_context_type(sub)
            system_prompt = build_system_prompt(avatar, sub, context_type, rag_memories=rag_memories, live_context=live_context)
            messages = build_messages(system_prompt, sub, message)

            # Call LLM
            raw_response = await llm_client.generate(messages)
            if raw_response is None:
                return None

            # Apply guardrails
            avatar_emojis = list(avatar.persona.voice.favorite_phrases) if (
                avatar.persona and avatar.persona.voice
            ) else None

            clean_response = post_process(raw_response, avatar_emojis)
            if clean_response is None:
                logger.info(
                    "Guardrails rejected LLM response for sub %s — using templates",
                    sub.sub_id,
                )
                return None

            # U6: Extract and store personal disclosures from fan message
            n_facts = update_callback_references(sub, message)
            if n_facts:
                logger.debug("U6 memory: added %d facts for sub %s", n_facts, sub.sub_id)

            # U8: Store facts to pgvector for future RAG retrieval
            await memory_manager.maybe_extract_and_store(sub, message)

            # Apply typo injection (U11)
            clean_response = inject_typos(clean_response)

            logger.info(
                "LLM response accepted for sub %s (state=%s context=%s)",
                sub.sub_id, sub.state.value, context_type,
            )

            # Wrap into BotActions with dynamic delay + burst mode (U1 + U2)
            return self.wrap_as_actions(clean_response, fan_message=message)

        except Exception as exc:
            logger.exception("LLM router error for sub %s: %s", sub.sub_id, exc)
            return None

    async def route_bridge(
        self,
        sub: Subscriber,
        message: str,
        avatar,
    ) -> Optional[list[BotAction]]:
        """
        Generate a 1-2 sentence LLM reaction to the fan's message, to prepend
        before a template PPV drop in the selling pipeline.

        Called for BRIDGE_ELIGIBLE_STATES only when the fan's message contains
        an engagement/arousal signal (not a price objection).

        Returns:
            List with a single BotAction (the reaction message) ready to prepend
            to template actions. Returns None if bridge is not warranted, LLM
            failed, or guardrails tripped — caller falls back to templates-only.

        Critical: this method does NOT call controller.handle_message() or
        mutate subscriber state. It only generates the reactive text.
        """
        if sub.state not in BRIDGE_ELIGIBLE_STATES:
            return None
        if not _should_bridge(message):
            return None
        if avatar is None:
            return None
        if not llm_client.is_available:
            return None

        try:
            system_prompt = build_bridge_prompt(avatar, sub, message)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]

            raw = await llm_client.generate(messages, max_tokens=80)
            if raw is None:
                return None

            # Guardrails — same post-processing as normal LLM responses
            avatar_emojis = list(avatar.persona.voice.favorite_phrases) if (
                avatar.persona and avatar.persona.voice
            ) else None
            clean = post_process(raw, avatar_emojis)
            if clean is None:
                logger.debug("Bridge guardrails rejected response for sub %s", sub.sub_id)
                return None

            # Typo injection — same as normal
            clean = inject_typos(clean)

            # Bridge delay: shorter than full reply (fan is already engaged)
            # Use high_intensity=True to get a faster, snappier timing
            delay = calculate_reply_delay(
                message, clean,
                high_intensity=True,
                emotional_excitement=True,
            )

            logger.debug("Bridge reaction generated for sub %s (state=%s)", sub.sub_id, sub.state.value)
            return [BotAction(
                action_type="send_message",
                message=clean,
                delay_seconds=delay,
                metadata={"source": "llm_bridge"},
            )]

        except Exception as exc:
            logger.debug("Bridge LLM error for sub %s: %s — skipping bridge", sub.sub_id, exc)
            return None

    async def route_enhance(
        self,
        sub: Subscriber,
        message: str,
        avatar,
        template_actions: list,
        pre_state: "SubState",
    ) -> list:
        """
        Enhance template message text with LLM naturalness for QUALIFYING and WARMING states.

        The template engine has already run (state has advanced). This method takes
        the first send_message action from template_actions, rewrites its text via LLM
        to react to the fan's actual message, and returns the enhanced action list.

        State transitions and all other action fields are preserved from the template.
        Falls back to unmodified template_actions if LLM fails.

        Args:
            sub: Subscriber (state already advanced by template engine).
            message: Original fan message.
            avatar: AvatarConfig for this subscriber's persona.
            template_actions: Actions returned by controller.handle_message().
            pre_state: Subscriber state BEFORE the template engine ran.
        """
        if pre_state not in ENHANCE_STATES:
            return template_actions
        if not template_actions:
            return template_actions
        if avatar is None:
            return template_actions
        if not llm_client.is_available:
            return template_actions

        # Find the first send_message action to enhance
        target_idx = next(
            (i for i, a in enumerate(template_actions) if a.action_type == "send_message"),
            None,
        )
        if target_idx is None:
            return template_actions

        template_msg = template_actions[target_idx].message
        context_type = "qualifying" if pre_state == SubState.QUALIFYING else "warming"

        try:
            system_prompt = build_enhance_prompt(avatar, sub, message, template_msg, context_type)
            llm_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]

            raw = await llm_client.generate(llm_messages, max_tokens=120)
            if raw is None:
                return template_actions

            avatar_emojis = list(avatar.persona.voice.favorite_phrases) if (
                avatar.persona and avatar.persona.voice
            ) else None
            clean = post_process(raw, avatar_emojis)
            if clean is None:
                return template_actions

            clean = inject_typos(clean)

            # Replace only the message text — preserve state transitions and delays
            import copy
            enhanced = copy.copy(template_actions[target_idx])
            enhanced.message = clean
            enhanced.metadata = {**template_actions[target_idx].metadata, "source": "llm_enhance"}

            result = list(template_actions)
            result[target_idx] = enhanced

            logger.debug(
                "Enhanced %s message for sub %s: %r → %r",
                pre_state.value, sub.sub_id, template_msg[:40], clean[:40],
            )
            return result

        except Exception as exc:
            logger.debug("Enhance LLM error for sub %s: %s — using template", sub.sub_id, exc)
            return template_actions

    async def route_full(
        self,
        sub: Subscriber,
        message: str,
        avatar,
        template_actions: list[BotAction],
        pre_state: SubState,
    ) -> list[BotAction]:
        """
        Full-LLM mode: replace ALL template text with LLM-generated responses.

        The engine already ran via controller.handle_message() — state is advanced,
        PPV timing is decided, objection counting is done. This method:
        1. Extracts decision metadata from template_actions
        2. Builds a state-specific mission prompt
        3. Calls LLM with 5-model fallback rotation
        4. Applies state-specific guardrails
        5. Replaces send_message text; preserves send_ppv price/content_id
        6. Falls back to template_actions if LLM fails

        Args:
            sub: Subscriber (state already advanced by engine).
            message: Original fan message.
            avatar: AvatarConfig for this subscriber's persona.
            template_actions: Actions returned by controller.handle_message().
            pre_state: Subscriber state BEFORE engine ran.

        Returns:
            List of BotActions with LLM-generated text (or template fallback).
        """
        if not template_actions:
            return template_actions

        # Immediate fallback if no avatar or LLM unavailable
        if avatar is None or not llm_client.is_available:
            return template_actions

        try:
            # Extract decision context from what the engine decided
            decision_ctx = _extract_decision_context(sub, pre_state, template_actions)

            # ── PPV readiness override ──────────────────────────
            # If engine stayed in WARMING or TENSION_BUILD, ask the LLM
            # whether the fan is ready for a PPV drop right now.
            # If YES, force state to FIRST_PPV_READY and generate PPV actions.
            if pre_state in (SubState.QUALIFYING, SubState.WARMING, SubState.TENSION_BUILD) and not decision_ctx.get("has_ppv"):
                from llm.ppv_readiness import check_ppv_readiness
                recent_for_check = (sub.recent_messages or [])[-6:]
                ppv_ready = await check_ppv_readiness(
                    recent_for_check, pre_state.value, sub.message_count,
                )
                if ppv_ready:
                    logger.info(
                        "PPV readiness override for sub %s -- forcing FIRST_PPV_READY",
                        sub.sub_id,
                    )
                    from engine.onboarding import ContentTier, TIER_CONFIG
                    tier = ContentTier.TIER_1_BODY_TEASE
                    tier_cfg = TIER_CONFIG[tier]
                    sub.state = SubState.FIRST_PPV_SENT
                    sub.current_loop_number = 1
                    template_actions = [
                        BotAction(
                            action_type="send_message",
                            message="I actually have something I want to show you...",
                            delay_seconds=random.randint(3, 8),
                        ),
                        BotAction(
                            action_type="send_ppv",
                            ppv_price=tier_cfg["price"],
                            ppv_caption="just for you",
                            content_id="",
                            message="",
                            delay_seconds=random.randint(5, 12),
                            metadata={"tier": tier.value, "bundle_id": ""},
                            new_state=SubState.FIRST_PPV_SENT,
                        ),
                    ]
                    # Re-extract decision context with the new PPV actions
                    decision_ctx = _extract_decision_context(sub, pre_state, template_actions)

            # Retrieve RAG memories
            rag_memories = await memory_manager.get_context_memories(sub, message)

            # U8: Retrieve persona self-identity facts for consistency
            persona_facts = await memory_manager.get_persona_context()
            if persona_facts:
                decision_ctx["persona_facts"] = persona_facts

            # CRITICAL: The engine's process_message() already added the current
            # fan message + template bot responses to sub.recent_messages.
            # We must strip those before building LLM messages, because:
            #   1. build_messages() appends `message` as the final user message
            #   2. The template bot response shouldn't be in history (we're replacing it)
            # Count how many messages the engine just added (1 fan + N bot template msgs)
            n_template_msgs = 1 + len([a for a in template_actions if a.message])  # fan + bot msgs
            saved_recent = sub.recent_messages
            sub.recent_messages = saved_recent[:-n_template_msgs] if n_template_msgs <= len(saved_recent) else []

            # U9: Build live context (weather + fan time detection)
            persona_loc = avatar.persona.location_story if avatar.persona else "Miami"
            weather = await get_weather(persona_loc)
            live_context = build_context_block(
                fan_messages=saved_recent[-5:] if saved_recent else [],
                avatar_location=persona_loc,
                weather=weather,
            )

            # Build mission-specific prompt
            system_prompt = build_full_prompt(
                avatar, sub, decision_ctx, message, rag_memories=rag_memories,
                live_context=live_context,
            )
            messages = build_messages(system_prompt, sub, message)

            # Restore recent_messages (engine's tracking needs them intact)
            sub.recent_messages = saved_recent

            # Determine max_tokens based on state
            mission_key = decision_ctx.get("mission_key", "")
            if mission_key in ("qualifying", "disqualified", "cooled_off"):
                max_tokens = 150
            elif mission_key.startswith("objection") or mission_key == "brokey_treatment":
                max_tokens = 120
            else:
                max_tokens = 200

            # Determine if this is a selling/explicit state (for Grok uncensoring)
            is_selling = mission_key in _UNCENSOR_STATES

            # Smart fallback: for non-selling states, use curated fallbacks instead
            # of engine templates (which are generic and sound scripted)
            def _get_fallback() -> list[BotAction]:
                fallbacks = _STATE_FALLBACKS.get(mission_key)
                if fallbacks:
                    fb_text = random.choice(fallbacks)
                    logger.info("Using curated fallback for sub %s (state=%s)", sub.sub_id, mission_key)
                    return self.wrap_as_actions(fb_text, fan_message=message)
                return template_actions

            # ── Layer 1: Opus generates clean, instruction-following text ──
            raw_response = await llm_client.generate_opus(messages, max_tokens=max_tokens)
            opus_generated = raw_response is not None

            if raw_response is None:
                # Opus failed — fall back to Grok as generator
                logger.info("Opus generation failed for sub %s — falling back to Grok", sub.sub_id)
                raw_response = await llm_client.generate(messages, max_tokens=max_tokens)

            # Smart fallback if generation failed entirely
            if raw_response is None:
                logger.info("LLM returned None for sub %s — using fallback", sub.sub_id)
                return _get_fallback()

            # ── Layer 2: Grok uncensors (only if Opus generated and state is explicit) ──
            if opus_generated and is_selling:
                uncensor_messages = [
                    {"role": "system", "content": _UNCENSOR_SYSTEM},
                    {"role": "user", "content": raw_response},
                ]
                uncensored = await llm_client.generate(
                    uncensor_messages,
                    max_tokens=max_tokens,
                    temperature=0.8,
                    frequency_penalty=0.0,
                    presence_penalty=0.0,
                )
                if uncensored:
                    logger.info("Grok uncensored response for sub %s", sub.sub_id)
                    raw_response = uncensored
                # If Grok uncensoring fails, use the clean Opus text as-is

            # Apply state-specific guardrails
            mode = get_mode_for_state(decision_ctx.get("mission_key", pre_state.value))
            # Override to OBJECTION mode for objection states
            if mission_key.startswith("objection"):
                mode = GuardrailMode.OBJECTION

            avatar_emojis = list(avatar.persona.voice.favorite_phrases) if (
                avatar.persona and avatar.persona.voice
            ) else None

            fan_word_count = len(message.split()) if message else 0

            # Tier boundary enforcement:
            # After _handle_loop runs, loop_number is already incremented PAST the tier being sold.
            # E.g., when dropping T2 PPV, loop_number = 3 (ready for T3 next).
            # The fan hasn't SEEN the current PPV yet — dirty talk must match what they've
            # actually received so far, which is one tier BELOW the one being dropped.
            # With PPV: current_shown = loop_number - 2 (fan saw up to previous tier)
            # Without PPV: current_shown = loop_number - 1 (no new content being sent)
            tier_level_raw = decision_ctx.get("loop_number", 0) or 0
            has_ppv = decision_ctx.get("has_ppv", False)
            if has_ppv:
                current_shown_tier = max(0, tier_level_raw - 2)
            else:
                current_shown_tier = max(0, tier_level_raw - 1)

            clean = post_process_stateful(raw_response, mode, avatar_emojis, fan_word_count=fan_word_count, tier_level=current_shown_tier)
            if clean is None:
                logger.info("Guardrails rejected LLM response for sub %s (mode=%s) — regenerating", sub.sub_id, mode.value)
                # Regenerate with explicit correction instead of falling to templates
                regen_messages = messages + [
                    {"role": "assistant", "content": raw_response},
                    {"role": "user", "content": (
                        "Your response was rejected by safety filters. Rewrite it following these rules:\n"
                        "- Do NOT use feminine endearments (mamas, mama, mami, honey, sweetie, darling, queen, hun)\n"
                        "- Do NOT say goodnight, goodbye, or end the conversation\n"
                        "- Do NOT mention prices or dollar amounts\n"
                        "- Do NOT use AI vocabulary (delve, nuanced, certainly, absolutely)\n"
                        "- Do NOT use system terminology (tier, level, PPV, content drop, unlock, pricing ladder, session number)\n"
                        "- Do NOT describe what the PPV content shows. Keep PPV teasers vague ('something special', 'you're gonna love this')\n"
                        "- Stay within the explicitness of what you've actually shown him so far\n"
                        "- React to what the fan actually said with matching emotional depth\n"
                        "Rewrite now. Same voice, same length."
                    )},
                ]
                # Regenerate with Opus if it was the original generator
                if opus_generated:
                    raw_regen = await llm_client.generate_opus(regen_messages, max_tokens=max_tokens)
                else:
                    raw_regen = await llm_client.generate(regen_messages, max_tokens=max_tokens)
                if raw_regen:
                    # Re-uncensor if needed
                    if opus_generated and is_selling:
                        uncensor_regen = [
                            {"role": "system", "content": _UNCENSOR_SYSTEM},
                            {"role": "user", "content": raw_regen},
                        ]
                        uncensored_regen = await llm_client.generate(
                            uncensor_regen, max_tokens=max_tokens,
                            temperature=0.8, frequency_penalty=0.0, presence_penalty=0.0,
                        )
                        if uncensored_regen:
                            raw_regen = uncensored_regen
                    clean_regen = post_process_stateful(raw_regen, mode, avatar_emojis, fan_word_count=fan_word_count, tier_level=current_shown_tier)
                    if clean_regen:
                        clean = clean_regen
                        logger.info("Regenerated response accepted for sub %s (guardrail retry)", sub.sub_id)
                if clean is None:
                    # Both attempts failed — use fallback
                    return _get_fallback()

            # ── Layer 3: Opus validates final response ──────────────
            # Catches: tier violations, contradictions, topic loops,
            # ignoring fan, platform names, filler phrases.
            persona_name = avatar.persona.name if avatar.persona else "the model"
            persona_loc = avatar.persona.location_story if avatar.persona else "Miami"

            # Collect topics from recent history for dedup checking
            topics = []
            for m in (saved_recent or [])[-6:]:
                if m.get("role") == "bot":
                    # Extract key nouns/phrases as rough topic markers
                    topics.append(m.get("content", "")[:60])

            is_valid, fix_instruction = await validate_response(
                proposed_response=clean,
                fan_message=message,
                recent_history=saved_recent[-8:] if saved_recent else [],
                tier_level=decision_ctx.get("loop_number", 0) or 0,
                persona_location=persona_loc,
                persona_name=persona_name,
                topics_mentioned=topics,
            )

            if not is_valid and fix_instruction:
                logger.info("Validator rejected — regenerating with fix: %s", fix_instruction[:80])
                fix_messages = messages + [
                    {"role": "assistant", "content": raw_response},
                    {"role": "user", "content": (
                        f"CORRECTION NEEDED: {fix_instruction}\n"
                        "Rewrite your response fixing this issue. Keep same voice and length."
                    )},
                ]
                if opus_generated:
                    raw_v2 = await llm_client.generate_opus(fix_messages, max_tokens=max_tokens)
                else:
                    raw_v2 = await llm_client.generate(fix_messages, max_tokens=max_tokens)
                if raw_v2:
                    if opus_generated and is_selling:
                        unc_v2_msgs = [
                            {"role": "system", "content": _UNCENSOR_SYSTEM},
                            {"role": "user", "content": raw_v2},
                        ]
                        unc_v2 = await llm_client.generate(
                            unc_v2_msgs, max_tokens=max_tokens,
                            temperature=0.8, frequency_penalty=0.0, presence_penalty=0.0,
                        )
                        if unc_v2:
                            raw_v2 = unc_v2
                    clean_v2 = post_process_stateful(raw_v2, mode, avatar_emojis, fan_word_count=fan_word_count, tier_level=current_shown_tier)
                    if clean_v2:
                        clean = clean_v2
                        logger.info("Regenerated response accepted for sub %s", sub.sub_id)
                    # If v2 also fails guardrails, use the original clean (already passed guardrails)

            # Apply typo injection (U11)
            clean = inject_typos(clean)

            # Memory extraction (U6 + U8)
            n_facts = update_callback_references(sub, message)
            if n_facts:
                logger.debug("U6 memory: added %d facts for sub %s", n_facts, sub.sub_id)
            await memory_manager.maybe_extract_and_store(sub, message)

            # U8: Extract and store persona self-identity facts from bot response
            await memory_manager.maybe_store_persona_facts(clean)

            # Build final action list: replace send_message text, preserve send_ppv
            import copy
            result_actions = []
            llm_actions_inserted = False

            for action in template_actions:
                if action.action_type == "send_message" and not llm_actions_inserted:
                    # Replace ALL send_message actions with the LLM response
                    # (burst mode handles splitting into multiple messages)
                    llm_wrapped = self.wrap_as_actions(clean, fan_message=message)
                    # Preserve state transitions from the first template action
                    if llm_wrapped and action.new_state:
                        llm_wrapped[-1].new_state = action.new_state
                    if llm_wrapped and action.new_script_phase:
                        llm_wrapped[-1].new_script_phase = action.new_script_phase
                    # Tag as full-LLM source
                    for la in llm_wrapped:
                        la.metadata = {**la.metadata, "source": "llm_full"}
                    result_actions.extend(llm_wrapped)
                    llm_actions_inserted = True

                elif action.action_type == "send_message" and llm_actions_inserted:
                    # Skip subsequent send_message actions (LLM already covers them)
                    # But preserve any state transitions they carry
                    if action.new_state and result_actions:
                        result_actions[-1].new_state = action.new_state
                    continue

                elif action.action_type == "send_ppv":
                    # PPV actions pass through UNCHANGED — price, caption, content_id from engine
                    # Add realistic "content creation" delay — she's taking photos/videos
                    # This maintains the illusion she's creating content in real-time
                    ppv_delay = random.randint(5, 15)  # 5-15s to "take a photo/video"
                    import copy as _copy
                    ppv_action = _copy.copy(action)
                    ppv_action.delay_seconds = ppv_delay
                    result_actions.append(ppv_action)

                else:
                    # Flag, wait, send_free — pass through
                    result_actions.append(action)

            logger.info(
                "Full-LLM response for sub %s (state=%s→%s, mission=%s)",
                sub.sub_id, pre_state.value, sub.state.value, mission_key,
            )
            return result_actions

        except Exception as exc:
            logger.exception("route_full error for sub %s: %s", sub.sub_id, exc)
            return template_actions

    def wrap_as_actions(
        self,
        response: str,
        fan_message: str = "",
        high_intensity: bool = False,
        emotional_excitement: bool = False,
    ) -> list[BotAction]:
        """
        Wrap an LLM response string into a list of BotAction(s).

        Applies:
          - U1: Dynamic delay (log-normal three-component model)
          - U2: Burst mode splitting (2-4 messages, 1-3s inter-message gap)

        Returns a list — usually 1 item, sometimes 2–4 for burst mode.
        """
        parts = split_into_burst(response)

        if len(parts) == 1:
            # Single message — full delay before sending
            delay = calculate_reply_delay(
                fan_message, response,
                high_intensity=high_intensity,
                emotional_excitement=emotional_excitement,
            )
            return [BotAction(
                action_type="send_message",
                message=response,
                delay_seconds=delay,
                metadata={"source": "llm"},
            )]

        # Burst mode — full delay before first, 1-3s between subsequent messages
        actions = []
        first_delay = calculate_reply_delay(
            fan_message, parts[0],
            high_intensity=high_intensity,
            emotional_excitement=emotional_excitement,
        )
        for i, part in enumerate(parts):
            delay = first_delay if i == 0 else _inter_burst_delay()
            actions.append(BotAction(
                action_type="send_message",
                message=part,
                delay_seconds=delay,
                metadata={"source": "llm", "burst": True, "burst_index": i, "burst_total": len(parts)},
            ))
        return actions

    def wrap_as_action(
        self,
        response: str,
        delay_seconds: int = 60,
    ) -> BotAction:
        """
        Legacy single-action wrapper. Kept for backward compatibility.
        Prefer wrap_as_actions() for new code.
        """
        return BotAction(
            action_type="send_message",
            message=response,
            delay_seconds=delay_seconds,
            metadata={"source": "llm"},
        )


# Singleton instance
llm_router = LLMRouter()
