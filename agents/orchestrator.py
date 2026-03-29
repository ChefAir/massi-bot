"""
Massi-Bot Multi-Agent — Orchestrator

Coordinates all 5 agents into a single pipeline that replaces the old
engine state machine + LLM router. This is the main entry point for
processing fan messages and purchase events.

Pipeline:
  1. [Code] Context Builder — memories, weather, profile
  2. [Opus] Emotion Analyzer + [Opus] Sales Strategist (parallel)
  3. [Opus] Conversation Director (gets output from 1+2)
  4. [Grok] Uncensor Agent (selling states only)
  5. [Opus] Quality Validator (PASS or FIX → retry)
  6. [Code] Action Builder — converts JSON to BotActions

Replaces: engine/controller.py handle_message + llm/llm_router.py route_full
"""

import os
import sys
import asyncio
import random
import logging
import uuid
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from models import Subscriber, SubState, BotAction
from engine.onboarding import ContentTier, TIER_CONFIG

from agents.context_builder import build_context
from agents.emotion_analyzer import analyze_emotion
from agents.sales_strategist import analyze_strategy
from agents.conversation_director import generate_response
from agents.uncensor_agent import uncensor
from agents.quality_validator import validate
from agents.gfe_agent import generate_gfe_response, check_rapport_metrics

# Memory extraction (runs async after response)
from llm.memory_extractor import update_callback_references, extract_facts
from llm.memory_manager import memory_manager

# Guardrails (architectural tier boundary enforcement)
from llm.guardrails import post_process_stateful, get_mode_for_state, GuardrailMode

logger = logging.getLogger(__name__)

# Tier prices (fixed, never change)
_TIER_PRICES = {
    1: 27.38, 2: 36.56, 3: 77.35,
    4: 92.46, 5: 127.45, 6: 200.00,
}

# Map strategist recommendations to guardrail modes
_RECOMMENDATION_TO_MODE = {
    "qualify": GuardrailMode.QUALIFYING,
    "gfe_building": GuardrailMode.QUALIFYING,
    "consent_check": GuardrailMode.QUALIFYING,
    "warm": GuardrailMode.SELLING,
    "build_tension": GuardrailMode.SELLING,
    "drop_ppv": GuardrailMode.SELLING,
    "post_purchase": GuardrailMode.SELLING,
    "handle_objection": GuardrailMode.OBJECTION,
    "brokey_treatment": GuardrailMode.OBJECTION,
    "pending_ppv": GuardrailMode.SELLING,
    "gfe": GuardrailMode.STANDARD,
    "retention": GuardrailMode.STANDARD,
    "re_engagement": GuardrailMode.STANDARD,
}


