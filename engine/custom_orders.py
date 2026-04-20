"""
Massi-Bot — Custom Order Detection + Classification + State Machine

Custom orders are OUT OF BAND content that doesn't flow through the tier ladder.
They're specific, scenario-based requests ("video of you in a golf outfit")
that require upfront payment + 48h manual fulfillment.

State machine:
  pitched → awaiting_admin_confirm → paid → fulfilled
                                   → denied  (fan can retry)

This module:
  - Detects specific/scenario-based custom requests (vs generic buy signals)
  - Classifies the custom type (pic/video, lingerie/nude)
  - Quotes a price from the model's WILLS_AND_WONTS.md
  - Detects fan claims of payment ("sent it", "paid", etc.)

Does NOT handle: the Telegram alert fire, the two-click confirm, post-confirm
messaging. Those live in admin_bot + orchestrator.
"""

import re
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Custom request detection
# ─────────────────────────────────────────────

# Keywords indicating the fan wants something SPECIFIC (custom), not generic tier content.
# Generic "show me your tits" should go through the tier ladder. But "video of you in a
# golf outfit" is out-of-band — there's no tier for that, it has to be a custom.
_CUSTOM_REQUEST_PATTERNS = [
    # Outfit-specific
    r"\bin\s+(?:a|an|some)\s+(?:sexy|cute|hot)?\s*(?:golf|tennis|yoga|maid|nurse|schoolgirl|bunny|cop|cheerleader|gym|workout|business|lingerie|bikini|sundress|babydoll)",
    r"\bwearing\s+(?:a|an|some|my|your)\s+\w+",
    r"\bdressed\s+(?:as|in|like)\b",
    r"\bin\s+(?:my|your)\s+\w+\s+(?:outfit|clothes|set|fit)",
    # Scenario / action-specific
    r"\bvideo\s+of\s+you\s+\w+",
    r"\bpic\s+of\s+you\s+\w+",
    r"\bcan\s+you\s+(?:make|film|record|send|do)\s+(?:a|an|me)",
    r"\bcould\s+you\s+(?:make|film|record|send|do)\s+(?:a|an|me)",
    r"\bwould\s+you\s+(?:make|film|record|send|do)\s+(?:a|an|me)",
    r"\bsend\s+me\s+(?:a|an|something)\s+\w+",
    r"\bmake\s+me\s+(?:a|an|something)\s+\w+",
    r"\bsay\s+my\s+name",  # refused, but it's a custom-type request
    r"\bcall\s+me\s+\w+",
    # Voice notes
    r"\bvoice\s+note",
    r"\bvoice\s+message",
    r"\baudio\s+(?:of|message|clip)",
]
_CUSTOM_REQUEST_RE = re.compile("|".join(_CUSTOM_REQUEST_PATTERNS), flags=re.IGNORECASE)


def is_custom_request(message: str) -> bool:
    """Detect if fan's message is a specific custom request (not generic buy signal)."""
    if not message:
        return False
    return bool(_CUSTOM_REQUEST_RE.search(message))


# ─────────────────────────────────────────────
# Custom type classification + pricing
# Pricing source of truth: models/{model_name}/WILLS_AND_WONTS.md
#
# Classification was moved from rules to the LLM agent in 2026-04-20.
# The agent classifies `custom_type` semantically from the fan's request
# (e.g. "picture of you riding a dildo" → pic_nude, not pic_lingerie).
# The functions here now validate + price the agent's classification.
# The keyword classifier is retained as a last-resort safety net.
# ─────────────────────────────────────────────

# Canonical price table. Adding a new type? Also update:
#   * models/{model_name}/WILLS_AND_WONTS.md
#   * The agent's classify_custom_request tool description in single_agent.py
CUSTOM_PRICES: Dict[str, float] = {
    "pic_lingerie": 77.38,
    "pic_nude": 127.38,
    "video_lingerie": 127.38,
    "video_nude": 177.38,
    "voice_note": 47.38,
    "complex": 227.38,     # Weird / super-complex / longer videos — no ceiling but this is the floor
}

VALID_CUSTOM_TYPES = tuple(CUSTOM_PRICES.keys())

_VIDEO_KEYWORDS = ["video", "clip", "footage", "recording", "film"]
_PIC_KEYWORDS = ["pic", "picture", "photo", "image", "shot", "selfie"]
_NUDE_KEYWORDS = ["nude", "naked", "topless", "bottomless", "no clothes", "without clothes", "bare", "fully nude"]
_LINGERIE_KEYWORDS = ["lingerie", "bra", "panties", "thong", "underwear", "robe", "babydoll", "outfit", "dress", "bikini", "uniform", "clothed", "costume"]
_VOICE_KEYWORDS = ["voice note", "voice message", "voice clip", "audio note", "audio message"]


def price_for_type(custom_type: str, fallback_text: str = "") -> Tuple[str, float]:
    """
    Return (canonical_type, price_dollars) for a given custom_type.

    If `custom_type` is in VALID_CUSTOM_TYPES, returns it + its canonical price
    from the schedule. If it's unrecognised, falls back to the keyword classifier
    over `fallback_text` (safety net), then to ("video_nude", 177.38) as the
    premium default — we'd rather quote high and have the fan push back than
    quote low and leave money on the table for explicit content.
    """
    if custom_type and custom_type in CUSTOM_PRICES:
        return (custom_type, CUSTOM_PRICES[custom_type])
    # Fallback path
    if fallback_text:
        return _classify_custom_type_keywords(fallback_text)
    return ("video_nude", CUSTOM_PRICES["video_nude"])


