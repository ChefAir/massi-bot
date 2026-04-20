"""
Massi-Bot Admin Bot — Custom Payment Confirmation Handler

Integrates with the MANAGER bot's python-telegram-bot Application via a
CallbackQueryHandler. (We originally planned to use the notify bot but it's
already being polled by telegram_chat.py for Claude Code bridge messages —
can't have two pollers on the same bot.)

Flow:
  1. Fan claims payment on a pitched custom → orchestrator fires alert_custom_payment_claim
  2. Manager bot sends message to admin with inline [Confirm] / [Deny] buttons
  3. Admin clicks once → button text changes to "Click again to commit (10s)"
  4. Admin clicks again within 10s → confirm/deny commits
  5. Bot sends fan appropriate message, updates sub.pending_custom_order.status
  6. Re-alert sweep resends alerts stuck 2h+ without admin action

Callback data format: "custom:{confirm|deny}:{sub_id_prefix}:{first|second}"
"""

import os
import sys
import time
import asyncio
import logging
from typing import Dict, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes

from persistence.supabase_client import get_client
from persistence.subscriber_store import load_subscriber, save_subscriber
from engine.custom_orders import (
    mark_admin_confirmed,
    mark_admin_denied,
    STATUS_AWAITING_ADMIN,
    STATUS_PAID,
    STATUS_DENIED,
)

logger = logging.getLogger(__name__)

# Maps callback state key → timestamp of first click
_first_click_state: Dict[str, float] = {}
_DOUBLE_CLICK_WINDOW_SECONDS = 10


# ─────────────────────────────────────────────
# Helpers: find sub, send fan message
# ─────────────────────────────────────────────

def _find_sub_by_id_prefix(sub_id_prefix: str) -> Optional[Tuple]:
    """Find subscriber by sub_id prefix. Returns (sub, platform, platform_user_id, model_id) or None."""
    try:
        db = get_client()
        result = db.table("subscribers").select(
            "id, platform, platform_user_id, model_id"
        ).execute()
        for row in (result.data or []):
            if str(row.get("id", "")).startswith(sub_id_prefix):
                platform = row.get("platform", "")
                pu_id = row.get("platform_user_id", "")
                model_id = row.get("model_id", "")
                sub = load_subscriber(platform, pu_id, model_id)
                if sub:
                    return (sub, platform, pu_id, model_id)
    except Exception as e:
        logger.warning("find_sub_by_id_prefix failed: %s", e)
    return None


async def _send_fan_message(platform: str, platform_user_id: str, model_id: str, text: str) -> None:
    """
    Send a message to the fan directly via platform API.
    Uses Redis tokens (Fanvue) or env-var API key (OF) — works from any container.
    """
    import httpx
    try:
        if platform == "onlyfans":
            account_id = os.environ.get("OFAPI_ACCOUNT_ID", "")
            api_key = os.environ.get("OFAPI_KEY", "")
            base = os.environ.get("OFAPI_BASE", "https://app.onlyfansapi.com")
            if account_id and api_key:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"{base}/api/{account_id}/chats/{platform_user_id}/messages",
                        json={"text": text},
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    )
                    if resp.status_code in (200, 201):
                        logger.info("Fan message sent on OF to %s", platform_user_id)
                    else:
                        logger.warning("OF send failed %d: %s", resp.status_code, resp.text[:100])

        elif platform == "fanvue":
            import redis, json as _json
            # Get creator_uuid from Supabase models table (column is fanvue_creator_uuid)
            db = get_client()
            r = db.table("models").select("fanvue_creator_uuid").eq("id", model_id).limit(1).execute()
            creator_uuid = ""
            if r.data:
                creator_uuid = r.data[0].get("fanvue_creator_uuid", "")
            if not creator_uuid:
                logger.warning("No fanvue_creator_uuid found for model %s", model_id)
                return

            # Get OAuth token from Redis
            redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
            red = redis.from_url(redis_url, decode_responses=True)
            raw = red.get(f"fanvue:tokens:{creator_uuid}")
            if not raw:
                logger.warning("No Fanvue token for creator %s", creator_uuid)
                return
            token = _json.loads(raw)["access_token"]

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://api.fanvue.com/chats/{platform_user_id}/message",
                    json={"text": text},
                    headers={"Authorization": f"Bearer {token}", "X-Fanvue-API-Version": "2025-06-26"},
                )
                if resp.status_code in (200, 201):
                    logger.info("Fan message sent on Fanvue to %s", platform_user_id)
                else:
                    logger.warning("Fanvue send failed %d: %s", resp.status_code, resp.text[:100])
    except Exception as e:
        logger.warning("Failed to send fan message on %s: %s", platform, e)