async def process_message(
    sub: Subscriber,
    message: str,
    avatar=None,
    model_profile=None,
) -> list[BotAction]:
    """
    Process an incoming fan message through the 5-agent pipeline.

    This is the main entry point — replaces controller.handle_message()
    + llm_router.route_full().

    Args:
        sub: Subscriber object (loaded from Supabase).
        message: The fan's message text.
        avatar: AvatarConfig for this subscriber's persona.

    Returns:
        List of BotActions ready to execute (send_message, send_ppv, etc.)
    """
    if not message or not message.strip():
        return []

    # Generate request ID for tracing this message through all agents
    req_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Processing message for sub %s: %s", req_id, sub.sub_id, message[:60])

    # Record the incoming message
    sub.add_message("sub", message)
    sub.message_count += 1

    try:
        # ── Step 1: Build context (code, no LLM) ──
        context = await build_context(sub, message, avatar, model_profile=model_profile)
        context["request_id"] = req_id

        # ── Step 1b: Emotion Analyzer (always runs — needed by both paths) ──
        emotion_task = asyncio.create_task(
            analyze_emotion(
                message=message,
                conversation_history=context["conversation_history"],
                subscriber_summary=context["subscriber_summary"],
            )
        )

        # ── GFE-FIRST ROUTING GATE ──
        # New subscribers without consent go to GFE Agent.
        # Returning buyers (ppv_count > 0) go straight to selling pipeline.
        sext_consent = getattr(sub, 'sext_consent_given', False)
        ppv_count = sub.spending.ppv_count if sub.spending else 0

        if not sext_consent and ppv_count == 0:
            emotion_analysis = await emotion_task
            logger.info("[%s] Routing to GFE path (no consent, no purchases)", req_id)
            return await _gfe_path(sub, message, avatar, context, emotion_analysis)

        # ── SELLING PIPELINE (unchanged) ──
        # Fire strategist in parallel (emotion already running)
        strategy_task = asyncio.create_task(
            analyze_strategy(
                message=message,
                conversation_history=context["conversation_history"],
                spending_summary=context["spending_summary"],
                tier_progress=context["tier_progress"],
                callback_refs=context.get("callback_refs", []),
            )
        )

        emotion_analysis, strategy = await asyncio.gather(emotion_task, strategy_task)

        # ── Step 2b: Escalation safeguard ──
        # Trust the Sales Strategist's decision but add a safety ceiling.
        # Only nudge escalation when the Strategist is already moving toward selling.
        recommendation = strategy.get("recommendation", "warm")
        tiers_purchased = context.get("tier_progress", {}).get("tiers_purchased", 0)
        buy_readiness = emotion_analysis.get("buy_readiness", 0)

        # Soft nudge: if Strategist says warm/build_tension AND buy_readiness is high
        # AND we've had 12+ fan messages with no PPV, suggest moving to next phase
        if (sub.message_count >= 12
                and tiers_purchased == 0
                and recommendation == "warm"
                and buy_readiness >= 6):
            logger.info(
                "Escalation safeguard: %d msgs, buy_readiness=%d — nudging warm→build_tension",
                sub.message_count, buy_readiness,
            )
            strategy["recommendation"] = "build_tension"
            strategy["pacing_note"] = (strategy.get("pacing_note", "") +
                " Transition naturally to tension — fan is ready.")

        # Hard ceiling: if Strategist already says build_tension or drop_ppv
        # AND 20+ fan messages with no PPV, force the drop
        if (sub.message_count >= 20
                and tiers_purchased == 0
                and recommendation in ("build_tension", "drop_ppv")):
            logger.info(
                "Escalation safeguard ceiling: %d msgs, 0 PPVs — forcing drop_ppv tier 1",
                sub.message_count,
            )
            strategy["recommendation"] = "drop_ppv"
            strategy["tier"] = 1

        # ── Step 3: Conversation Director ──
        director_output = await generate_response(
            message=message,
            avatar=avatar,
            sub=sub,
            context=context,
            emotion_analysis=emotion_analysis,
            strategy=strategy,
        )

        # Extract text from director output
        messages_list = director_output.get("messages", [])
        ppv_info = director_output.get("ppv")

        if not messages_list:
            messages_list = [{"text": "hmm I got distracted 😏 what were you saying?", "delay_seconds": 8}]

        # ── Step 4: Uncensor Agent (selling states only) ──
        recommendation = strategy.get("recommendation", "warm")
        tiers_purchased = context.get("tier_progress", {}).get("tiers_purchased", 0)

        uncensored_messages = []
        for msg in messages_list:
            text = msg.get("text", "")
            if text:
                uncensored_text = await uncensor(
                    text=text,
                    recommendation=recommendation,
                    tiers_purchased=tiers_purchased,
                )
                uncensored_messages.append({
                    "text": uncensored_text,
                    "delay_seconds": msg.get("delay_seconds", 8),
                })
            else:
                uncensored_messages.append(msg)

        # ── Step 5: Quality Validator ──
        # Validate the COMBINED response (all messages joined), not each individually.
        # This prevents the triple-send bug where each rejected message spawns a new one.
        mp = model_profile or context.get("model_profile")
        persona_name = (mp.stage_name if mp and mp.stage_name else None) or (avatar.persona.name if avatar and avatar.persona else "the model")
        persona_loc = (mp.stated_location if mp and mp.stated_location else None) or (avatar.persona.location_story if avatar and avatar.persona else "Miami")

        mode = _RECOMMENDATION_TO_MODE.get(recommendation, GuardrailMode.STANDARD)
        avatar_emojis = None  # Use default emoji pool from guardrails (favorite_phrases are text, not emojis)
        avatar_id = avatar.persona.ig_account_tag if avatar and avatar.persona else ""
        fan_word_count = len(message.split())

        # Apply guardrails to each uncensored message
        guardrail_passed_messages = []
        for msg in uncensored_messages:
            text = msg.get("text", "")
            if not text:
                continue
            clean = post_process_stateful(
                text, mode, avatar_emojis,
                fan_word_count=fan_word_count,
                tier_level=tiers_purchased,
                avatar_id=avatar_id,
            )
            if clean is None:
                # Guardrails rejected uncensored version — use clean (pre-uncensor) text
                original_idx = uncensored_messages.index(msg)
                if original_idx < len(messages_list):
                    clean = messages_list[original_idx].get("text", "")
                if not clean:
                    clean = "hmm 😏 what were you saying?"
                logger.info("Guardrails rejected uncensored text — using clean version")
            guardrail_passed_messages.append({
                "text": clean,
                "delay_seconds": msg.get("delay_seconds", 8),
            })

        if not guardrail_passed_messages:
            guardrail_passed_messages = [{"text": "hmm 😏 what were you saying?", "delay_seconds": 8}]

        # Validate the FULL combined response text (not per-message)
        combined_response = " ".join(m["text"] for m in guardrail_passed_messages if m.get("text"))

        is_valid, fix_instruction = await validate(
            response=combined_response,
            fan_message=message,
            conversation_history=context["conversation_history"],
            tiers_purchased=tiers_purchased,
            persona_location=persona_loc,
            persona_name=persona_name,
            avatar_id=avatar_id,
        )

        validated_messages = guardrail_passed_messages

        if not is_valid and fix_instruction:
            logger.info("Validator rejected: %s — regenerating once", fix_instruction[:80])
            # Regenerate entire response (not per-message) — max 1 retry
            fix_strategy = dict(strategy)
            fix_strategy["pacing_note"] = f"CORRECTION: {fix_instruction}. Fix this in your response."
            regen_output = await generate_response(
                message=message,
                avatar=avatar,
                sub=sub,
                context=context,
                emotion_analysis=emotion_analysis,
                strategy=fix_strategy,
            )
            regen_msgs = regen_output.get("messages", [])
            if regen_msgs:
                # Process ALL regen messages through uncensor + guardrails
                regen_validated = []
                for rm in regen_msgs:
                    rt = rm.get("text", "")
                    if not rt:
                        continue
                    rt = await uncensor(rt, recommendation, tiers_purchased)
                    rc = post_process_stateful(
                        rt, mode, avatar_emojis,
                        fan_word_count=fan_word_count,
                        tier_level=tiers_purchased,
                        avatar_id=avatar_id,
                    )
                    if rc:
                        regen_validated.append({"text": rc, "delay_seconds": rm.get("delay_seconds", 8)})
                if regen_validated:
                    validated_messages = regen_validated
                    # Update ppv_info from regenerated output if present
                    regen_ppv = regen_output.get("ppv")
                    if regen_ppv:
                        ppv_info = regen_ppv
                    logger.info("Regenerated response accepted (%d messages)", len(regen_validated))

        # ── Step 5b: Update subscriber state based on strategist recommendation ──
        logger.info("[%s] Pipeline complete: recommendation=%s, msgs=%d, ppv=%s",
                     req_id, recommendation, len(validated_messages),
                     ppv_info.get("tier") if ppv_info else "none")
        _advance_state(sub, recommendation, ppv_info)

        # ── Step 6: Build BotActions ──
        actions = _build_actions(validated_messages, ppv_info, sub)

        # Track bot messages
        for action in actions:
            if action.message and action.action_type == "send_message":
                sub.add_message("bot", action.message)

        # ── Background: Memory extraction ──
        try:
            update_callback_references(sub, message)
            await memory_manager.maybe_extract_and_store(sub, message)
            # Store persona facts from bot response
            for action in actions:
                if action.message and action.action_type == "send_message":
                    await memory_manager.maybe_store_persona_facts(action.message)
        except Exception as e:
            logger.debug("Memory extraction error: %s", e)

        return actions

    except Exception as exc:
        logger.exception("Orchestrator error for sub %s: %s", sub.sub_id, exc)
        return [BotAction(
            action_type="send_message",
            message="hmm I got distracted for a sec 😂 what were you saying? 😏",
            delay_seconds=random.randint(5, 12),
        )]