def _classify_custom_type_keywords(message: str) -> Tuple[str, float]:
    """
    Last-resort keyword classifier. Kept for safety-net / backward compat only —
    the LLM agent is expected to classify semantically as the primary path
    (it can read "riding a dildo" as nude; this function cannot).
    """
    if not message:
        return ("video_nude", CUSTOM_PRICES["video_nude"])
    m = message.lower()

    if any(kw in m for kw in _VOICE_KEYWORDS):
        return ("voice_note", CUSTOM_PRICES["voice_note"])

    is_video = any(kw in m for kw in _VIDEO_KEYWORDS)
    is_pic = any(kw in m for kw in _PIC_KEYWORDS) and not is_video
    is_nude = any(kw in m for kw in _NUDE_KEYWORDS)

    if is_video:
        if is_nude:
            return ("video_nude", CUSTOM_PRICES["video_nude"])
        return ("video_lingerie", CUSTOM_PRICES["video_lingerie"])
    if is_pic:
        if is_nude:
            return ("pic_nude", CUSTOM_PRICES["pic_nude"])
        return ("pic_lingerie", CUSTOM_PRICES["pic_lingerie"])

    # Fan didn't specify medium — default to nude video (premium, usually right)
    return ("video_nude", CUSTOM_PRICES["video_nude"])


# Legacy shim — old callers still import this name; prefer price_for_type() for new code.
def classify_custom_type(message: str) -> Tuple[str, float]:
    return _classify_custom_type_keywords(message)


# ─────────────────────────────────────────────
# Fan-says-paid detection
# ─────────────────────────────────────────────

_PAID_CLAIM_PATTERNS = [
    r"\b(?:i\s+)?(?:just\s+)?paid\b",
    r"\bsent\s+it\b",
    r"\bsent\s+(?:the\s+)?(?:money|payment|it|ya)",
    r"\btipped\s+(?:you|ya)\b",
    r"\bdone\b(?!\s+with)",  # "done" but not "done with"
    r"\bcomplete[d]?\s+(?:the\s+)?(?:payment|tip)",
    r"\bcheck\s+(?:your|the)\s+(?:notifications|alerts|dms|messages)",
    r"\btransferred\b",
    r"\byou\s+should\s+see\s+(?:it|the|a)\s*(?:payment|tip)?",
]
_PAID_CLAIM_RE = re.compile("|".join(_PAID_CLAIM_PATTERNS), flags=re.IGNORECASE)


def is_payment_claim(message: str) -> bool:
    """Detect if fan's message claims they sent payment."""
    if not message:
        return False
    return bool(_PAID_CLAIM_RE.search(message))


# ─────────────────────────────────────────────
# Order state machine
# ─────────────────────────────────────────────

STATUS_PITCHED = "pitched"              # Bot quoted price, waiting for fan to decide
STATUS_AWAITING_ADMIN = "awaiting_admin_confirm"  # Fan claimed paid, waiting admin verify
STATUS_PAID = "paid"                    # Admin confirmed, fulfillment deadline clock starts
STATUS_DENIED = "denied"                # Admin denied — fan can retry
STATUS_FULFILLED = "fulfilled"          # Content delivered


def new_order(request_text: str, custom_type: str, price: float, platform: str = "") -> Dict:
    """Create a new pending_custom_order dict."""
    from datetime import datetime
    return {
        "request_text": request_text[:400],
        "custom_type": custom_type,
        "quoted_price": price,
        "platform": platform,
        "pitched_at": datetime.now().isoformat(),
        "fan_confirmed_paid_at": None,
        "admin_confirmed_at": None,
        "admin_last_alerted_at": None,
        "status": STATUS_PITCHED,
    }


def mark_fan_paid(order: Dict) -> Dict:
    """Fan claimed payment — update order, caller should fire admin alert."""
    from datetime import datetime
    order = dict(order)
    order["status"] = STATUS_AWAITING_ADMIN
    order["fan_confirmed_paid_at"] = datetime.now().isoformat()
    return order


def mark_admin_confirmed(order: Dict) -> Dict:
    """Admin confirmed payment via Telegram. Fulfillment deadline = now + 48h."""
    from datetime import datetime
    order = dict(order)
    order["status"] = STATUS_PAID
    order["admin_confirmed_at"] = datetime.now().isoformat()
    return order


def mark_admin_denied(order: Dict) -> Dict:
    """Admin denied payment via Telegram. Fan can retry."""
    from datetime import datetime
    order = dict(order)
    order["status"] = STATUS_DENIED
    order["admin_confirmed_at"] = datetime.now().isoformat()
    return order


def mark_fulfilled(order: Dict) -> Dict:
    """Admin delivered the custom content."""
    from datetime import datetime
    order = dict(order)
    order["status"] = STATUS_FULFILLED
    order["fulfilled_at"] = datetime.now().isoformat()
    return order
