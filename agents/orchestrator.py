"""
Massi-Bot — Single-Agent Orchestrator

Thin wrapper around agents.single_agent for the connectors.
One Opus 4.7 call per fan message; code-level post-processing handles
guardrails, PPV injection, state advancement, and memory extraction.

Public entry points (called by connectors):
  - process_message(sub, message, avatar, model_profile) -> list[BotAction]
  - process_purchase(sub, amount, avatar, content_type, model_profile) -> list[BotAction]
  - process_new_subscriber(sub, avatar, model_profile) -> list[BotAction]
"""

import os
import sys
import random
import logging
import uuid
from typing import Optional
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from models import Subscriber, SubState, BotAction
from engine.bandit_recorder import record_bot_message_sent
from engine.high_value_memory import HVCategory, append_utterance

from agents.context_builder import build_context
from agents.single_agent import process_message as single_agent_process
from agents.parallel_guardrails import run_all_guardrails, build_corrective_hint

from llm.memory_extractor import update_callback_references
from llm.memory_manager import memory_manager

logger = logging.getLogger(__name__)

# Default tier pricing — override via WILLS_AND_WONTS.md or model profile.
# These are the defaults Massi-Bot ships with; Claude Code will ask the
# operator whether they want to keep or change them during setup.
_DEFAULT_TIER_PRICES = {
    1: 27.38, 2: 36.56, 3: 77.35,
    4: 92.46, 5: 127.45, 6: 200.00,
}

_GFE_CONTINUATION_PRICE = 20.00

# Cobalt-Strike jitter for PPV realness (heads-up -> PPV drop).
_PPV_JITTER_MIN_SECONDS = 108
_PPV_JITTER_MAX_SECONDS = 252


def _tier_prices(model_profile=None) -> dict:
    """Return the active tier price table. Per-model overrides via model_profile."""
    if model_profile and getattr(model_profile, "tier_prices", None):
        try:
            return {int(k): float(v) for k, v in model_profile.tier_prices.items()}
        except Exception:
            pass
    return dict(_DEFAULT_TIER_PRICES)


async def process_message(
    sub: Subscriber,
    message: str,
    avatar=None,
    model_profile=None,
    active_tier_count: Optional[int] = None,
) -> list[BotAction]:
    """
    Route an incoming fan message through the single agent.

    One Opus call with optional tool use (Grok uncensor, custom classifier,
    memory lookup, admin alert). Code-level post-processing enforces
    guardrails and injects PPV heads-up / jitter.
    """
    if not message or not message.strip():
        return []

    req_id = str(uuid.uuid4())[:8]
    logger.info("[%s] Processing message for sub %s: %s", req_id, sub.sub_id, message[:60])

    sub.add_message("sub", message)
    sub.message_count += 1

    try:
        context = await build_context(sub, message, avatar, model_profile=model_profile)
        context["request_id"] = req_id

        tier_count = active_tier_count
        if tier_count is None:
            tier_count = 6
            if model_profile and getattr(model_profile, "active_tier_count", None):
                tier_count = int(model_profile.active_tier_count)

        result = await single_agent_process(
            message=message,
            avatar=avatar,
            sub=sub,
            context=context,
            active_tier_count=tier_count,
        )

        messages_list = result.get("messages", []) or []
        ppv_info = result.get("ppv")
        consent_given = result.get("consent_given", False)

        if consent_given and not getattr(sub, "sext_consent_given", False):
            sub.sext_consent_given = True
            logger.info("[%s] Consent given by sub %s", req_id, sub.sub_id)

        # ── Parallel guardrails (8 concurrent checks, Cresta pattern) ──
        tiers_purchased = sub.spending.ppv_count if sub.spending else 0
        sext_consent = getattr(sub, "sext_consent_given", False)
        all_passed, reports = await run_all_guardrails(
            messages=messages_list,
            ppv_intent=ppv_info,
            sub=sub,
            avatar=avatar,
            tiers_purchased=tiers_purchased,
            sext_consent_given=sext_consent,
        )

        guardrail_passed: list[dict] = []
        if all_passed:
            for msg in messages_list:
                text = (msg.get("text") or "").strip()
                if text:
                    guardrail_passed.append({
                        "text": text,
                        "delay_seconds": msg.get("delay_seconds", random.randint(5, 12)),
                    })
        else:
            hint = build_corrective_hint([r for r in reports if not r.passed])
            logger.info("[%s] Guardrail rejection: %s", req_id, hint[:120])
            # Strip PPV intent if guardrails failed (safer to skip than to retry).
            ppv_info = None

        if not guardrail_passed and not ppv_info:
            guardrail_passed = [{"text": "hmm 😏 what were you saying?", "delay_seconds": 8}]

        # ── Build BotActions ──
        actions: list[BotAction] = []
        for msg in guardrail_passed:
            actions.append(BotAction(
                action_type="send_message",
                message=msg["text"],
                delay_seconds=msg["delay_seconds"],
                metadata={"source": "single_agent"},
            ))

        # ── PPV injection with heads-up + Cobalt jitter ──
        if ppv_info and ppv_info.get("tier"):
            prices = _tier_prices(model_profile)
            ppv_tier = ppv_info.get("tier")
            is_custom = str(ppv_tier).lower() == "custom"

            if is_custom:
                price = float(ppv_info.get("price", 0.0)) or 0.0
                caption = ppv_info.get("caption", "just for you")
                actions.append(BotAction(
                    action_type="send_ppv",
                    ppv_price=price,
                    ppv_caption=caption,
                    message="",
                    delay_seconds=random.randint(5, 15),
                    metadata={"tier": "custom", "source": "single_agent"},
                ))
            else:
                tier_num = int(ppv_tier)
                price = prices.get(tier_num, prices.get(1, 27.38))
                caption = ppv_info.get("caption", "just for you 😈")
                heads_up = ppv_info.get("heads_up", "")

                if heads_up:
                    actions.append(BotAction(
                        action_type="send_message",
                        message=heads_up,
                        delay_seconds=random.randint(4, 9),
                        metadata={"source": "single_agent", "ppv_heads_up": True},
                    ))
                    append_utterance(sub, HVCategory.PPV_HEADS_UP, heads_up)

                # Cobalt-Strike jitter between heads-up and PPV drop.
                ppv_delay = random.randint(_PPV_JITTER_MIN_SECONDS, _PPV_JITTER_MAX_SECONDS)
                actions.append(BotAction(
                    action_type="send_ppv",
                    ppv_price=price,
                    ppv_caption=caption,
                    message="",
                    delay_seconds=ppv_delay,
                    metadata={"tier": f"tier_{tier_num}", "source": "single_agent"},
                ))
                sub.last_pitch_at = datetime.now()

        # ── Track bot messages + bandit record ──
        for action in actions:
            if action.message and action.action_type == "send_message":
                sub.add_message("bot", action.message)
                try:
                    await record_bot_message_sent(sub, action.message)
                except Exception:
                    logger.debug("bandit record failed", exc_info=True)

        # ── Memory extraction (background-ish) ──
        try:
            update_callback_references(sub, message)
            await memory_manager.maybe_extract_and_store(sub, message)
            for action in actions:
                if action.message and action.action_type == "send_message":
                    await memory_manager.maybe_store_persona_facts(action.message)
        except Exception as exc:
            logger.debug("Memory extraction error: %s", exc)

        return actions

    except Exception as exc:
        logger.exception("Orchestrator error for sub %s: %s", sub.sub_id, exc)
        return [BotAction(
            action_type="send_message",
            message="hmm I got distracted for a sec 😂 what were you saying?",
            delay_seconds=random.randint(5, 12),
        )]


