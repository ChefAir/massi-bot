"""
Massi-Bot - OnlyFans Connector (OnlyFansAPI.com v2 webhook format)

FastAPI app (port 8001) that:
  1. Receives all OnlyFansAPI.com webhook events on a single endpoint
  2. Verifies HMAC-SHA256 signatures (Signature: <hex>)
  3. Dispatches on the "event" field in the payload
  4. Loads/saves subscriber state from Supabase
  5. Feeds events into the 5-agent orchestrator pipeline
  6. Executes BotActions with mandatory delays

Key difference from Fanvue:
  - Auth is a static API key (no OAuth flow needed)
  - Prices are in DOLLARS — pass through unchanged from engine output
  - Signature header is just "Signature: <hex>" (no timestamp prefix)
  - Single unified webhook endpoint, not per-event routes

Run with: uvicorn connector.of_connector:app --port 8001
"""

import os
import re
import sys
import hmac
import json
import random
import hashlib
import logging
import asyncio
from typing import Optional, Dict

import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.models import Subscriber, BotAction, SubState
from engine.avatars import AvatarConfig
from connector.init_helpers import load_avatars, build_attribution, get_avatar
from persistence.subscriber_store import (
    load_subscriber, create_subscriber, save_subscriber, record_transaction,
)
from persistence.content_store import get_bundle_by_id
from persistence.model_profile import load_model_profile
from agents.orchestrator import process_message as orchestrator_process_message
from agents.orchestrator import process_purchase as orchestrator_process_purchase
from agents.orchestrator import process_new_subscriber as orchestrator_process_new_subscriber
from admin_bot.alerts import alert_purchase, alert_whale_escalation

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ─────────────────────────────────────────────
# Sentry (optional — only initializes if SENTRY_DSN is set)
# ─────────────────────────────────────────────

_SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,
            environment=os.environ.get("ENVIRONMENT", "production"),
        )
        logger.info("Sentry initialized for of_connector")
    except Exception as _sentry_err:
        logger.warning("Sentry init failed: %s", _sentry_err)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

PLATFORM = "onlyfans"

# ─────────────────────────────────────────────
# Module state (replaces BotController)
# ─────────────────────────────────────────────

_avatars: Dict[str, AvatarConfig] = {}
_attribution = None  # Optional[AttributionEngine]
_model_id: Optional[str] = None
_model_profile = None  # Loaded from Supabase models table


def _get_model_id() -> str:
    model_id = os.environ.get("OF_MODEL_ID", "")
    if not model_id:
        raise RuntimeError("OF_MODEL_ID environment variable not set")
    return model_id


async def _check_whale_escalation(sub, platform: str) -> None:
    """U10: Fire tiered whale escalation alert if thresholds are crossed."""
    score = sub.whale_score
    total = sub.spending.total_spent
    highest = sub.spending.highest_single_purchase
    trigger = None
    if score >= 50:
        trigger = "score"
    elif highest >= 50:
        trigger = "single_purchase"
    elif total >= 150:
        trigger = "total_spent"
    if trigger:
        await alert_whale_escalation(
            platform=platform, username=sub.username, sub_id=sub.sub_id,
            whale_score=score, total_spent=total, highest_purchase=highest,
            trigger=trigger,
        )


# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────

app = FastAPI(title="Massi-Bot OnlyFans Connector", version="2.0.0", redirect_slashes=False)


@app.on_event("startup")
async def startup():
    global _model_id, _model_profile, _avatars, _attribution
    _model_id = os.environ.get("OF_MODEL_ID", "")
    _avatars = load_avatars()
    _attribution = build_attribution(
        os.environ.get("OF_IG_MAP", "{}"), _avatars
    )
    if _model_id:
        _model_profile = load_model_profile(_model_id)
    # Pre-warm sentence-transformer encoder (avoids 3s cold-start on first fan message)
    try:
        from llm.memory_store import prewarm_encoder
        prewarm_encoder()
    except Exception:
        pass
    logger.info("OnlyFans connector started (model_id=%s, profile=%s, avatars=%d)",
                _model_id, _model_profile.stage_name if _model_profile else "none", len(_avatars))


# ─────────────────────────────────────────────
# Signature verification
# ─────────────────────────────────────────────

