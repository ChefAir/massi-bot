"""
Massi-Bot — PPV Auto-Cleanup Sweep

Background task run by both connectors. Every 10 minutes, scans all subscribers
with a pending unpaid PPV older than PPV_ABANDONMENT_HOURS (default 6) and:
  1. Deletes the PPV from the chat via platform API
  2. Clears sub.pending_ppv and sub.last_pitch_at
  3. Saves the subscriber

This lets fans re-enter fresh on next engagement — the abandoned tier drop
no longer clutters the chat and the Sales Strategist's "no re-drop" rule
won't block them forever.

Constraints by platform:
  - Fanvue: DELETE only works on UNPAID messages. No time limit.
  - OnlyFansAPI: DELETE has hard 24h window (platform-side limit).
    Our 6h default is well inside this window.

Paid PPVs are never pending (sub.pending_ppv is cleared on purchase).
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


def _abandonment_hours() -> float:
    """Configurable abandonment window. Default 6h."""
    try:
        return float(os.environ.get("PPV_ABANDONMENT_HOURS", "6"))
    except ValueError:
        return 6.0


def _sweep_interval_seconds() -> int:
    """How often to scan. Default 600 (10 min)."""
    try:
        return int(os.environ.get("PPV_SWEEP_INTERVAL_SECONDS", "600"))
    except ValueError:
        return 600


async def sweep_abandoned_ppvs(
    platform: str,
    delete_fn: Callable[..., Awaitable[bool]],
) -> int:
    """
    Scan all subscribers on this platform with pending_ppv older than threshold.
    Call delete_fn to remove from chat. Clear pending_ppv + last_pitch_at.

    delete_fn signature (platform-specific):
      - Fanvue: delete_fn(creator_uuid, user_uuid, message_uuid) -> bool
      - OnlyFans: delete_fn(chat_id, message_id) -> bool

    Returns: number of PPVs successfully cleaned up this sweep.
    """
    from persistence.supabase_client import get_client
    from persistence.subscriber_store import load_subscriber, save_subscriber

    threshold = _abandonment_hours()
    cutoff = datetime.now() - timedelta(hours=threshold)

    db = get_client()
    try:
        result = (
            db.table("subscribers")
            .select("id, platform, platform_user_id, model_id, qualifying_data")
            .eq("platform", platform)
            .not_.is_("qualifying_data->pending_ppv", "null")
            .execute()
        )
    except Exception as e:
        logger.warning("PPV sweep: query failed: %s", e)
        return 0

    rows = result.data or []
    cleaned = 0

    for row in rows:
        qd = row.get("qualifying_data") or {}
        pending = qd.get("pending_ppv")
        if not pending or not isinstance(pending, dict):
            continue

        sent_at_raw = pending.get("sent_at", "")
        try:
            sent_at = datetime.fromisoformat(sent_at_raw.replace("Z", "+00:00"))
            # Normalize to naive (our `datetime.now()` is naive)
            if sent_at.tzinfo is not None:
                sent_at = sent_at.replace(tzinfo=None)
        except Exception:
            logger.warning("PPV sweep: invalid sent_at %s — skipping", sent_at_raw)
            continue

        if sent_at >= cutoff:
            continue  # Not old enough yet

        platform_user_id = row.get("platform_user_id", "")
        model_id = row.get("model_id", "")
        msg_id = pending.get("platform_msg_id")

        if not msg_id:
            logger.debug("PPV sweep: no platform_msg_id — clearing anyway for %s", platform_user_id)
            deleted = False
        else:
            try:
                if platform == "fanvue":
                    creator_uuid = pending.get("creator_uuid", "")
                    deleted = await delete_fn(creator_uuid, platform_user_id, msg_id)
                else:  # onlyfans
                    deleted = await delete_fn(platform_user_id, msg_id)
            except Exception as e:
                logger.warning("PPV sweep: delete call failed for %s: %s", platform_user_id, e)
                deleted = False

        # Whether deletion succeeded or not, clear the pending state so we don't retry forever.
        # (If Fanvue delete failed because fan paid in the meantime, that's fine — clear and move on.)
        try:
            sub = load_subscriber(platform, platform_user_id, model_id)
            if sub and sub.pending_ppv:
                tier = sub.pending_ppv.get("tier")
                sub.pending_ppv = None
                # Also clear last_pitch_at so re-drops can resume naturally
                sub.last_pitch_at = None
                save_subscriber(sub, platform, platform_user_id, model_id)
                logger.info(
                    "PPV sweep [%s]: cleaned up tier=%s user=%s (deleted_from_chat=%s, age=%.1fh)",
                    platform, tier, platform_user_id, deleted,
                    (datetime.now() - sent_at).total_seconds() / 3600,
                )
                cleaned += 1
        except Exception as e:
            logger.warning("PPV sweep: save failed for %s: %s", platform_user_id, e)

    return cleaned


async def start_sweep_loop(
    platform: str,
    delete_fn: Callable[..., Awaitable[bool]],
) -> None:
    """
    Background loop that runs sweep_abandoned_ppvs every N seconds.
    Call with asyncio.create_task from connector startup.
    """
    interval = _sweep_interval_seconds()
    hours = _abandonment_hours()
    logger.info("PPV cleanup loop started [%s]: every %ds, threshold %sh",
                platform, interval, hours)
    # Small initial delay to let other startup complete
    await asyncio.sleep(30)
    while True:
        try:
            cleaned = await sweep_abandoned_ppvs(platform, delete_fn)
            if cleaned:
                logger.info("PPV sweep [%s]: cleaned %d abandoned PPV(s)", platform, cleaned)
        except Exception as e:
            logger.exception("PPV sweep loop error [%s]: %s", platform, e)
        await asyncio.sleep(interval)