async def process_purchase(
    sub: Subscriber,
    amount: float,
    avatar=None,
    content_type: str = "ppv",
    model_profile=None,
) -> list[BotAction]:
    """
    Process a purchase event through the pipeline.

    Called when a real purchase is confirmed (webhook or sim 'paid').
    Generates post-purchase reaction + next tier PPV.

    Args:
        sub: Subscriber who made the purchase.
        amount: Dollar amount.
        avatar: AvatarConfig for this subscriber's persona.
        content_type: Type of purchase.

    Returns:
        List of BotActions: [reaction message, lead-in, next PPV] or [reaction, post-session].
    """
    sub.record_purchase(amount, content_type)

    # ── GFE Continuation Payment Handling ──
    # If this was a continuation payment, reset the counter and clear the gate
    if content_type == "gfe_continuation" or (
            sub.gfe_continuation_pending and 15.0 <= amount <= 25.0):
        sub.gfe_continuation_pending = False
        sub.gfe_message_count = 0
        sub.gfe_continuations_paid = getattr(sub, 'gfe_continuations_paid', 0) + 1
        logger.info("GFE continuation paid by %s — counter reset to 0 (total paid: %d)",
                     sub.sub_id, sub.gfe_continuations_paid)

    try:
        # Build context
        context = await build_context(sub, "paid", avatar, model_profile=model_profile)

        # Run strategy with purchase flag
        strategy = await analyze_strategy(
            message="paid",
            conversation_history=context["conversation_history"],
            spending_summary=context["spending_summary"],
            tier_progress=context["tier_progress"],
            callback_refs=context.get("callback_refs", []),
            is_purchase_event=True,
        )

        # Emotion analysis (fan just bought — assume positive)
        emotion_analysis = {
            "emotion": "excited",
            "engagement": 9,
            "buy_readiness": 8,
            "key_signals": ["just purchased"],
            "fan_time_of_day": "unknown",
        }

        # Director generates post-purchase reaction + next tier lead-in
        director_output = await generate_response(
            message="paid",
            avatar=avatar,
            sub=sub,
            context=context,
            emotion_analysis=emotion_analysis,
            strategy=strategy,
        )

        messages_list = director_output.get("messages", [])
        ppv_info = director_output.get("ppv")

        # Uncensor + validate (same as process_message)
        recommendation = strategy.get("recommendation", "post_purchase")
        tiers_purchased = context.get("tier_progress", {}).get("tiers_purchased", 0)

        validated_messages = []
        for msg in messages_list:
            text = msg.get("text", "")
            if text:
                text = await uncensor(text, recommendation, tiers_purchased)
                # Light guardrails for post-purchase
                clean = post_process_stateful(
                    text, GuardrailMode.SELLING, None,
                    fan_word_count=5, tier_level=tiers_purchased,
                    avatar_id=avatar_id,
                )
                validated_messages.append({
                    "text": clean or text,
                    "delay_seconds": msg.get("delay_seconds", 8),
                })

        actions = _build_actions(validated_messages, ppv_info, sub)

        # Track bot messages
        for action in actions:
            if action.message and action.action_type == "send_message":
                sub.add_message("bot", action.message)

        return actions

    except Exception as exc:
        logger.exception("Purchase orchestrator error for sub %s: %s", sub.sub_id, exc)
        return [BotAction(
            action_type="send_message",
            message="omg you actually opened it 😍 you have no idea how happy that makes me",
            delay_seconds=random.randint(5, 12),
        )]


