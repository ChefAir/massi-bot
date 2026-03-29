"""
Massi-Bot Bot Engine - Attribution System
3-Layer subscriber source detection for one OF page with multiple IG accounts.

Detection Priority:
  1. TRACKING LINK — OF campaign/trial link tag (near 100% reliable)
  2. PROMO CODE — Discount code used at subscribe (high reliability)
  3. KEYWORD FALLBACK — Message content analysis (best-effort backup)

Setup:
  Each IG account gets:
    - A unique OF tracking/trial/campaign link in bio
    - A unique promo code promoted in stories/posts
    - A keyword profile for fallback detection

  When a sub arrives, the system checks in priority order until source is found.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from datetime import datetime

from models import Persona, NicheType, Subscriber


# ─────────────────────────────────────────────
# ATTRIBUTION CONFIG
# ─────────────────────────────────────────────

@dataclass
class IGAccountConfig:
    """
    Configuration for one Instagram account feeding into the OF page.
    Maps tracking links, promo codes, and keyword profiles to a persona.
    """
    # Identity
    ig_handle: str = ""                     # e.g. "@fitbabe_official"
    ig_display_name: str = ""               # e.g. "Fit Babe"
    persona_id: str = ""                    # Links to which Persona/script set

    # Layer 1: Tracking Links
    # OF allows creating campaign/trial links with unique identifiers.
    # Each IG bio gets a different link. The platform passes the campaign
    # tag when the sub arrives.
    tracking_link_tag: str = ""             # e.g. "fitbabe_ig" or "camp_fitness01"
    tracking_link_url: str = ""             # The full OF link for this IG bio
    trial_link_id: str = ""                 # If using trial links instead

    # Layer 2: Promo Codes
    # Each IG promotes a unique discount code. When sub uses it at checkout,
    # the code maps back to the source account.
    promo_codes: List[str] = field(default_factory=list)  # e.g. ["FITBABE", "FIT30"]
    promo_discount_percent: int = 30        # Discount offered

    # Layer 3: Keyword Profile (fallback)
    # Used when layers 1 and 2 fail (direct URL, shared link, etc.)
    niche_keywords: List[str] = field(default_factory=list)
    niche_topics: List[str] = field(default_factory=list)
    content_references: List[str] = field(default_factory=list)  # e.g. "gym video", "squat post"

    # Confidence tracking
    attribution_method: Optional[str] = None  # Set when detected: "tracking_link", "promo_code", "keyword"


@dataclass
class AttributionResult:
    """Result of an attribution attempt."""
    detected: bool = False
    persona_id: Optional[str] = None
    ig_handle: Optional[str] = None
    method: Optional[str] = None            # "tracking_link", "promo_code", "keyword"
    confidence: float = 0.0                 # 0.0 to 1.0
    details: str = ""                       # Human-readable explanation

    def __repr__(self):
        if self.detected:
            return (f"AttributionResult(detected=True, ig={self.ig_handle}, "
                    f"method={self.method}, confidence={self.confidence:.0%})")
        return "AttributionResult(detected=False)"


# ─────────────────────────────────────────────
# ATTRIBUTION ENGINE
# ─────────────────────────────────────────────

class AttributionEngine:
    """
    3-layer attribution system for detecting which IG account
    a subscriber came from on a single OF page.

    Usage:
        attr_engine = AttributionEngine(ig_configs)

        # Layer 1: Check at subscription time (from OF webhook/API)
        result = attr_engine.detect_from_tracking_link("fitbabe_ig")

        # Layer 2: Check promo code used at checkout
        result = attr_engine.detect_from_promo_code("FITBABE")

        # Layer 3: Analyze their first message(s)
        result = attr_engine.detect_from_message("your gym pics are fire")

        # Or run all layers in priority order:
        result = attr_engine.detect(
            tracking_tag="fitbabe_ig",       # from OF subscription data
            promo_code="FITBABE",            # from checkout data
            messages=["your gym pics are fire"]  # from chat
        )
    """

    def __init__(self, ig_configs: List[IGAccountConfig]):
        self.ig_configs = ig_configs

        # Build lookup indexes for fast matching
        self._tracking_link_index: Dict[str, IGAccountConfig] = {}
        self._promo_code_index: Dict[str, IGAccountConfig] = {}

        for config in ig_configs:
            # Index tracking links
            if config.tracking_link_tag:
                self._tracking_link_index[config.tracking_link_tag.lower()] = config
            if config.trial_link_id:
                self._tracking_link_index[config.trial_link_id.lower()] = config

            # Index promo codes
            for code in config.promo_codes:
                self._promo_code_index[code.upper()] = config

    # ═══════════════════════════════════════════
    # MAIN DETECTION METHOD (runs all layers)
    # ═══════════════════════════════════════════

    def detect(
        self,
        tracking_tag: Optional[str] = None,
        promo_code: Optional[str] = None,
        messages: Optional[List[str]] = None,
    ) -> AttributionResult:
        """
        Run all attribution layers in priority order.
        Returns as soon as a confident match is found.

        Args:
            tracking_tag: Campaign/trial link tag from OF subscription data
            promo_code: Discount code used at checkout
            messages: List of subscriber messages for keyword analysis
        """
        # ── Layer 1: Tracking Link (highest priority, ~100% reliable) ──
        if tracking_tag:
            result = self.detect_from_tracking_link(tracking_tag)
            if result.detected:
                return result

        # ── Layer 2: Promo Code (high reliability) ──
        if promo_code:
            result = self.detect_from_promo_code(promo_code)
            if result.detected:
                return result

        # ── Layer 3: Keyword Fallback (best-effort) ──
        if messages:
            combined_text = " ".join(messages)
            result = self.detect_from_message(combined_text)
            if result.detected:
                return result

        # Nothing detected
        return AttributionResult(
            detected=False,
            details="No attribution source detected from any layer"
        )

    # ═══════════════════════════════════════════
    # LAYER 1: TRACKING LINK DETECTION
    # ═══════════════════════════════════════════

    def detect_from_tracking_link(self, tracking_tag: str) -> AttributionResult:
        """
        Detect source from OF tracking/campaign/trial link tag.

        This is the most reliable method. When you create campaign links in OF,
        each link gets a unique identifier. Pass that identifier here.

        Example:
            IG bio has: onlyfans.com/model?campaign=fitbabe_ig
            tracking_tag = "fitbabe_ig"
        """
        tag_lower = tracking_tag.lower().strip()

        config = self._tracking_link_index.get(tag_lower)
        if config:
            return AttributionResult(
                detected=True,
                persona_id=config.persona_id,
                ig_handle=config.ig_handle,
                method="tracking_link",
                confidence=0.99,
                details=f"Matched tracking link tag '{tracking_tag}' → {config.ig_handle}"
            )

        # Partial match attempt (in case tag format varies slightly)
        for stored_tag, config in self._tracking_link_index.items():
            if stored_tag in tag_lower or tag_lower in stored_tag:
                return AttributionResult(
                    detected=True,
                    persona_id=config.persona_id,
                    ig_handle=config.ig_handle,
                    method="tracking_link",
                    confidence=0.90,
                    details=f"Partial match on tracking tag '{tracking_tag}' → {config.ig_handle}"
                )

        return AttributionResult(
            detected=False,
            details=f"No match for tracking tag '{tracking_tag}'"
        )

    # ═══════════════════════════════════════════
    # LAYER 2: PROMO CODE DETECTION
    # ═══════════════════════════════════════════

    def detect_from_promo_code(self, promo_code: str) -> AttributionResult:
        """
        Detect source from the discount/promo code used at checkout.

        Each IG account promotes a unique code:
            @fitbabe_official → "Use code FITBABE for 30% off"
            @gamergirl_xo → "Use code GAMERXO for 30% off"
        """
        code_upper = promo_code.upper().strip()

        config = self._promo_code_index.get(code_upper)
        if config:
            return AttributionResult(
                detected=True,
                persona_id=config.persona_id,
                ig_handle=config.ig_handle,
                method="promo_code",
                confidence=0.95,
                details=f"Matched promo code '{promo_code}' → {config.ig_handle}"
            )

        # Fuzzy match for typos (e.g., "FITBAB" instead of "FITBABE")
        for stored_code, config in self._promo_code_index.items():
            if (len(code_upper) >= 4 and
                (code_upper in stored_code or stored_code in code_upper)):
                return AttributionResult(
                    detected=True,
                    persona_id=config.persona_id,
                    ig_handle=config.ig_handle,
                    method="promo_code",
                    confidence=0.80,
                    details=f"Fuzzy match on promo code '{promo_code}' → {config.ig_handle}"
                )

        return AttributionResult(
            detected=False,
            details=f"No match for promo code '{promo_code}'"
        )

    # ═══════════════════════════════════════════
    # LAYER 3: KEYWORD FALLBACK DETECTION
    # ═══════════════════════════════════════════

    def detect_from_message(self, message: str) -> AttributionResult:
        """
        Detect source from message content analysis.
        This is the fallback when tracking links and promo codes aren't available.

        Scoring:
            - IG handle mentioned directly: +20 points
            - Content reference match: +4 points each
            - Niche topic match: +3 points each
            - Niche keyword match: +2 points each

        Only returns a match if score meets confidence threshold.
        """
        msg_lower = message.lower()
        scores: Dict[str, Tuple[int, IGAccountConfig]] = {}

        for config in self.ig_configs:
            score = 0

            # Direct IG handle mention (strongest signal)
            handle_clean = config.ig_handle.lower().replace("@", "")
            if handle_clean and handle_clean in msg_lower:
                score += 20

            # Display name mention
            if config.ig_display_name and config.ig_display_name.lower() in msg_lower:
                score += 10

            # Content references (e.g., "gym video", "squat post")
            for ref in config.content_references:
                if ref.lower() in msg_lower:
                    score += 4

            # Niche topics (e.g., "stream", "cosplay")
            for topic in config.niche_topics:
                if topic.lower() in msg_lower:
                    score += 3

            # Niche keywords (e.g., "gym", "workout", "gains")
            for keyword in config.niche_keywords:
                if keyword.lower() in msg_lower:
                    score += 2

            if score > 0:
                scores[config.persona_id] = (score, config)

        if not scores:
            return AttributionResult(
                detected=False,
                details="No keyword matches found in message"
            )

        # Get highest score
        best_id = max(scores, key=lambda k: scores[k][0])
        best_score, best_config = scores[best_id]

        # Check if there's a clear winner (not too close to second place)
        sorted_scores = sorted(scores.values(), key=lambda x: x[0], reverse=True)
        if len(sorted_scores) >= 2:
            gap = sorted_scores[0][0] - sorted_scores[1][0]
            if gap < 3:
                # Too close to call — ambiguous
                return AttributionResult(
                    detected=False,
                    details=f"Ambiguous: top scores too close ({sorted_scores[0][0]} vs {sorted_scores[1][0]})"
                )

        # Confidence based on score
        if best_score >= 10:
            confidence = 0.85
        elif best_score >= 6:
            confidence = 0.70
        elif best_score >= 4:
            confidence = 0.55
        else:
            return AttributionResult(
                detected=False,
                details=f"Score too low ({best_score}) for confident attribution"
            )

        return AttributionResult(
            detected=True,
            persona_id=best_config.persona_id,
            ig_handle=best_config.ig_handle,
            method="keyword",
            confidence=confidence,
            details=f"Keyword analysis scored {best_score} for {best_config.ig_handle}"
        )

    # ═══════════════════════════════════════════
    # SUBSCRIBER INTEGRATION
    # ═══════════════════════════════════════════

    def attribute_subscriber(
        self,
        sub: Subscriber,
        tracking_tag: Optional[str] = None,
        promo_code: Optional[str] = None,
    ) -> AttributionResult:
        """
        Convenience method: attribute a subscriber and update their profile.

        Call this when:
          - A new subscriber arrives (with tracking_tag and/or promo_code from OF)
          - After receiving messages (for keyword fallback)
        """
        # Collect messages for keyword fallback
        messages = [
            m["content"] for m in sub.recent_messages
            if m["role"] == "sub"
        ] if sub.recent_messages else None

        result = self.detect(
            tracking_tag=tracking_tag,
            promo_code=promo_code,
            messages=messages,
        )

        if result.detected:
            sub.source_ig_account = result.ig_handle or ""
            sub.persona_id = result.persona_id or ""
            sub.source_detected = True

        return result

    # ═══════════════════════════════════════════
    # SETUP HELPERS
    # ═══════════════════════════════════════════

    def get_setup_guide(self) -> str:
        """
        Generate a setup guide showing what links/codes to put in each IG bio.
        """
        lines = [
            "=" * 60,
            "  IG ACCOUNT SETUP GUIDE",
            "  One OF page, multiple IG accounts",
            "=" * 60,
            "",
        ]

        for i, config in enumerate(self.ig_configs, 1):
            lines.append(f"── IG Account #{i}: {config.ig_handle} ──")
            lines.append(f"  Display Name: {config.ig_display_name}")
            lines.append(f"  Persona: {config.persona_id[:8]}...")
            lines.append(f"")
            lines.append(f"  📎 BIO LINK:")
            if config.tracking_link_url:
                lines.append(f"     {config.tracking_link_url}")
            else:
                lines.append(f"     Create OF campaign link with tag: '{config.tracking_link_tag}'")
                lines.append(f"     Example: onlyfans.com/yourpage?campaign={config.tracking_link_tag}")
            lines.append(f"")
            lines.append(f"  🏷️  PROMO CODES (promote in stories/posts):")
            for code in config.promo_codes:
                lines.append(f"     \"Use code {code} for {config.promo_discount_percent}% off!\"")
            lines.append(f"")
            lines.append(f"  🔑 KEYWORD PROFILE (auto-detected from chat):")
            lines.append(f"     Keywords: {', '.join(config.niche_keywords[:8])}...")
            lines.append(f"     Topics: {', '.join(config.niche_topics[:5])}")
            lines.append(f"")
            lines.append(f"  {'─' * 50}")
            lines.append(f"")

        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """Get attribution system stats."""
        return {
            "total_ig_accounts": len(self.ig_configs),
            "total_tracking_links": len(self._tracking_link_index),
            "total_promo_codes": len(self._promo_code_index),
            "accounts": [
                {
                    "ig_handle": c.ig_handle,
                    "tracking_tag": c.tracking_link_tag,
                    "promo_codes": c.promo_codes,
                    "keyword_count": len(c.niche_keywords),
                }
                for c in self.ig_configs
            ],
        }


# ─────────────────────────────────────────────
# FACTORY: Build configs from personas
# ─────────────────────────────────────────────

def build_attribution_configs(
    ig_account_map: Dict[str, Dict]
) -> List[IGAccountConfig]:
    """
    Build IG account configs from a simple map.

    Args:
        ig_account_map: {
            "@fitbabe_official": {
                "persona_id": "abc123",
                "display_name": "Fit Babe",
                "tracking_tag": "fitbabe_ig",
                "promo_codes": ["FITBABE", "FIT30"],
                "niche": NicheType.FITNESS,
            },
            ...
        }
    """
    # Default keyword profiles per niche
    NICHE_DEFAULTS = {
        NicheType.FITNESS: {
            "keywords": ["gym", "workout", "fit", "gains", "muscles", "abs",
                         "squat", "yoga", "protein", "lifting", "athletic",
                         "sweaty", "toned", "exercise", "cardio", "glutes"],
            "topics": ["gym selfie", "workout video", "fitness post",
                       "gym pic", "booty gains", "leg day"],
            "content_refs": ["gym video", "workout post", "fitness content",
                           "squat video", "gym selfie", "exercise clip"],
        },
        NicheType.GAMER: {
            "keywords": ["game", "gaming", "stream", "twitch", "valorant",
                         "fortnite", "cod", "apex", "minecraft", "discord",
                         "controller", "headset", "pc", "console", "anime"],
            "topics": ["stream", "gaming clip", "gamer girl", "cosplay",
                       "gaming setup", "twitch stream", "discord server"],
            "content_refs": ["stream clip", "gaming video", "cosplay pic",
                           "twitch clip", "gaming post"],
        },
        NicheType.EGIRL: {
            "keywords": ["aesthetic", "anime", "cosplay", "uwu", "kawaii",
                         "egirl", "alt", "goth", "emo", "e-girl", "weeb",
                         "manga", "catgirl", "pink", "alt girl"],
            "topics": ["cosplay", "anime post", "tiktok", "aesthetic",
                       "egirl content", "alt aesthetic"],
            "content_refs": ["cosplay photo", "anime tiktok", "aesthetic post",
                           "egirl video"],
        },
        NicheType.GIRL_NEXT_DOOR: {
            "keywords": ["cute", "sweet", "pretty", "smile", "eyes", "natural",
                         "wholesome", "genuine", "real", "beautiful", "lovely",
                         "adorable", "nice", "girl next door"],
            "topics": ["selfie", "cute pic", "photo", "natural beauty",
                       "mirror selfie"],
            "content_refs": ["cute selfie", "mirror pic", "photo",
                           "your smile", "your eyes"],
        },
        NicheType.LATINA: {
            "keywords": ["mami", "papi", "chica", "bonita", "caliente",
                         "latina", "spanish", "reggaeton", "bachata",
                         "dancing", "spicy", "hot"],
            "topics": ["dancing video", "latina", "spanish post",
                       "reggaeton", "dance clip"],
            "content_refs": ["dance video", "latina content", "spanish post"],
        },
        NicheType.BADDIE: {
            "keywords": ["baddie", "slay", "queen", "boss", "luxe", "drip",
                         "vibe", "fire", "stunner", "designer", "nails",
                         "glam", "iconic", "that girl"],
            "topics": ["baddie post", "glam pic", "outfit", "fashion",
                       "luxury aesthetic"],
            "content_refs": ["outfit post", "glam video", "fashion content"],
        },
        NicheType.MILF: {
            "keywords": ["mature", "experienced", "woman", "cougar", "milf",
                         "older", "sophisticated", "classy", "elegant",
                         "wine", "lingerie", "real woman"],
            "topics": ["mature content", "real woman", "lingerie",
                       "sophisticated", "classy"],
            "content_refs": ["lingerie pic", "mature content", "classy photo"],
        },
    }

    configs = []
    for ig_handle, settings in ig_account_map.items():
        niche = settings.get("niche", NicheType.GIRL_NEXT_DOOR)
        defaults = NICHE_DEFAULTS.get(niche, NICHE_DEFAULTS[NicheType.GIRL_NEXT_DOOR])

        config = IGAccountConfig(
            ig_handle=ig_handle,
            ig_display_name=settings.get("display_name", ig_handle),
            persona_id=settings.get("persona_id", ""),
            tracking_link_tag=settings.get("tracking_tag", ""),
            tracking_link_url=settings.get("tracking_url", ""),
            trial_link_id=settings.get("trial_link_id", ""),
            promo_codes=settings.get("promo_codes", []),
            promo_discount_percent=settings.get("discount", 30),
            niche_keywords=settings.get("keywords", defaults["keywords"]),
            niche_topics=settings.get("topics", defaults["topics"]),
            content_references=settings.get("content_refs", defaults["content_refs"]),
        )
        configs.append(config)

    return configs
