"""
Massi-Bot Admin Bot - Alerts

Sends real-time Telegram alerts to the admin chat.
Uses direct HTTP calls to the Bot API so alerts work from any process
(connectors, engine, background tasks) without importing the full bot app.

Usage from any module:
    from admin_bot.alerts import alert_new_subscriber, alert_purchase, alert_error
    await alert_new_subscriber("fanvue", "john_doe", whale_score=72)
    await alert_purchase("fanvue", "john_doe", 77.35, tier=3)
    await alert_error("fanvue_connector", "Supabase timeout")
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)


def _admin_ids() -> list[int]:
    """Parse TELEGRAM_ADMIN_IDS env var (comma-separated)."""
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


def _bot_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _notify_bot_token() -> str:
    """Notify bot — separate from manager bot, used for time-sensitive alerts with buttons."""
    return os.environ.get("TELEGRAM_NOTIFY_BOT_TOKEN", "")


async def _send_with_buttons(text: str, reply_markup: dict = None) -> None:
    """
    Send a message via the MANAGER bot with inline keyboard buttons.
    Used for custom payment confirmations — the two-click confirm/deny flow.
    (NOTE: we originally planned to use the notify bot but telegram_chat.py listen
    is already polling it for Claude Code bridge messages. The manager bot already
    has callback_query handling via python-telegram-bot, so we use it instead.)
    """
    token = _bot_token()
    admin_ids = _admin_ids()
    if not admin_ids:
        logger.warning("No TELEGRAM_ADMIN_IDS configured — alert with buttons dropped")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in admin_ids:
            try:
                payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.warning("Manager bot send-with-buttons failed %d: %s", resp.status_code, resp.text[:100])
            except Exception as exc:
                logger.warning("Manager bot send-with-buttons exception: %s", exc)


async def _send(text: str, parse_mode: str = "HTML") -> None:
    """
    Send a message to all admin chat IDs via the Bot API.
    Silently logs on failure — alerts should never crash the caller.
    """
    token = _bot_token()
    admin_ids = _admin_ids()
    if not admin_ids:
        logger.warning("No TELEGRAM_ADMIN_IDS configured — alert dropped")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in admin_ids:
            try:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                })
                if resp.status_code != 200:
                    logger.warning("Alert send failed %d: %s", resp.status_code, resp.text[:100])
            except Exception as exc:
                logger.warning("Alert send exception: %s", exc)


# ─────────────────────────────────────────────
# Alert helpers
# ─────────────────────────────────────────────

async def alert_new_subscriber(
    platform: str,
    username: str,
    whale_score: int = 0,
    model_id: str = "",
) -> None:
    whale_tag = " 🐋 <b>HIGH WHALE SCORE</b>" if whale_score >= 50 else ""
    text = (
        f"🆕 <b>New Subscriber</b>{whale_tag}\n"
        f"Platform: {platform}\n"
        f"Username: @{username}\n"
        f"Whale score: {whale_score}/100"
    )
    await _send(text)


async def alert_whale_detected(
    platform: str,
    username: str,
    whale_score: int,
    sub_id: str = "",
) -> None:
    text = (
        f"🐋 <b>WHALE DETECTED</b>\n"
        f"Platform: {platform}\n"
        f"Username: @{username}\n"
        f"Score: {whale_score}/100\n"
        f"Sub ID: <code>{sub_id}</code>"
    )
    await _send(text)


async def alert_purchase(
    platform: str,
    username: str,
    amount: float,
    tier: int = 0,
    content_ref: str = "",
) -> None:
    tier_str = f" (Tier {tier})" if tier else ""
    text = (
        f"💰 <b>Purchase</b>\n"
        f"Platform: {platform}\n"
        f"Username: @{username}\n"
        f"Amount: <b>${amount:.2f}</b>{tier_str}"
    )
    await _send(text)


async def alert_tip(platform: str, username: str, amount: float) -> None:
    text = (
        f"💝 <b>Tip Received</b>\n"
        f"Platform: {platform}\n"
        f"Username: @{username}\n"
        f"Amount: <b>${amount:.2f}</b>"
    )
    await _send(text)


async def alert_error(context: str, error: str) -> None:
    text = (
        f"🚨 <b>Engine Error</b>\n"
        f"Context: <code>{context}</code>\n"
        f"Error: {error[:300]}"
    )
    await _send(text)


async def alert_engine_paused(paused_by: str = "admin") -> None:
    await _send(f"⏸ <b>Engine PAUSED</b> by {paused_by}")


async def alert_engine_resumed(resumed_by: str = "admin") -> None:
    await _send(f"▶️ <b>Engine RESUMED</b> by {resumed_by}")


async def alert_whale_escalation(
    platform: str,
    username: str,
    sub_id: str,
    whale_score: int,
    total_spent: float,
    highest_purchase: float,
    trigger: str,  # "score", "single_purchase", "total_spent"
) -> None:
    """
    U10: Three-level whale escalation alert.

    Levels:
      Emerging whale  — whale_score ≥ 50 OR single purchase ≥ $50
      High whale      — whale_score ≥ 70 OR single purchase ≥ $100
      Mega whale      — whale_score ≥ 90 OR total_spent ≥ $500

    Includes recommended action for Massimo:
      Emerging → let AI run, watch closely
      High     → review conversation, consider personal touch
      Mega     → take DM personally, offer custom content
    """
    if whale_score >= 90 or total_spent >= 500:
        level = "🐋🐋🐋 MEGA WHALE"
        action = "⚡ TAKE DM PERSONALLY — offer custom content + VIP treatment"
    elif whale_score >= 70 or highest_purchase >= 100:
        level = "🐋🐋 HIGH WHALE"
        action = "👀 REVIEW CONVERSATION — consider personal touch or custom pitch"
    else:
        level = "🐋 EMERGING WHALE"
        action = "✅ LET AI RUN — monitor closely, flag if score rises"

    trigger_labels = {
        "score": f"whale score hit {whale_score}/100",
        "single_purchase": f"single purchase of ${highest_purchase:.2f}",
        "total_spent": f"total spend reached ${total_spent:.2f}",
    }
    trigger_label = trigger_labels.get(trigger, trigger)

    text = (
        f"{level}\n"
        f"Platform: {platform} | @{username}\n"
        f"Sub ID: <code>{sub_id}</code>\n"
        f"Whale score: <b>{whale_score}/100</b>\n"
        f"Total spent: <b>${total_spent:.2f}</b>\n"
        f"Highest single purchase: <b>${highest_purchase:.2f}</b>\n"
        f"Trigger: {trigger_label}\n\n"
        f"{action}"
    )
    await _send(text)


async def alert_content_uploaded(
    model_id: str,
    session: int,
    tier: int,
    bundle_id: str,
) -> None:
    tier_prices = {1: 27.38, 2: 36.56, 3: 77.35, 4: 92.46, 5: 127.45, 6: 200.00}
    price = tier_prices.get(tier, 0)
    text = (
        f"📦 <b>Content Uploaded</b>\n"
        f"Session: {session} | Tier: {tier} (${price:.2f})\n"
        f"Bundle: <code>{bundle_id}</code>"
    )
    await _send(text)


async def alert_custom_payment_claim(sub, order: dict) -> None:
    """
    Fan claimed payment on a pitched custom order.
    Sends a message to the NOTIFY bot with inline keyboard buttons:
      [✅ CONFIRM PAID]  [❌ DENY]
    Each button requires DOUBLE-CLICK to commit (handled by the notify bot polling service).

    Callback data format: "custom:{confirm|deny}:{sub_id}:{first|second}"
    """
    # Platform isn't on the Subscriber dataclass — check the order dict first (we store it there),
    # then fall back to sub attribute (won't exist), then "unknown"
    platform = order.get("platform") or getattr(sub, "platform", "unknown") or "unknown"
    sub_id = getattr(sub, "sub_id", "?")
    username = getattr(sub, "username", "unknown") or "unknown"
    display_name = getattr(sub, "display_name", "") or ""
    request = order.get("request_text", "")[:160]
    custom_type = order.get("custom_type", "?")
    price = order.get("quoted_price", 0)
    pitched_at = order.get("pitched_at", "?")[:19]

    # Build fan identifier — show all available info so admin can find them
    fan_line = f"Fan: <b>{display_name}</b>" if display_name else "Fan:"
    if username and username != "unknown":
        fan_line += f" @{username}"
    fan_line += f" (<code>{sub_id[:12]}</code>)"

    text = (
        "⚠️ <b>CUSTOM PAYMENT CONFIRMATION NEEDED</b>\n"
        f"{fan_line}\n"
        f"Platform: <b>{platform}</b>\n"
        f"Type: {custom_type}\n"
        f"Quoted: <b>${price:.2f}</b>\n"
        f"Request: <i>\"{request}\"</i>\n"
        f"Pitched at: {pitched_at}\n\n"
        "Check the platform — did the payment actually land?\n"
        "Click twice to commit (prevents mis-clicks)."
    )
    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Confirm Paid", "callback_data": f"custom:confirm:{sub_id}:first"},
            {"text": "❌ Deny", "callback_data": f"custom:deny:{sub_id}:first"},
        ]]
    }
    await _send_with_buttons(text, reply_markup=reply_markup)
