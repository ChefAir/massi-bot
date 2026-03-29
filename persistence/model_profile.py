"""
Massi-Bot — Model Profile Loader

Loads a model's profile from Supabase and provides identity overrides
for the agent system. Model profiles override avatar defaults for
personal identity fields (name, location, age, appearance, boundaries).

Avatar provides: psychology, voice, selling style, themes
Model provides: name, location, age, appearance, boundaries, languages
"""

import logging
import time
from typing import Optional, Dict
from dataclasses import dataclass, field

from persistence.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class ModelProfile:
    """Model-specific identity that overrides avatar defaults."""
    model_id: str = ""
    stage_name: str = ""
    stated_location: str = ""           # Where the model claims to be (e.g., "Miami")
    age: Optional[int] = None
    ethnicity: str = ""
    hair_color: str = ""
    hair_length: str = ""
    body_type: str = ""
    height: str = ""
    notable_features: str = ""
    natural_personality: str = ""
    speaking_style: str = ""
    will_do: str = ""
    wont_do: str = ""
    face_in_tease: bool = True
    face_in_explicit: bool = True
    languages: list[str] = field(default_factory=lambda: ["English", "Spanish"])
    shooting_locations: list[str] = field(default_factory=list)


# Module-level cache with TTL — dict keyed by model_id
_profile_cache: Dict[str, tuple[ModelProfile, float]] = {}  # model_id -> (profile, cache_time)
_CACHE_TTL_SECONDS = 3600  # 1 hour


def load_model_profile(model_id: str) -> Optional[ModelProfile]:
    """
    Load a model's profile from Supabase.

    Caches the result for 1 hour per model_id. Returns None if model not found or profile_json is empty.
    """
    now = time.time()
    cached = _profile_cache.get(model_id)
    if cached and (now - cached[1]) < _CACHE_TTL_SECONDS:
        return cached[0]

    try:
        db = get_client()
        result = (
            db.table("models")
            .select("id, stage_name, profile_json")
            .eq("id", model_id)
            .limit(1)
            .execute()
        )

        if not result.data:
            logger.warning("Model %s not found in models table", model_id)
            return None

        row = result.data[0]
        pj = row.get("profile_json") or {}

        if not pj:
            logger.warning("Model %s has no profile_json", model_id)
            return None

        profile = ModelProfile(
            model_id=model_id,
            stage_name=row.get("stage_name", "") or pj.get("stage_name", ""),
            stated_location=pj.get("stated_location", "") or pj.get("location", ""),
            age=_parse_age(pj.get("age")),
            ethnicity=pj.get("ethnicity", ""),
            hair_color=pj.get("hair_color", ""),
            hair_length=pj.get("hair_length", ""),
            body_type=pj.get("body_type", ""),
            height=pj.get("height", ""),
            notable_features=pj.get("notable_features", ""),
            natural_personality=pj.get("natural_personality", ""),
            speaking_style=pj.get("natural_speaking_style", ""),
            will_do=pj.get("will_do", ""),
            wont_do=pj.get("wont_do", ""),
            face_in_tease=pj.get("face_in_tease", "Yes") == "Yes",
            face_in_explicit=pj.get("face_in_explicit", "Yes") == "Yes",
            languages=_parse_languages(pj.get("language", "")),
            shooting_locations=pj.get("shooting_locations") or [],
        )

        _profile_cache[model_id] = (profile, time.time())
        logger.info(
            "Loaded model profile: %s (location=%s, age=%s)",
            profile.stage_name, profile.stated_location, profile.age,
        )
        return profile

    except Exception as e:
        logger.warning("Failed to load model profile for %s: %s", model_id, str(e)[:100])
        return None


def _parse_age(val) -> Optional[int]:
    """Parse age from various formats."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int(val)
        except ValueError:
            pass
    return None


def _parse_languages(lang_code: str) -> list[str]:
    """Parse language code to language names."""
    mapping = {
        "en": ["English"],
        "es": ["English", "Spanish"],
        "es-CO": ["English", "Spanish"],
        "pt": ["English", "Portuguese"],
        "pt-BR": ["English", "Portuguese"],
        "fr": ["English", "French"],
        "de": ["English", "German"],
        "it": ["English", "Italian"],
    }
    return mapping.get(lang_code, ["English", "Spanish"])


def load_creator_model_map() -> Dict[str, str]:
    """
    Load all models with fanvue_creator_uuid set.
    Returns: {creator_uuid: model_id}
    """
    db = get_client()
    result = db.table("models").select(
        "id, fanvue_creator_uuid, stage_name, is_active"
    ).not_.is_("fanvue_creator_uuid", "null").execute()

    mapping = {}
    for row in result.data or []:
        creator_uuid = row["fanvue_creator_uuid"]
        model_id = row["id"]
        mapping[creator_uuid] = model_id
        logger.info("Model mapping: %s (%s) -> %s",
                     row.get("stage_name", "?"), creator_uuid[:8], model_id[:8])
    return mapping