async def process_new_subscriber(
    sub: Subscriber,
    avatar=None,
    model_profile=None,
) -> list[BotAction]:
    """
    Generate a welcome message for a brand new subscriber.

    Args:
        sub: New subscriber.
        avatar: AvatarConfig for this subscriber's persona.

    Returns:
        List with welcome message BotAction.
    """
    try:
        context = await build_context(sub, "", avatar, model_profile=model_profile)

        # For new subs, we don't need emotion/strategy — just welcome
        emotion_analysis = {
            "emotion": "curious",
            "engagement": 5,
            "buy_readiness": 2,
            "key_signals": ["new subscriber"],
            "fan_time_of_day": "unknown",
        }
        strategy = {
            "recommendation": "qualify",
            "tier": None,
            "objection_level": 0,
            "reasoning": "Brand new subscriber — simple flirty intro",
            "pacing_note": "Short, flirty intro. Just say hi and be inviting. Do NOT ask what brought them here — in production they message you first. Keep it to 1-2 short messages max.",
        }

        # Check if returning user
        is_returning = sub.message_count > 0 or bool(sub.recent_messages)
        if is_returning:
            strategy["pacing_note"] = (
                "This fan has chatted before. Greet warmly like catching up with someone you missed. "
                "Reference past conversations if you have callback references. Keep it short — 1-2 messages."
            )

        director_output = await generate_response(
            message="",
            avatar=avatar,
            sub=sub,
            context=context,
            emotion_analysis=emotion_analysis,
            strategy=strategy,
        )

        messages_list = director_output.get("messages", [])
        if not messages_list:
            persona_name = avatar.persona.name if avatar and avatar.persona else "babe"
            messages_list = [{"text": f"hey 😏 I'm {persona_name}... what caught your eye?", "delay_seconds": 8}]

        actions = []
        for msg in messages_list:
            text = msg.get("text", "")
            if text:
                actions.append(BotAction(
                    action_type="send_message",
                    message=text,
                    delay_seconds=msg.get("delay_seconds", random.randint(5, 12)),
                ))

        sub.state = SubState.WELCOME_SENT

        # Track bot messages
        for action in actions:
            if action.message:
                sub.add_message("bot", action.message)

        return actions

    except Exception as exc:
        logger.exception("Welcome orchestrator error: %s", exc)
        return [BotAction(
            action_type="send_message",
            message="hey 😏 what caught your eye?",
            delay_seconds=random.randint(5, 12),
        )]