def verify_signature(body: bytes, sig_header: str) -> None:
    """
    Verify OnlyFansAPI.com HMAC-SHA256 signature.
    Header: Signature: <hex-encoded-hmac-sha256-of-body>
    """
    if not sig_header:
        raise HTTPException(status_code=403, detail="Missing Signature header")

    secret = os.environ["OFAPI_WEBHOOK_SECRET"]
    expected = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig_header, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Strip HTML tags from OF message text."""
    return _HTML_TAG_RE.sub("", text).strip()


def _get_or_load_subscriber(
    platform_user_id: str,
    model_id: str,
    username: str = "",
    display_name: str = "",
) -> tuple[Subscriber, bool]:
    sub = load_subscriber(PLATFORM, platform_user_id, model_id)
    if sub is None:
        sub = create_subscriber(
            PLATFORM, platform_user_id, model_id,
            username=username, display_name=display_name,
        )
        return sub, True
    return sub, False


# ─────────────────────────────────────────────
# Outbound OnlyFans API calls
# ─────────────────────────────────────────────

def _of_api_base() -> str:
    account_id = os.environ["OFAPI_ACCOUNT_ID"]
    base = os.environ.get("OFAPI_BASE", "https://app.onlyfansapi.com")
    return f"{base}/api/{account_id}"


def _of_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['OFAPI_KEY']}",
        "Content-Type": "application/json",
    }


async def send_typing_indicator(chat_id: str) -> None:
    """Send 'typing...' indicator to a fan's chat. Lasts ~4 seconds per call. Free."""
    try:
        url = f"{_of_api_base()}/chats/{chat_id}/typing"
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, headers=_of_headers())
    except Exception:
        pass  # Best-effort — never crash on typing indicator failure


async def maintain_typing(chat_id: str, duration_seconds: float) -> None:
    """Keep typing indicator alive for a duration by re-sending every 3 seconds."""
    import time
    start = time.monotonic()
    while (time.monotonic() - start) < duration_seconds:
        await send_typing_indicator(chat_id)
        await asyncio.sleep(3)


async def send_of_message(chat_id: str, text: str) -> None:
    """Send a plain text message via OnlyFansAPI.com."""
    url = f"{_of_api_base()}/chats/{chat_id}/messages"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"text": text}, headers=_of_headers())
    if resp.status_code not in (200, 201):
        logger.error("OF send_message failed %d: %s", resp.status_code, resp.text[:200])
    else:
        logger.debug("Sent OF message to chat %s", chat_id)


async def send_of_ppv(
    chat_id: str,
    caption: str,
    of_media_id: str,
    price_dollars: float,
) -> None:
    """
    Send a PPV message via OnlyFansAPI.com.
    Price is in DOLLARS — do NOT multiply by 100 (opposite of Fanvue).
    """
    url = f"{_of_api_base()}/chats/{chat_id}/messages"
    payload = {
        "text": caption,
        "price": price_dollars,
        "mediaFiles": [of_media_id],
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, json=payload, headers=_of_headers())
    if resp.status_code not in (200, 201):
        logger.error(
            "OF send_ppv failed %d for chat %s: %s",
            resp.status_code, chat_id, resp.text[:200],
        )
    else:
        logger.info("Sent OF PPV $%.2f to chat %s", price_dollars, chat_id)


# ─────────────────────────────────────────────
# Action executor
# ─────────────────────────────────────────────

async def execute_actions(
    actions: list[BotAction],
    chat_id: str,
    model_id: str,
    sub: Subscriber,
) -> None:
    """Execute BotActions against the OnlyFans API. Price in dollars (pass-through)."""
    for action in actions:
        if action.delay_seconds > 0:
            # Show "typing..." during the mandatory delay
            if action.delay_seconds > 2:
                typing_task = asyncio.create_task(
                    maintain_typing(chat_id, action.delay_seconds - 1)
                )
                await asyncio.sleep(action.delay_seconds)
                typing_task.cancel()
            else:
                await asyncio.sleep(action.delay_seconds)

        if action.action_type == "send_message" and action.message:
            await send_of_message(chat_id, action.message)

        elif action.action_type == "send_ppv":
            bundle_info = None
            if action.content_id:
                bundle_info = get_bundle_by_id(action.content_id, model_id)

            of_media_id = (bundle_info or {}).get("of_media_id") or (bundle_info or {}).get("b2_key")

            if not of_media_id:
                logger.warning(
                    "No OF media ID for bundle %s — sending caption only",
                    action.content_id,
                )
                if action.ppv_caption:
                    await send_of_message(chat_id, action.ppv_caption)
            else:
                price_dollars = action.ppv_price or 0.0
                await send_of_ppv(chat_id, action.ppv_caption, of_media_id, price_dollars)

        elif action.action_type == "send_free" and action.message:
            await send_of_message(chat_id, action.message)

        elif action.action_type == "flag":
            logger.info("FLAG action for chat %s: %s", chat_id, action.metadata)


