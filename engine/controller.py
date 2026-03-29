"""
Massi-Bot Bot Engine - Master Controller v2
The single entry point that wires everything together.

This replaces the need to manually initialize individual components.
One controller manages:
  - Model profile & content catalog
  - Avatar personas & script library
  - 3-layer IG attribution
  - Conversation engine with 6-tier pricing
  - Subscriber tracking

Usage:
    controller = BotController()
    controller.setup_model(profile_data)
    controller.setup_avatars(ig_account_map)
    controller.load_content(content_pieces)

    # When a new sub arrives:
    actions = controller.handle_new_subscriber(sub_id, tracking_tag, promo_code)

    # When a sub sends a message:
    actions = controller.handle_message(sub_id, message_text)

    # When a sub purchases a PPV:
    controller.record_purchase(sub_id, bundle_id, amount)

    # Periodic re-engagement check:
    actions = controller.check_re_engagements()
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

from models import (
    Subscriber, SubState, SubType, SubTier, BotAction,
    Persona, NicheType
)
from avatars import AvatarConfig, ALL_AVATARS
from onboarding import (
    ModelProfile, ModelOnboarding, ContentCatalog, ContentBundle,
    ContentTier, TIER_CONFIG, get_tier_price, ContentAnalyzer
)
from attribution import (
    AttributionEngine, IGAccountConfig, build_attribution_configs
)
from engine_v2 import IntegratedEngine


class BotController:
    """
    Master controller that coordinates all subsystems.

    Architecture:
        BotController
        ├── ModelProfile (who the model is)
        ├── ContentCatalog (what content is available)
        ├── AttributionEngine (which IG account subs came from)
        ├── AvatarConfigs (10 psychological personas)
        ├── IntegratedEngine (conversation state machine)
        └── Subscribers (all tracked subscriber profiles)
    """

    def __init__(self):
        # Core components (initialized during setup)
        self.model: Optional[ModelProfile] = None
        self.catalog: Optional[ContentCatalog] = None
        self.attribution: Optional[AttributionEngine] = None
        self.engine: Optional[IntegratedEngine] = None
        self.onboarding: Optional[ModelOnboarding] = None

        # Avatar registry: avatar_key → AvatarConfig
        self.avatars: Dict[str, AvatarConfig] = {}

        # IG account → avatar_key mapping
        self.ig_to_avatar: Dict[str, str] = {}

        # Subscriber registry: sub_id → Subscriber
        self.subscribers: Dict[str, Subscriber] = {}

        # State
        self._is_setup = False

    # ═══════════════════════════════════════════
    # SETUP METHODS
    # ═══════════════════════════════════════════

    def setup_model(self, profile_data: Dict[str, Any]) -> ModelProfile:
        """
        Step 1: Set up the model profile.

        profile_data = {
            "stage_name": "Bella",
            "age": 23,
            "ethnicity": "latina",
            "skin_tone": "olive",
            "hair_color": "brunette",
            ...
        }
        """
        self.onboarding = ModelOnboarding()
        self.model = self.onboarding.create_profile(**profile_data)
        self.catalog = self.onboarding.get_catalog()
        return self.model

    def setup_avatars(
        self,
        ig_account_map: Dict[str, str],
        custom_avatars: Dict[str, AvatarConfig] = None
    ):
        """
        Step 2: Set up avatar personas and link them to IG accounts.

        ig_account_map = {
            "@fitbabe_official": "girl_boss",     # IG handle → avatar key
            "@gamergirl_xo": "sports_girl",
            "@sweet.nextdoor": "innocent",
            ...
        }

        Avatar keys: girl_boss, housewife, southern_belle, crypto_babe,
                     sports_girl, innocent, patriot, divorced_mom,
                     luxury_baddie, poker_girl
        """
        # Load base avatars
        self.avatars = dict(ALL_AVATARS)

        # Override with custom avatars if provided
        if custom_avatars:
            self.avatars.update(custom_avatars)

        # Build IG → avatar mapping
        self.ig_to_avatar = {}
        ig_configs = []

        for ig_handle, avatar_key in ig_account_map.items():
            if avatar_key not in self.avatars:
                raise ValueError(f"Unknown avatar key: {avatar_key}. "
                               f"Available: {list(self.avatars.keys())}")

            avatar = self.avatars[avatar_key]
            self.ig_to_avatar[ig_handle] = avatar_key

            # Update avatar's persona with the IG handle
            avatar.persona.ig_account_tag = ig_handle

            # Build attribution config
            # Generate tracking tag and promo codes from avatar key
            clean_handle = ig_handle.replace("@", "").replace(".", "_")
            ig_configs.append(IGAccountConfig(
                ig_handle=ig_handle,
                ig_display_name=avatar.persona.name,
                persona_id=avatar_key,
                tracking_link_tag=f"{clean_handle}_ig",
                promo_codes=[
                    clean_handle.upper()[:10],
                    f"{avatar_key.upper()[:6]}30",
                ],
                niche_keywords=avatar.persona.niche_keywords,
                niche_topics=avatar.persona.niche_topics,
                content_references=avatar.persona.niche_topics,
            ))

        # Initialize attribution engine
        self.attribution = AttributionEngine(ig_configs)

    def setup_engine(self):
        """
        Step 3: Initialize the integrated conversation engine.
        Must be called after setup_model and setup_avatars.
        """
        if not self.avatars:
            raise RuntimeError("Call setup_avatars() before setup_engine()")

        self.engine = IntegratedEngine(
            avatars=self.avatars,
            catalog=self.catalog,
            model_profile=self.model,
            attribution=self.attribution,
        )
        self._is_setup = True

    def full_setup(
        self,
        model_data: Dict[str, Any],
        ig_account_map: Dict[str, str],
    ):
        """
        Convenience method: run all setup steps at once.

        Usage:
            controller.full_setup(
                model_data={"stage_name": "Bella", "ethnicity": "latina", ...},
                ig_account_map={
                    "@fitbabe_official": "girl_boss",
                    "@gamergirl_xo": "sports_girl",
                    ...
                }
            )
        """
        self.setup_model(model_data)
        self.setup_avatars(ig_account_map)
        self.setup_engine()

    # ═══════════════════════════════════════════
    # CONTENT MANAGEMENT
    # ═══════════════════════════════════════════

    def add_content(
        self,
        file_path: str,
        content_type: str = "image",
        tags: Dict[str, Any] = None,
        tier: ContentTier = None,
    ):
        """Add a content piece to the catalog."""
        if not self.onboarding:
            raise RuntimeError("Call setup_model() first")
        return self.onboarding.add_content(file_path, content_type, tags, tier)

    def assemble_bundles(self) -> Dict[ContentTier, int]:
        """Assemble all content into PPV bundles."""
        if not self.onboarding:
            raise RuntimeError("Call setup_model() first")
        result = self.onboarding.assemble_all_bundles()
        self.catalog = self.onboarding.get_catalog()
        # Refresh engine's catalog reference
        if self.engine:
            self.engine.catalog = self.catalog
        return result

    def get_readiness(self) -> Dict:
        """Check if the system is ready to go live."""
        if not self.onboarding:
            return {"ready": False, "issues": ["Model not set up"]}
        report = self.onboarding.get_readiness_report()
        if not self.avatars:
            report["issues"].append("No avatars configured")
            report["ready"] = False
        if not self.ig_to_avatar:
            report["issues"].append("No IG accounts linked to avatars")
            report["ready"] = False
        return report

    # ═══════════════════════════════════════════
    # MESSAGE HANDLING (Main interface)
    # ═══════════════════════════════════════════

    def handle_new_subscriber(
        self,
        sub_id: str,
        username: str = "",
        tracking_tag: str = None,
        promo_code: str = None,
    ) -> List[BotAction]:
        """
        Handle a brand new subscriber arriving on the OF page.

        Args:
            sub_id: Unique subscriber identifier
            username: OF display name
            tracking_tag: Campaign link tag from OF (Layer 1 attribution)
            promo_code: Discount code used at checkout (Layer 2 attribution)

        Returns:
            List of BotActions to execute (welcome message, etc.)
        """
        self._ensure_setup()

        # Reuse existing subscriber if already injected by the connector
        # (preserves persona_id set by connector-level attribution)
        existing = self.subscribers.get(sub_id)
        if existing is not None:
            sub = existing
            # Update username if provided and not already set
            if username and sub.username == sub_id:
                sub.username = username
        else:
            sub = Subscriber(sub_id=sub_id, username=username or sub_id)
            self.subscribers[sub_id] = sub

        # Run attribution only if persona not already set by connector
        if not sub.source_detected and self.attribution:
            result = self.attribution.detect(
                tracking_tag=tracking_tag,
                promo_code=promo_code,
            )
            if result.detected:
                sub.source_ig_account = result.ig_handle or ""
                sub.persona_id = result.persona_id or ""
                sub.source_detected = True

        logger.info(
            "handle_new_subscriber: sub=%s persona_id=%r source_detected=%s",
            sub_id, sub.persona_id, sub.source_detected,
        )

        # Generate welcome message
        return self.engine.process_new_subscriber(sub)

    def handle_message(
        self,
        sub_id: str,
        message: str,
    ) -> List[BotAction]:
        """
        Handle an incoming message from a subscriber.

        Args:
            sub_id: Subscriber identifier
            message: The message text

        Returns:
            List of BotActions to execute
        """
        self._ensure_setup()

        sub = self._get_or_create_sub(sub_id)

        # If source not yet detected, try keyword fallback on this message
        if not sub.source_detected and self.attribution:
            result = self.attribution.detect(messages=[message])
            if result.detected:
                sub.source_ig_account = result.ig_handle or ""
                sub.persona_id = result.persona_id or ""
                sub.source_detected = True

        return self.engine.process_message(sub, message)

    def record_purchase(
        self,
        sub_id: str,
        amount: float,
        content_type: str = "ppv",
        bundle_id: str = None,
    ):
        """Record that a subscriber made a purchase."""
        sub = self._get_or_create_sub(sub_id)
        sub.record_purchase(amount, content_type)

        # Update bundle tracking
        if bundle_id and self.catalog:
            bundle = self.catalog.bundles.get(bundle_id)
            if bundle:
                bundle.times_purchased += 1
                bundle.times_sent += 1
                total = bundle.times_sent
                if total > 0:
                    bundle.conversion_rate = bundle.times_purchased / total

    def process_purchase(
        self,
        sub_id: str,
        amount: float,
        content_type: str = "ppv",
        bundle_id: str = None,
    ) -> List[BotAction]:
        """Handle an actual purchase event — returns post-purchase reaction + next PPV.

        Called by connectors on purchase webhooks and by the simulator on 'paid'.
        Delegates to engine.process_purchase() for state management and action generation.
        """
        self._ensure_setup()
        sub = self._get_or_create_sub(sub_id)

        # Update bundle tracking in catalog
        if bundle_id and self.catalog:
            bundle = self.catalog.bundles.get(bundle_id)
            if bundle:
                bundle.times_purchased += 1

        return self.engine.process_purchase(sub, amount, content_type)

    def record_ppv_rejected(self, sub_id: str):
        """Record that a subscriber saw but didn't purchase a PPV."""
        sub = self._get_or_create_sub(sub_id)
        sub.spending.rejected_ppv_count += 1

    # ═══════════════════════════════════════════
    # PROACTIVE OUTREACH
    # ═══════════════════════════════════════════

    def check_re_engagements(self) -> Dict[str, List[BotAction]]:
        """
        Check all subscribers for re-engagement opportunities.
        Call this periodically (e.g., every few hours).

        Returns:
            {sub_id: [BotAction, ...]} for each sub that needs outreach
        """
        self._ensure_setup()
        outreach = {}

        for sub_id, sub in self.subscribers.items():
            actions = self.engine.check_for_re_engagement(sub)
            if actions:
                outreach[sub_id] = actions

        return outreach

    # ═══════════════════════════════════════════
    # SUBSCRIBER MANAGEMENT
    # ═══════════════════════════════════════════

    def get_subscriber(self, sub_id: str) -> Optional[Subscriber]:
        """Get a subscriber profile."""
        return self.subscribers.get(sub_id)

    def get_all_subscribers(self) -> Dict[str, Subscriber]:
        """Get all subscriber profiles."""
        return self.subscribers

    def get_whales(self, min_score: int = 50) -> List[Subscriber]:
        """Get all subscribers with whale score above threshold."""
        return [
            sub for sub in self.subscribers.values()
            if sub.whale_score >= min_score
        ]

    def get_sub_summary(self, sub_id: str) -> Optional[Dict]:
        """Get a summary of a subscriber's profile and history."""
        sub = self.subscribers.get(sub_id)
        if not sub:
            return None
        return sub.to_dict()

    # ═══════════════════════════════════════════
    # ANALYTICS
    # ═══════════════════════════════════════════

    def get_analytics(self) -> Dict:
        """Get system-wide analytics."""
        total_subs = len(self.subscribers)
        total_revenue = sum(s.spending.total_spent for s in self.subscribers.values())
        buyers = [s for s in self.subscribers.values() if s.spending.is_buyer]
        whales = self.get_whales(50)

        # Per-avatar stats
        avatar_stats = {}
        for key in self.avatars:
            avatar_subs = [
                s for s in self.subscribers.values()
                if s.persona_id == key
            ]
            avatar_revenue = sum(s.spending.total_spent for s in avatar_subs)
            avatar_stats[key] = {
                "subscribers": len(avatar_subs),
                "revenue": avatar_revenue,
                "avg_revenue_per_sub": avatar_revenue / len(avatar_subs) if avatar_subs else 0,
            }

        # Per-tier stats
        tier_stats = {}
        if self.catalog:
            for tier in ContentTier:
                bundles = [
                    self.catalog.bundles[bid]
                    for bid in self.catalog.bundles_by_tier.get(tier, [])
                    if bid in self.catalog.bundles
                ]
                tier_stats[tier.value] = {
                    "bundles_available": len(bundles),
                    "times_sent": sum(b.times_sent for b in bundles),
                    "times_purchased": sum(b.times_purchased for b in bundles),
                    "revenue": sum(b.times_purchased * b.price for b in bundles),
                }

        return {
            "total_subscribers": total_subs,
            "total_buyers": len(buyers),
            "conversion_rate": len(buyers) / total_subs if total_subs > 0 else 0,
            "total_revenue": total_revenue,
            "avg_revenue_per_sub": total_revenue / total_subs if total_subs > 0 else 0,
            "avg_revenue_per_buyer": total_revenue / len(buyers) if buyers else 0,
            "whale_count": len(whales),
            "avatar_performance": avatar_stats,
            "tier_performance": tier_stats,
            "sub_type_distribution": {
                st.value: len([s for s in self.subscribers.values() if s.sub_type == st])
                for st in SubType
            },
        }

    # ═══════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════

    def _ensure_setup(self):
        """Verify the system is properly set up."""
        if not self._is_setup:
            raise RuntimeError(
                "Bot not set up. Call full_setup() or "
                "setup_model() + setup_avatars() + setup_engine() first."
            )

    def _get_or_create_sub(self, sub_id: str) -> Subscriber:
        """Get existing subscriber or create a new one."""
        if sub_id not in self.subscribers:
            sub = Subscriber(sub_id=sub_id, username=sub_id)
            self.subscribers[sub_id] = sub
        return self.subscribers[sub_id]
