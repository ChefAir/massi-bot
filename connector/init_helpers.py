"""
Massi-Bot - Connector Initialization Helpers

Lightweight functions that replace BotController for avatar loading
and IG attribution setup. Used by both Fanvue and OnlyFans connectors.

This removes the dependency on engine/controller.py (legacy state machine
orchestrator) while keeping access to avatars and attribution.
"""

import json
import logging
from typing import Dict, Optional

from engine.avatars import ALL_AVATARS, AvatarConfig
from engine.attribution import AttributionEngine, IGAccountConfig

logger = logging.getLogger(__name__)


def load_avatars() -> Dict[str, AvatarConfig]:
    """Load all 10 avatar configs directly from engine/avatars.py."""
    avatars = dict(ALL_AVATARS)
    logger.info("Loaded %d avatars: %s", len(avatars), list(avatars.keys()))
    return avatars


def build_attribution(
    ig_map_json: str,
    avatars: Dict[str, AvatarConfig],
) -> Optional[AttributionEngine]:
    """
    Build an AttributionEngine from an IG account map JSON string.

    ig_map_json: '{"@fitbabe_official": "girl_boss", ...}'

    Returns None if ig_map is empty or invalid.
    """
    try:
        ig_map: dict = json.loads(ig_map_json) if ig_map_json else {}
    except (json.JSONDecodeError, TypeError):
        logger.warning("Invalid IG map JSON — attribution disabled")
        return None

    if not ig_map:
        logger.info("No IG account map — attribution disabled")
        return None

    ig_configs = []
    for ig_handle, avatar_key in ig_map.items():
        if avatar_key not in avatars:
            logger.warning(
                "IG map references unknown avatar %s — skipping", avatar_key
            )
            continue

        avatar = avatars[avatar_key]
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

    if not ig_configs:
        logger.info("No valid IG configs built — attribution disabled")
        return None

    engine = AttributionEngine(ig_configs)
    logger.info("Attribution engine built with %d IG accounts", len(ig_configs))
    return engine


def get_avatar(
    avatars: Dict[str, AvatarConfig],
    persona_id: str,
) -> Optional[AvatarConfig]:
    """Look up an avatar by persona_id. Returns None if not found."""
    if not persona_id:
        return None
    return avatars.get(persona_id)