# ─────────────────────────────────────────────
# Event handlers (called as background tasks)
# ─────────────────────────────────────────────

async def _handle_message(payload: dict, model_id: str) -> None:
    """Handle messages.received — new inbound message from a fan."""
    from_user = payload.get("fromUser") or {}
    platform_user_id: str = str(from_user.get("id") or payload.get("user_id", ""))
    username: str = from_user.get("username", "")
    display_name: str = from_user.get("name", username)
    chat_id: str = platform_user_id
    raw_text: str = payload.get("text", "")
    message_text: str = strip_html(raw_text).strip()

    if not platform_user_id or not message_text:
        logger.debug("messages.received ignored: missing user_id or text")
        return

    try:
        sub, is_new = _get_or_load_subscriber(
            platform_user_id, model_id,
            username=username, display_name=display_name,
        )

        # Start typing indicator while agents process ("reading" pause + typing)
        await asyncio.sleep(random.uniform(1.0, 2.0))  # Natural "reading" pause
        typing_task = asyncio.create_task(maintain_typing(chat_id, 20))

        try:
            if is_new:
                if _attribution and message_text:
                    attr_result = _attribution.detect(messages=[message_text])
                    if attr_result.detected:
                        sub.persona_id = attr_result.persona_id or ""
                        sub.source_ig_account = attr_result.ig_handle or ""
                        sub.source_detected = True
                        logger.info(
                            "Keyword attribution for new sub %s: persona=%s",
                            platform_user_id, sub.persona_id,
                        )
                avatar = get_avatar(_avatars, sub.persona_id)
                actions = await orchestrator_process_new_subscriber(sub, avatar, model_profile=_model_profile)
            else:
                avatar = get_avatar(_avatars, sub.persona_id)
                actions = await orchestrator_process_message(sub, message_text, avatar, model_profile=_model_profile)
        finally:
            typing_task.cancel()  # Stop typing when agents are done

        save_subscriber(sub, PLATFORM, platform_user_id, model_id)
        await execute_actions(actions, chat_id, model_id, sub)
    except Exception as exc:
        logger.exception("Error handling messages.received from %s: %s", platform_user_id, exc)


async def _handle_new_subscriber(payload: dict, model_id: str) -> None:
    """Handle subscriptions.new — a fan just subscribed."""
    platform_user_id: str = str(payload.get("user_id", ""))
    replace_pairs: dict = payload.get("replacePairs", {})
    link_html: str = replace_pairs.get("{SUBSCRIBER_LINK}", "")
    username_match = re.search(r'onlyfans\.com/([^"\'>/]+)', link_html)
    username: str = username_match.group(1) if username_match else ""
    chat_id: str = platform_user_id

    if not platform_user_id:
        logger.warning("subscriptions.new: missing user_id in payload")
        return

    try:
        sub = create_subscriber(
            PLATFORM, platform_user_id, model_id,
            username=username, display_name=username,
        )
        avatar = get_avatar(_avatars, sub.persona_id)
        actions = await orchestrator_process_new_subscriber(sub, avatar, model_profile=_model_profile)
        save_subscriber(sub, PLATFORM, platform_user_id, model_id)
        await execute_actions(actions, chat_id, model_id, sub)
    except Exception as exc:
        logger.exception("Error handling subscriptions.new %s: %s", platform_user_id, exc)


async def _handle_renewed(payload: dict, model_id: str) -> None:
    """Handle subscriptions.renewed — subscriber renewed."""
    platform_user_id: str = str(payload.get("user_id", ""))
    replace_pairs: dict = payload.get("replacePairs", {})
    price_str: str = replace_pairs.get("{PRICE}", "0").replace("$", "").replace(",", "")
    try:
        amount = float(price_str)
    except ValueError:
        amount = 0.0

    if not platform_user_id:
        return

    try:
        sub, _ = _get_or_load_subscriber(platform_user_id, model_id)
        record_transaction(sub.sub_id, model_id, "subscription", amount, PLATFORM)
        logger.info("OF renewal: %s $%.2f", platform_user_id, amount)
    except Exception as exc:
        logger.exception("Error handling subscriptions.renewed %s: %s", platform_user_id, exc)