# ─────────────────────────────────────────────
# Commit confirm / deny
# ─────────────────────────────────────────────

async def _commit_confirm(sub_id_prefix: str) -> Tuple[bool, str]:
    found = _find_sub_by_id_prefix(sub_id_prefix)
    if not found:
        return False, f"sub not found for prefix {sub_id_prefix}"
    sub, platform, platform_user_id, model_id = found
    if not sub.pending_custom_order:
        return False, "no pending custom order"
    if sub.pending_custom_order.get("status") == STATUS_PAID:
        return False, "already confirmed"

    sub.pending_custom_order = mark_admin_confirmed(sub.pending_custom_order)
    save_subscriber(sub, platform, platform_user_id, model_id)

    msg = "got it baby, I see your payment come through. you'll have your custom delivered within 48 hours, gonna be so worth it for you."
    await _send_fan_message(platform, platform_user_id, model_id, msg)
    return True, f"confirmed (${sub.pending_custom_order.get('quoted_price', 0):.2f})"


async def _commit_deny(sub_id_prefix: str) -> Tuple[bool, str]:
    found = _find_sub_by_id_prefix(sub_id_prefix)
    if not found:
        return False, f"sub not found for prefix {sub_id_prefix}"
    sub, platform, platform_user_id, model_id = found
    if not sub.pending_custom_order:
        return False, "no pending custom order"

    sub.pending_custom_order = mark_admin_denied(sub.pending_custom_order)
    save_subscriber(sub, platform, platform_user_id, model_id)

    msg = "hmm i don't see the payment come through yet baby, can you double check on your end? I really want to do this for you, just need to see it first."
    await _send_fan_message(platform, platform_user_id, model_id, msg)
    return True, "denied"


# ─────────────────────────────────────────────
# CallbackQueryHandler (integrated with manager bot)
# ─────────────────────────────────────────────

async def custom_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle "custom:*" callback queries. Registered with the manager bot's Application.
    """
    query = update.callback_query
    if not query:
        return
    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 4 or parts[0] != "custom":
        await query.answer("unknown callback")
        return

    action = parts[1]       # confirm | deny
    sub_id_prefix = parts[2]
    click = parts[3]        # first | second

    if action not in ("confirm", "deny"):
        await query.answer("invalid action")
        return

    state_key = f"{action}:{sub_id_prefix}"
    current_text = (query.message.text or query.message.caption or "") if query.message else ""

    if click == "first":
        _first_click_state[state_key] = time.monotonic()
        logger.info("First click: action=%s sub=%s", action, sub_id_prefix)
        label_committing = f"⏳ Click again to {action} (10s)"
        other_action = "deny" if action == "confirm" else "confirm"
        other_label = "❌ Deny" if action == "confirm" else "✅ Confirm Paid"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(label_committing, callback_data=f"custom:{action}:{sub_id_prefix}:second"),
            InlineKeyboardButton(other_label, callback_data=f"custom:{other_action}:{sub_id_prefix}:first"),
        ]])
        await query.edit_message_text(
            text=current_text + f"\n\n<i>First click: {action}. Click again to commit.</i>",
            parse_mode="HTML",
            reply_markup=kb,
        )
        await query.answer(f"Click {action} again to commit")
        return

    if click == "second":
        first_time = _first_click_state.get(state_key)
        if not first_time:
            await query.answer("no first click — restart")
            return
        if time.monotonic() - first_time > _DOUBLE_CLICK_WINDOW_SECONDS:
            _first_click_state.pop(state_key, None)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Confirm Paid", callback_data=f"custom:confirm:{sub_id_prefix}:first"),
                InlineKeyboardButton("❌ Deny", callback_data=f"custom:deny:{sub_id_prefix}:first"),
            ]])
            await query.edit_message_text(
                text=current_text + "\n\n<i>Timed out. Click once to start again.</i>",
                parse_mode="HTML",
                reply_markup=kb,
            )
            await query.answer("timeout — click first again")
            return

        _first_click_state.pop(state_key, None)
        if action == "confirm":
            ok, detail = await _commit_confirm(sub_id_prefix)
            status_text = f"✅ CONFIRMED — {detail}" if ok else f"⚠️ Failed: {detail}"
        else:
            ok, detail = await _commit_deny(sub_id_prefix)
            status_text = f"❌ DENIED — {detail}" if ok else f"⚠️ Failed: {detail}"

        await query.edit_message_text(
            text=current_text + f"\n\n<b>{status_text}</b>",
            parse_mode="HTML",
            reply_markup=None,
        )
        await query.answer(status_text[:200])
        logger.info("Custom payment %s committed: %s", action, detail)


def get_callback_handler() -> CallbackQueryHandler:
    """Returns the handler to be registered on the manager bot's Application."""
    return CallbackQueryHandler(custom_callback_handler, pattern=r"^custom:")