# GFE continuation paywall — $20 every 30 messages
_GFE_CONTINUATION_INTERVAL = 30
_GFE_CONTINUATION_PRICE = 20.00
_GFE_DECAY_PER_DAY = 10  # Messages of counter to decay per 24h of absence


async def _build_continuation_actions(
    sub: Subscriber,
    avatar,
    context: dict,
    emotion_analysis: dict,
) -> list[BotAction]:
    """
    Build the continuation paywall pitch using the GFE Agent.

    The agent generates a natural pitch that flows from the current conversation,
    then we append a $20 PPV. Unique every time.
    """
    # Ask GFE Agent to generate the pitch in context
    try:
        pitch_output = await generate_gfe_response(
            message="[SYSTEM: Generate a continuation pitch — see instructions]",
            avatar=avatar,
            sub=sub,
            context=context,
            emotion_analysis=emotion_analysis,
            continuation_pitch=True,
        )
        pitch_msgs = pitch_output.get("messages", [])
        pitch_text = pitch_msgs[0].get("text", "") if pitch_msgs else ""
    except Exception as e:
        logger.warning("GFE continuation pitch generation failed: %s — using fallback", e)
        pitch_text = ""

    if not pitch_text:
        _avatar_id = avatar.persona.ig_account_tag if avatar and avatar.persona else ""
        if _avatar_id == "goth_domme":
            import random as _rng
            pitch_text = _rng.choice([
                "ugh okay so this stupid app makes me do this thing. its $20 to keep going. i know. i hate it too. but i dont make the rules 🙄",
                "okay dont be mad at me... fanvue is doing that paywall thing. $20 and we can pretend this never happened and keep talking 💀",
                "so the app decided to interrupt us. rude. $20 to keep me around. your call pretty boy.",
                "i would literally keep talking for free but this app has other plans. $20. blame fanvue not me 🖤",
            ])
        else:
            pitch_text = (
                "I'm not gonna lie... I really love talking to you and I don't wanna stop "
                "😩 but I need to know this means something to you too"
            )

    actions = [
        BotAction(
            action_type="send_message",
            message=pitch_text,
            delay_seconds=random.randint(10, 20),
        ),
        BotAction(
            action_type="send_ppv",
            message="",
            ppv_price=_GFE_CONTINUATION_PRICE,
            ppv_caption="unlock to keep talking to me 😘",
            delay_seconds=random.randint(5, 10),
            metadata={"type": "gfe_continuation", "tier": "continuation"},
        ),
    ]

    sub.add_message("bot", pitch_text)
    return actions