async def process_purchase(
    sub: Subscriber,
    amount: float,
    avatar=None,
    content_type: str = "ppv",
    model_profile=None,
    active_tier_count: Optional[int] = None,
) -> list[BotAction]:
    """
    Process a confirmed purchase event. Agent generates the post-purchase
    reaction + (if appropriate) next-tier lead-in. PPV injection is disabled
    here so the agent can't auto-pitch a new tier during payment confirmation.
    """
    sub.record_purchase(amount, content_type)

    # ANY purchase (tier PPV, custom, continuation, tip) resets the GFE
    # message counter so a fan who just spent money doesn't immediately hit
    # the continuation paywall again.
    sub.gfe_message_count = 0

    if content_type == "gfe_continuation" or (
        getattr(sub, "gfe_continuation_pending", False) and 15.0 <= amount <= 25.0
    ):
        sub.gfe_continuation_pending = False
        # Re-randomize the continuation threshold so the next cycle fires at
        # a different point (prevents deterministic "exactly 30 msgs" pattern).
        sub.continuation_threshold_jitter = random.randint(25, 35)

    try:
        context = await build_context(sub, "paid", avatar, model_profile=model_profile)
        tier_count = active_tier_count
        if tier_count is None:
            tier_count = 6
            if model_profile and getattr(model_profile, "active_tier_count", None):
                tier_count = int(model_profile.active_tier_count)

        result = await single_agent_process(
            message="paid",
            avatar=avatar,
            sub=sub,
            context=context,
            active_tier_count=tier_count,
        )

        actions: list[BotAction] = []
        for msg in (result.get("messages") or []):
            text = (msg.get("text") or "").strip()
            if text:
                actions.append(BotAction(
                    action_type="send_message",
                    message=text,
                    delay_seconds=msg.get("delay_seconds", random.randint(5, 12)),
                    metadata={"source": "single_agent", "context": "post_purchase"},
                ))

        for action in actions:
            if action.message:
                sub.add_message("bot", action.message)

        return actions

    except Exception as exc:
        logger.exception("Purchase orchestrator error for sub %s: %s", sub.sub_id, exc)
        return [BotAction(
            action_type="send_message",
            message="omg you actually opened it 😍",
            delay_seconds=random.randint(5, 12),
        )]


async def process_new_subscriber(
    sub: Subscriber,
    avatar=None,
    model_profile=None,
    active_tier_count: Optional[int] = None,
) -> list[BotAction]:
    """Welcome a brand-new subscriber. One short opener from the agent."""
    try:
        context = await build_context(sub, "", avatar, model_profile=model_profile)
        tier_count = active_tier_count
        if tier_count is None:
            tier_count = int(getattr(model_profile, "active_tier_count", 6) or 6)
        result = await single_agent_process(
            message="",
            avatar=avatar,
            sub=sub,
            context=context,
            active_tier_count=tier_count,
        )

        actions: list[BotAction] = []
        for msg in (result.get("messages") or []):
            text = (msg.get("text") or "").strip()
            if text:
                actions.append(BotAction(
                    action_type="send_message",
                    message=text,
                    delay_seconds=msg.get("delay_seconds", random.randint(5, 12)),
                    metadata={"source": "single_agent", "context": "welcome"},
                ))

        sub.state = SubState.WELCOME_SENT
        for action in actions:
            if action.message:
                sub.add_message("bot", action.message)
        return actions

    except Exception as exc:
        logger.exception("Welcome orchestrator error for sub %s: %s", sub.sub_id, exc)
        return [BotAction(
            action_type="send_message",
            message="hey 😏 what caught your eye?",
            delay_seconds=random.randint(5, 12),
        )]