async def _handle_ppv_unlocked(payload: dict, model_id: str) -> None:
    """Handle messages.ppv.unlocked — fan purchased a PPV message."""
    platform_user_id: str = str(payload.get("user_id", ""))
    replace_pairs: dict = payload.get("replacePairs", {})
    amount_str: str = replace_pairs.get("{AMOUNT}", "0").replace("$", "").replace(",", "")
    try:
        amount_dollars = float(amount_str)
    except ValueError:
        amount_dollars = 0.0

    if not platform_user_id:
        return

    try:
        sub, _ = _get_or_load_subscriber(platform_user_id, model_id)
        avatar = get_avatar(_avatars, sub.persona_id)

        actions = await orchestrator_process_purchase(sub, amount_dollars, avatar)

        save_subscriber(sub, PLATFORM, platform_user_id, model_id)
        record_transaction(sub.sub_id, model_id, "ppv", amount_dollars, PLATFORM)
        logger.info("OF PPV unlocked: %s $%.2f", platform_user_id, amount_dollars)
        await alert_purchase(PLATFORM, sub.username, amount_dollars)
        await _check_whale_escalation(sub, PLATFORM)

        if actions:
            await execute_actions(actions, platform_user_id, model_id, sub)
            save_subscriber(sub, PLATFORM, platform_user_id, model_id)
    except Exception as exc:
        logger.exception("Error handling messages.ppv.unlocked %s: %s", platform_user_id, exc)


async def _handle_transaction(payload: dict, model_id: str) -> None:
    """Handle transactions.new — any new revenue transaction."""
    tx_type: str = payload.get("type", "other")
    amount: float = float(payload.get("amount", 0.0))
    logger.info("OF transaction: type=%s amount=%.2f", tx_type, amount)


async def _handle_tip(payload: dict, model_id: str) -> None:
    """Handle tips.received — fan sent a tip."""
    platform_user_id: str = str(payload.get("user_id", ""))
    amount_gross: float = float(payload.get("amountGross", 0.0))

    if not platform_user_id:
        return

    try:
        sub, _ = _get_or_load_subscriber(platform_user_id, model_id)
        record_transaction(sub.sub_id, model_id, "tip", amount_gross, PLATFORM)
        logger.info("OF tip: %s $%.2f gross", platform_user_id, amount_gross)
    except Exception as exc:
        logger.exception("Error handling tips.received %s: %s", platform_user_id, exc)


# ─────────────────────────────────────────────
# Unified webhook endpoint
# ─────────────────────────────────────────────

@app.get("/webhook/of")
@app.get("/webhook/of/")
async def webhook_of_ping():
    """Endpoint reachability check."""
    return JSONResponse({"status": "ok"})


@app.post("/webhook/of")
@app.post("/webhook/of/")
async def webhook_of(request: Request, background_tasks: BackgroundTasks):
    """Single unified webhook endpoint for all OnlyFansAPI.com events."""
    body = await request.body()
    verify_signature(body, request.headers.get("Signature", ""))

    data = json.loads(body)
    event: str = data.get("event", "")
    account_id: str = data.get("account_id", "")
    payload: dict = data.get("payload", {})

    try:
        model_id = _get_model_id()
    except RuntimeError as exc:
        logger.error("Cannot dispatch event %s: %s", event, exc)
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=500)

    if event == "messages.received":
        background_tasks.add_task(_handle_message, payload, model_id)
    elif event == "messages.ppv.unlocked":
        background_tasks.add_task(_handle_ppv_unlocked, payload, model_id)
    elif event == "subscriptions.new":
        background_tasks.add_task(_handle_new_subscriber, payload, model_id)
    elif event == "subscriptions.renewed":
        background_tasks.add_task(_handle_renewed, payload, model_id)
    elif event == "transactions.new":
        background_tasks.add_task(_handle_transaction, payload, model_id)
    elif event == "tips.received":
        background_tasks.add_task(_handle_tip, payload, model_id)
    elif event.startswith("accounts."):
        logger.info("OF account event: %s (account_id=%s)", event, account_id)
    else:
        logger.debug("Unhandled OF event: %s", event)

    return JSONResponse({"status": "ok"})


# ─────────────────────────────────────────────
# Health + status
# ─────────────────────────────────────────────

@app.get("/health")
async def health():
    return JSONResponse({
        "status": "ok",
        "platform": "onlyfans",
        "engine_ready": bool(_avatars),
        "model_id": _model_id or "not_set",
    })


@app.get("/")
async def root():
    return JSONResponse({"service": "Massi-Bot OnlyFans Connector", "version": "2.0.0"})