async def _gfe_path(
    sub: Subscriber,
    message: str,
    avatar,
    context: dict,
    emotion_analysis: dict,
) -> list[BotAction]:
    """
    Handle messages through the GFE Agent (pre-consent path).

    Runs instead of the selling pipeline for new subscribers
    who haven't given sext consent yet.
    """
    # ── ABSENCE DECAY ──
    # If the fan has been away 24+ hours, decay the message counter.
    # This gives them runway to re-warm but not a full free ride.
    # Decay: 10 messages per 24h of absence, minimum 0.
    if sub.last_message_date and sub.gfe_message_count > 0:
        hours_away = (datetime.now() - sub.last_message_date).total_seconds() / 3600
        if hours_away >= 24:
            days_away = hours_away / 24
            decay = int(_GFE_DECAY_PER_DAY * days_away)
            old_count = sub.gfe_message_count
            # Decay within the current interval window (don't undo a paid gate)
            count_in_window = sub.gfe_message_count % _GFE_CONTINUATION_INTERVAL
            decayed_window = max(0, count_in_window - decay)
            sub.gfe_message_count = (sub.gfe_message_count - count_in_window) + decayed_window
            if sub.gfe_message_count < 0:
                sub.gfe_message_count = 0
            # If they had a pending gate and were away long enough, clear it
            # (they've been gone — the silence already happened)
            if sub.gfe_continuation_pending and days_away >= 3:
                sub.gfe_continuation_pending = False
                logger.info("GFE continuation gate cleared for %s after %d days away", sub.sub_id, int(days_away))
            if old_count != sub.gfe_message_count:
                logger.info("GFE decay: %s was away %.1f days, counter %d → %d",
                             sub.sub_id, days_away, old_count, sub.gfe_message_count)

    # Track GFE message count
    if sub.state in (SubState.NEW, SubState.WELCOME_SENT, SubState.QUALIFYING,
                     SubState.GFE_BUILDING, SubState.SEXT_CONSENT):
        sub.gfe_message_count += 1

    # ── CONTINUATION PAYWALL ──
    # If they already hit the gate and haven't paid, complete silence.
    # No response, no reminders. The absence creates the pressure.
    if sub.gfe_continuation_pending:
        logger.info("GFE continuation pending for %s (msg_count=%d) — silent until payment",
                     sub.sub_id, sub.gfe_message_count)
        return []

    # Check if we've hit a continuation gate (every 30 messages)
    if (sub.gfe_message_count > 0
            and sub.gfe_message_count % _GFE_CONTINUATION_INTERVAL == 0):
        logger.info("GFE continuation gate hit for %s at message %d", sub.sub_id, sub.gfe_message_count)
        sub.gfe_continuation_pending = True
        return await _build_continuation_actions(sub, avatar, context, emotion_analysis)

    # Generate response via GFE Agent
    gfe_output = await generate_gfe_response(
        message=message,
        avatar=avatar,
        sub=sub,
        context=context,
        emotion_analysis=emotion_analysis,
    )

    messages_list = gfe_output.get("messages", [])
    if not messages_list:
        messages_list = [{"text": "hmm 😏 what were you saying?", "delay_seconds": 8}]

    # Apply guardrails (QUALIFYING mode — no explicit, no selling)
    guardrail_passed = []
    fan_word_count = len(message.split())
    gfe_avatar_id = avatar.persona.ig_account_tag if avatar and avatar.persona else ""
    for msg in messages_list:
        text = msg.get("text", "")
        if not text:
            continue
        clean = post_process_stateful(
            text, GuardrailMode.QUALIFYING, None,
            fan_word_count=fan_word_count,
            tier_level=0,
            avatar_id=gfe_avatar_id,
        )
        if clean:
            guardrail_passed.append({"text": clean, "delay_seconds": msg.get("delay_seconds", 8)})
        else:
            # Guardrails rejected — use original text (GFE shouldn't have selling lang)
            guardrail_passed.append(msg)

    if not guardrail_passed:
        guardrail_passed = [{"text": "hmm 😏 what were you saying?", "delay_seconds": 8}]

    # Quality Validator
    combined = " ".join(m["text"] for m in guardrail_passed if m.get("text"))
    mp = context.get("model_profile")
    persona_name = (mp.stage_name if mp and mp.stage_name else None) or (avatar.persona.name if avatar and avatar.persona else "the model")
    persona_loc = (mp.stated_location if mp and mp.stated_location else None) or (avatar.persona.location_story if avatar and avatar.persona else "Miami")

    is_valid, fix_instruction = await validate(
        response=combined,
        fan_message=message,
        conversation_history=context["conversation_history"],
        tiers_purchased=0,
        persona_location=persona_loc,
        persona_name=persona_name,
        avatar_id=gfe_avatar_id,
    )

    if not is_valid and fix_instruction:
        logger.info("GFE Validator rejected: %s — regenerating", fix_instruction[:80])
        regen_output = await generate_gfe_response(
            message=message,
            avatar=avatar,
            sub=sub,
            context=context,
            emotion_analysis=emotion_analysis,
        )
        regen_msgs = regen_output.get("messages", [])
        if regen_msgs:
            regen_passed = []
            for rm in regen_msgs:
                rt = rm.get("text", "")
                if not rt:
                    continue
                rc = post_process_stateful(rt, GuardrailMode.QUALIFYING, None,
                                           fan_word_count=fan_word_count, tier_level=0,
                                           avatar_id=gfe_avatar_id)
                if rc:
                    regen_passed.append({"text": rc, "delay_seconds": rm.get("delay_seconds", 8)})
            if regen_passed:
                guardrail_passed = regen_passed
                gfe_output = regen_output

    # ── Check consent ──
    if gfe_output.get("consent_given"):
        sub.sext_consent_given = True
        sub.state = SubState.WARMING
        logger.info("Sext consent given by sub %s — switching to selling pipeline", sub.sub_id)
    else:
        phase = gfe_output.get("phase", "building")
        if phase == "consent_ask":
            sub.state = SubState.SEXT_CONSENT
        elif sub.state not in (SubState.GFE_BUILDING, SubState.SEXT_CONSENT):
            sub.state = SubState.GFE_BUILDING

    # ── Build BotActions (messages only, NEVER PPV) ──
    actions = []
    for msg in guardrail_passed:
        text = msg.get("text", "")
        if text:
            actions.append(BotAction(
                action_type="send_message",
                message=text,
                delay_seconds=msg.get("delay_seconds", random.randint(5, 12)),
                metadata={"source": "gfe_agent"},
            ))

    # Track bot messages
    for action in actions:
        if action.message and action.action_type == "send_message":
            sub.add_message("bot", action.message)

    # Background: Memory extraction
    try:
        update_callback_references(sub, message)
        await memory_manager.maybe_extract_and_store(sub, message)
        for action in actions:
            if action.message and action.action_type == "send_message":
                await memory_manager.maybe_store_persona_facts(action.message)
    except Exception as e:
        logger.debug("GFE memory extraction error: %s", e)

    return actions