# ─────────────────────────────────────────────
# Re-alert sweep — resend alerts if admin hasn't acted in 2h
# ─────────────────────────────────────────────

async def realert_sweep() -> None:
    """Scan for stuck custom orders and resend alerts."""
    from datetime import datetime, timedelta
    from admin_bot.alerts import alert_custom_payment_claim

    try:
        db = get_client()
        result = db.table("subscribers").select(
            "id, platform, platform_user_id, model_id, qualifying_data"
        ).execute()
        now = datetime.now()
        cutoff_2h_ago = now - timedelta(hours=2)
        resent_count = 0

        for row in (result.data or []):
            qd = row.get("qualifying_data") or {}
            order = qd.get("pending_custom_order")
            if not order or order.get("status") != STATUS_AWAITING_ADMIN:
                continue

            try:
                fan_paid_at_str = order.get("fan_confirmed_paid_at", "")
                if not fan_paid_at_str:
                    continue
                fan_paid_at = datetime.fromisoformat(fan_paid_at_str.replace("Z", "+00:00"))
                if fan_paid_at.tzinfo is not None:
                    fan_paid_at = fan_paid_at.replace(tzinfo=None)
                if fan_paid_at > cutoff_2h_ago:
                    continue

                last_alert_str = order.get("admin_last_alerted_at", "")
                if last_alert_str:
                    last_alert = datetime.fromisoformat(last_alert_str.replace("Z", "+00:00"))
                    if last_alert.tzinfo is not None:
                        last_alert = last_alert.replace(tzinfo=None)
                    if last_alert > cutoff_2h_ago:
                        continue
            except Exception:
                continue

            try:
                sub = load_subscriber(row["platform"], row["platform_user_id"], row["model_id"])
                if not sub:
                    continue
                await alert_custom_payment_claim(sub, order)
                order["admin_last_alerted_at"] = now.isoformat()
                sub.pending_custom_order = order
                save_subscriber(sub, row["platform"], row["platform_user_id"], row["model_id"])
                resent_count += 1
            except Exception as e:
                logger.warning("realert_sweep send failed: %s", e)

        if resent_count:
            logger.info("Custom payment re-alert sweep: resent %d alerts", resent_count)
    except Exception as e:
        logger.warning("realert_sweep error: %s", e)


async def realert_loop() -> None:
    """Run re-alert sweep every hour (configurable via CUSTOM_REALERT_INTERVAL_SECONDS)."""
    interval = int(os.environ.get("CUSTOM_REALERT_INTERVAL_SECONDS", "3600"))
    logger.info("Custom re-alert loop started (interval %ds)", interval)
    await asyncio.sleep(60)
    while True:
        try:
            await realert_sweep()
        except Exception as e:
            logger.exception("realert loop error: %s", e)
        await asyncio.sleep(interval)


def start_realert_task() -> asyncio.Task:
    return asyncio.create_task(realert_loop())
