"""
Massi-Bot Admin Bot — Bot Error Alerts

Rich per-error Telegram alerts for production bot errors. Separate from the
basic alert_error() in alerts.py — this is the one used by the connectors'
top-level exception handlers and logs enough detail for the user to spin up
a Claude Code session via Telegram bridge and push a fix.

Every error that prevents a fan-visible response:
  1. Appends a structured entry to logs/errors.jsonl (always — survives Telegram outages)
  2. Sends a formatted Telegram alert to TELEGRAM_ADMIN_IDS
  3. Dedups within a 5-minute window per (sub_id, operation, error_type)
  4. Repeat hits inside the dedup window become a "(+N more)" follow-up
"""

from __future__ import annotations

import os
import json
import time
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

_DEDUP_WINDOW_SECONDS = 300  # 5 min
_LOG_DIR = Path("/app/logs")
_LOG_FILE = _LOG_DIR / "errors.jsonl"

# Dedup cache: key -> (first_seen_ts, suppressed_count)
_dedup: Dict[str, tuple] = {}


def _admin_ids() -> list[int]:
    raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    out = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


def _bot_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _append_log(entry: Dict[str, Any]) -> None:
    """Append entry to logs/errors.jsonl. Best effort — never raises."""
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as e:
        logger.warning("Failed to append error log: %s", e)


async def _send_telegram(text: str) -> bool:
    token = _bot_token()
    admin_ids = _admin_ids()
    if not token or not admin_ids:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = False
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in admin_ids:
            try:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
                if resp.status_code == 200:
                    ok = True
                else:
                    logger.warning("Telegram error alert send failed %d: %s", resp.status_code, resp.text[:200])
            except Exception as exc:
                logger.warning("Telegram error alert exception: %s", exc)
    return ok


def _sub_identity(sub: Any) -> str:
    if sub is None:
        return "(no sub)"
    display = getattr(sub, "display_name", "") or ""
    username = getattr(sub, "username", "") or ""
    sub_id = getattr(sub, "sub_id", "") or ""
    parts = []
    if display:
        parts.append(display)
    if username:
        parts.append(f"@{username}")
    if sub_id:
        parts.append(f"({sub_id[:8]})")
    return " ".join(parts) if parts else "(unknown)"


def _dedup_key(sub_id: str, operation: str, err_type: str) -> str:
    return f"{sub_id}|{operation}|{err_type}"


async def alert_bot_error(
    operation: str,
    error: BaseException,
    *,
    sub: Any = None,
    platform: str = "",
    model: str = "",
    inbound_snippet: str = "",
    extra_context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Send a rich error alert and append to the local error log.

    Args:
        operation: Short name of the pipeline op that crashed
                   (handle_messages_received, handle_purchase, custom_payment,
                   media_reactor, recovery_sweep, etc.)
        error: The caught exception.
        sub: Subscriber object (optional — unknown at webhook signature stage)
        platform: "fanvue" or "onlyfans"
        model: Model stage name or UUID
        inbound_snippet: First ~200 chars of the fan input that triggered the crash
        extra_context: Free-form dict appended to both Telegram and log entry
    """
    now_iso = datetime.now().isoformat(timespec="seconds")
    err_type = type(error).__name__
    err_msg = str(error)[:500]
    tb_str = traceback.format_exc()
    # Keep top ~15 lines for Telegram
    tb_lines = tb_str.strip().split("\n")
    tb_snippet = "\n".join(tb_lines[-15:]) if tb_lines else ""

    sub_id = getattr(sub, "sub_id", "") if sub else ""
    identity = _sub_identity(sub)

    log_entry = {
        "ts": now_iso,
        "operation": operation,
        "platform": platform,
        "model": model,
        "sub_id": sub_id,
        "sub_identity": identity,
        "error_type": err_type,
        "error_msg": err_msg,
        "traceback": tb_str,
        "inbound_snippet": inbound_snippet,
        "extra": extra_context or {},
    }
    _append_log(log_entry)

    # Dedup window
    key = _dedup_key(sub_id, operation, err_type)
    now_mono = time.monotonic()
    prev = _dedup.get(key)
    if prev:
        first_seen, suppressed = prev
        if now_mono - first_seen < _DEDUP_WINDOW_SECONDS:
            _dedup[key] = (first_seen, suppressed + 1)
            logger.info("Error alert deduped (%s): +1 (total suppressed=%d)", key, suppressed + 1)
            return
    _dedup[key] = (now_mono, 0)

    # Build Telegram message
    lines = []
    lines.append("🚨 <b>BOT ERROR</b>")
    if platform or model:
        lines.append(f"Platform: <code>{_html_escape(platform)}</code>  Model: <code>{_html_escape(model)}</code>")
    lines.append(f"Fan: {_html_escape(identity)}")
    lines.append(f"Operation: <code>{_html_escape(operation)}</code>")
    lines.append(f"Time: <code>{_html_escape(now_iso)}</code>")
    lines.append(f"Error: <code>{_html_escape(_truncate(err_type + ': ' + err_msg, 400))}</code>")
    if inbound_snippet:
        lines.append("")
        lines.append(f"<b>Last inbound:</b>")
        lines.append(f"<code>{_html_escape(_truncate(inbound_snippet, 300))}</code>")
    if extra_context:
        lines.append("")
        lines.append(f"<b>Context:</b>")
        for k, v in extra_context.items():
            lines.append(f"  <code>{_html_escape(str(k))}</code>: {_html_escape(_truncate(str(v), 200))}")
    lines.append("")
    lines.append(f"<b>Traceback:</b>")
    lines.append(f"<pre>{_html_escape(_truncate(tb_snippet, 2500))}</pre>")

    text = "\n".join(lines)
    # Telegram hard limit is 4096 chars; trim tail if needed
    if len(text) > 4000:
        text = text[:3990] + "\n…[truncated]</pre>"

    await _send_telegram(text)


async def alert_bot_error_resolved(
    operation: str,
    *,
    sub: Any = None,
    platform: str = "",
    retries: int = 0,
    silence_duration_str: str = "",
) -> None:
    """Send a short 'recovered' notice after a successful recovery run."""
    identity = _sub_identity(sub)
    lines = [
        "✅ <b>BOT RECOVERED</b>",
        f"Platform: <code>{_html_escape(platform)}</code>",
        f"Fan: {_html_escape(identity)}",
        f"Operation: <code>{_html_escape(operation)}</code>",
    ]
    if silence_duration_str:
        lines.append(f"Silence duration: <code>{_html_escape(silence_duration_str)}</code>")
    if retries:
        lines.append(f"Recovery attempts: <code>{retries}</code>")
    await _send_telegram("\n".join(lines))