def _advance_state(sub: Subscriber, recommendation: str, ppv_info: Optional[dict]) -> None:
    """Update subscriber state based on strategist recommendation."""
    _REC_TO_STATE = {
        "qualify": SubState.QUALIFYING,
        "gfe_building": SubState.GFE_BUILDING,
        "consent_check": SubState.SEXT_CONSENT,
        "warm": SubState.WARMING,
        "build_tension": SubState.TENSION_BUILD,
        "drop_ppv": SubState.FIRST_PPV_SENT if not sub.spending.is_buyer else SubState.LOOPING,
        "post_purchase": SubState.LOOPING,
        "handle_objection": sub.state,  # Stay in current state
        "brokey_treatment": SubState.GFE_ACTIVE,
        "gfe": SubState.GFE_ACTIVE,
        "retention": SubState.RETENTION,
        "re_engagement": SubState.RE_ENGAGEMENT,
        "pending_ppv": sub.state,  # Stay in current state
    }
    new_state = _REC_TO_STATE.get(recommendation)
    if new_state and new_state != sub.state:
        logger.info("State advanced: %s -> %s (recommendation=%s)", sub.state.value, new_state.value, recommendation)

        # Clear sent_captions after 2 completed sessions (transitions to RETENTION/GFE_ACTIVE)
        if new_state in (SubState.RETENTION, SubState.GFE_ACTIVE, SubState.POST_SESSION):
            caption_sessions = getattr(sub, '_caption_session_count', 0) + 1
            sub._caption_session_count = caption_sessions
            if caption_sessions >= 2:
                sub.sent_captions = []
                sub._caption_session_count = 0
                logger.info("Cleared sent_captions for %s after 2 completed sessions", sub.sub_id)

        # Clear sent_captions on new selling session start
        if new_state == SubState.WARMING and sub.state != SubState.WARMING:
            sub.sent_captions = []
            logger.info("New selling session — cleared sent_captions for %s", sub.sub_id)

        sub.state = new_state


