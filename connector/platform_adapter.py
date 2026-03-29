"""
Massi-Bot - Platform Adapter

Normalized event types and a common outbound interface that abstracts
Fanvue vs OnlyFans differences. Both connectors translate their
platform-specific payloads into these dataclasses before touching the engine.

Outbound platform actions are dispatched through PlatformSender, which the
connector initializes with its platform-specific send functions.
"""

from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable
from enum import Enum


# ─────────────────────────────────────────────
# Normalized inbound events (platform → engine)
# ─────────────────────────────────────────────

class EventType(Enum):
    NEW_SUBSCRIBER   = "new_subscriber"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_READ     = "message_read"
    PURCHASE         = "purchase"
    TIP              = "tip"
    UNSUBSCRIBED     = "unsubscribed"


@dataclass
class PlatformEvent:
    """
    Normalized event from any platform.
    The connector creates one of these from the raw webhook payload,
    then passes it to the engine dispatch layer.
    """
    event_type: EventType
    platform: str                     # "fanvue" or "onlyfans"
    platform_user_id: str             # Subscriber's platform-specific UUID
    model_id: str                     # Supabase models.id UUID

    # Message received
    message_text: Optional[str] = None

    # Purchase / tip
    amount_dollars: Optional[float] = None
    content_ref: Optional[str] = None    # bundle_id or PPV reference

    # Attribution hints (new subscriber)
    tracking_tag: Optional[str] = None
    promo_code: Optional[str] = None

    # Display info
    username: Optional[str] = None
    display_name: Optional[str] = None


# ─────────────────────────────────────────────
# Normalized outbound actions (engine → platform)
# ─────────────────────────────────────────────

SendMessageFn = Callable[[str, str], Awaitable[None]]
SendPPVFn = Callable[[str, str, str, int], Awaitable[None]]


@dataclass
class PlatformSender:
    """
    Holds the platform-specific send functions.
    Passed into the action executor so it works for both Fanvue and OF.

    send_message(platform_user_id, text) -> None
    send_ppv(platform_user_id, caption, media_ref, price_cents) -> None
    """
    platform: str
    send_message: SendMessageFn
    send_ppv: SendPPVFn
