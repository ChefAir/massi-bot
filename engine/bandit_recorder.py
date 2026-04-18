"""
Massi-Bot — Silent Bandit Outcome Recorder

Captures bot message outcomes for Thompson Sampling learning WITHOUT
touching the bot's response generation. Pure observation mode.

Pattern:
  1. After bot sends a message, record it as "pending" on the subscriber
  2. On the NEXT fan message, the pending message is marked "success" (fan responded)
  3. If no fan message within N hours, marked "failure" (fan went silent)

The bandit_selector.record_outcome() function already exists and writes to
the template_rewards table. This module just provides the wiring to call it
at the right time.

Silent observer — zero impact on bot behavior. The bandit learns in the
background for future analysis.
"""

import logging
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


def record_bot_message_sent(sub, message_text: str, state: str = "", tier: int = 0) -> None:
    """
    Record that the bot sent a message. Stores metadata on sub for
    outcome tracking on the next fan message.

    Called AFTER the bot sends a message in the orchestrator.
    """
    if not message_text or not message_text.strip():
        return

    sub._bandit_pending = {
        "text": message_text.strip()[:300],
        "state": state,
        "tier": tier,
        "sent_at": datetime.now().isoformat(),
    }


def record_fan_responded(sub, avatar_id: str = "") -> None:
    """
    Fan sent a message — the bot's previous message was a "success."
    Record the outcome and clear the pending state.

    Called at the TOP of process_message, before the agent runs.
    """
    pending = getattr(sub, "_bandit_pending", None)
    if not pending:
        return

    try:
        from engine.bandit_selector import record_outcome
        record_outcome(
            template_text=pending.get("text", ""),
            avatar_id=avatar_id,
            state=pending.get("state", ""),
            time_period=_get_time_period(),
            success=True,
        )
        logger.debug("Bandit: recorded success for msg=%s state=%s",
                      pending.get("text", "")[:40], pending.get("state", ""))
    except Exception as e:
        logger.debug("Bandit recording failed (non-fatal): %s", e)

    sub._bandit_pending = None


def _get_time_period() -> str:
    """Simple time bucketing: morning/afternoon/evening/night."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    return "night"