def _build_actions(
    messages: list[dict],
    ppv_info: Optional[dict],
    sub: Subscriber,
) -> list[BotAction]:
    """
    Convert Director output to BotActions.

    Args:
        messages: List of {"text": str, "delay_seconds": int} dicts.
        ppv_info: Optional {"tier": int, "caption": str} dict.
        sub: Subscriber (for state tracking).

    Returns:
        List of BotActions.
    """
    actions = []

    for msg in messages:
        text = msg.get("text", "")
        if text:
            actions.append(BotAction(
                action_type="send_message",
                message=text,
                delay_seconds=msg.get("delay_seconds", random.randint(5, 12)),
                metadata={"source": "multi_agent"},
            ))

    # Add PPV action if directed by the strategist/director
    if ppv_info and ppv_info.get("tier"):
        # Enforce strict tier ordering — NEVER skip tiers
        # Use ppv_count (actual purchases) to determine next tier, not current_loop_number (sent count)
        tiers_purchased = sub.spending.ppv_count if sub.spending else 0
        expected_tier = min(tiers_purchased + 1, 6)
        tier_num = ppv_info["tier"]
        if tier_num != expected_tier:
            logger.warning("Tier ordering fix: Director wanted tier %d but expected tier %d (ppv_count=%d) — correcting",
                         tier_num, expected_tier, tiers_purchased)
            tier_num = expected_tier
        price = _TIER_PRICES.get(tier_num, 27.38)
        caption = ppv_info.get("caption", "just for you 😈")

        actions.append(BotAction(
            action_type="send_ppv",
            ppv_price=price,
            ppv_caption=caption,
            content_id="",  # Connector fills in from content_catalog
            message="",
            delay_seconds=random.randint(5, 15),
            metadata={
                "tier": f"tier_{tier_num}",
                "bundle_id": "",
                "source": "multi_agent",
            },
        ))

        # Track sent caption for dedup (never reuse same caption in a session)
        if caption and hasattr(sub, 'sent_captions'):
            if not sub.sent_captions:
                sub.sent_captions = []
            sub.sent_captions.append(caption)

        # NOTE: Do NOT advance current_loop_number here — only advance after PURCHASE
        # (process_purchase handles this via sub.record_purchase)
        sub.last_pitch_at = datetime.now()

        # State management
        if tier_num == 1 and not sub.spending.is_buyer:
            sub.state = SubState.FIRST_PPV_SENT
        else:
            sub.state = SubState.LOOPING

    return actions
