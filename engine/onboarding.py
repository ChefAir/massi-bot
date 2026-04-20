"""
Massi-Bot Bot Engine - Model Onboarding & Content Catalog System

This module handles everything that happens BEFORE scripts are written:
1. Model profile setup (appearance, ethnicity, location, personality)
2. Content upload and analysis (what's in each image/video)
3. Content cataloging into pricing tiers
4. Content bundle assembly (3-4 images + 1-2 videos per tier)
5. Script generation informed by actual content descriptions

FLOW:
  Model signs on → Fill out profile → Bulk create content →
  Upload content → Analyze/tag each piece → Catalog into tiers →
  Assemble bundles → Generate scripts around real content →
  Bot goes live with accurate descriptions

PRICING TIERS (6 tiers, non-negotiable feel):
  Tier 1: $27.38  - Full body tease, clothes ON
  Tier 2: $36.56  - Teasing top (pulling shirt, bra under shirt)
  Tier 3: $77.35  - Revealing top explicitly, playing with top half
  Tier 4: $92.46  - Revealing bottom (top on, bottoms off, not too explicit)
  Tier 5: $127.45 - Fully unclothed, explicit, playing with self
  Tier 6: $200.00 - Full out: on her back, self-inserts dildo, climaxes (OF max PPV)

Each tier PPV = 3-4 images + 1-2 videos bundled together.
Prices use odd numbers intentionally — looks "set in stone", no negotiation.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime
import uuid


# ═══════════════════════════════════════════════════════════════
# PRICING TIERS
# ═══════════════════════════════════════════════════════════════

class ContentTier(Enum):
    """
    6-tier pricing ladder. Each tier escalates in explicitness.
    Prices are intentionally odd numbers to look non-negotiable.
    """
    TIER_1_BODY_TEASE = "tier_1_body_tease"
    TIER_2_TOP_TEASE = "tier_2_top_tease"
    TIER_3_TOP_REVEAL = "tier_3_top_reveal"
    TIER_4_BOTTOM_REVEAL = "tier_4_bottom_reveal"
    TIER_5_FULL_EXPLICIT = "tier_5_full_explicit"
    TIER_6_CLIMAX = "tier_6_climax"


TIER_CONFIG = {
    ContentTier.TIER_1_BODY_TEASE: {
        "price": 27.38,
        "name": "Full Body Tease",
        "description": "Full body showing, clothes on, nothing explicit. Teasing body shape.",
        "explicitness": "clothed",
        "what_shows": "Full body silhouette, curves visible through clothing, suggestive poses",
        "what_doesnt_show": "No skin below neckline, no underwear visible",
        "images_per_bundle": (3, 4),   # min, max images
        "videos_per_bundle": (1, 2),   # min, max videos
        "position_in_ladder": 1,
    },
    ContentTier.TIER_2_TOP_TEASE: {
        "price": 36.56,
        "name": "Top Tease",
        "description": "Teasing the top half. Pulling shirt, bra off under shirt, cleavage.",
        "explicitness": "implied",
        "what_shows": "Cleavage, bra straps, pulling shirt down, removing bra under clothes",
        "what_doesnt_show": "No bare chest fully visible, no explicit nudity",
        "images_per_bundle": (3, 4),
        "videos_per_bundle": (1, 2),
        "position_in_ladder": 2,
    },
    ContentTier.TIER_3_TOP_REVEAL: {
        "price": 77.35,
        "name": "Top Reveal",
        "description": "Explicitly showing top half. Playing with top half.",
        "explicitness": "topless",
        "what_shows": "Bare chest, touching/playing with top half, explicit top nudity",
        "what_doesnt_show": "Bottom half covered or out of frame",
        "images_per_bundle": (3, 4),
        "videos_per_bundle": (1, 2),
        "position_in_ladder": 3,
    },
    ContentTier.TIER_4_BOTTOM_REVEAL: {
        "price": 92.46,
        "name": "Bottom Reveal",
        "description": "Top goes back on. Starts in panties, then takes panties off. Shows ass and legs. Teases like she's going to show pussy but DOESN'T. Pussy NOT visible.",
        "explicitness": "bottom_implied",
        "what_shows": "Panties on then off, ass, legs, teasing poses. Top covered.",
        "what_doesnt_show": "Pussy NOT shown. Legs not opened. Teasing only — no explicit genital visibility.",
        "images_per_bundle": (3, 4),
        "videos_per_bundle": (1, 2),
        "position_in_ladder": 4,
    },
    ContentTier.TIER_5_FULL_EXPLICIT: {
        "price": 127.45,
        "name": "Fully Unclothed Explicit",
        "description": "Fully nude. Shows tits, ass, AND pussy. Begins masturbating by fingering herself. No toys, no climax.",
        "explicitness": "full_nude_explicit",
        "what_shows": "Full nudity, tits, ass, pussy visible, fingering herself",
        "what_doesnt_show": "No toys, no dildo, no climax/orgasm",
        "images_per_bundle": (3, 4),
        "videos_per_bundle": (1, 2),
        "position_in_ladder": 5,
    },
    ContentTier.TIER_6_CLIMAX: {
        "price": 200.00,  # OF max PPV price — set in stone
        "name": "Full Climax",
        "description": "Lays on her back on the bed, legs spread, and self-inserts her dildo (7-inch, nude/tan) to climax. Missionary-style self-pleasure. NOT riding, NOT grinding, NOT on top.",
        "explicitness": "maximum",
        "what_shows": "On her back, self-inserting dildo missionary-style, climaxing with eye contact + moans",
        "what_doesnt_show": "N/A — this is the top tier",
        "images_per_bundle": (3, 4),
        "videos_per_bundle": (1, 2),
        "position_in_ladder": 6,
    },
}

def get_tier_price(tier: ContentTier) -> float:
    """Get the fixed price for a tier."""
    return TIER_CONFIG[tier]["price"]

def get_tier_name(tier: ContentTier) -> str:
    """Get the display name for a tier."""
    return TIER_CONFIG[tier]["name"]

def get_full_ladder_price() -> float:
    """Total price if a sub buys all 6 tiers in one session."""
    return sum(cfg["price"] for cfg in TIER_CONFIG.values())


# ═══════════════════════════════════════════════════════════════
# MODEL PROFILE
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModelProfile:
    """
    Complete model profile. Filled out during onboarding.
    The bot uses this to stay in character and never contradict
    what the model looks like or where she's from.
    """
    model_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # ── Identity ──
    stage_name: str = ""                    # Name used on OF
    real_first_name: str = ""               # For internal reference only
    age: int = 0
    birthday: str = ""                      # "March 15" (no year for privacy)

    # ── Appearance ──
    ethnicity: str = ""                     # e.g., "white", "latina", "mixed", "black", "asian"
    skin_tone: str = ""                     # e.g., "fair", "olive", "tan", "brown", "dark"
    hair_color: str = ""                    # e.g., "brunette", "blonde", "black", "red", "pink"
    hair_length: str = ""                   # "short", "medium", "long"
    hair_style: str = ""                    # "straight", "curly", "wavy", "braids"
    eye_color: str = ""
    body_type: str = ""                     # "slim", "athletic", "curvy", "petite", "thick"
    height: str = ""                        # e.g., "5'4"
    notable_features: List[str] = field(default_factory=list)  # tattoos, piercings, freckles, etc.
    breast_size: str = ""                   # for content accuracy
    butt_description: str = ""              # for content accuracy

    # ── Location & Background ──
    stated_location: str = ""               # Where "she" says she's from (may differ per avatar)
    actual_timezone: str = ""               # For scheduling messages appropriately
    accent_or_dialect: str = ""             # Affects voice/slang choices

    # ── Personality Baseline ──
    # These are overridden per avatar but this is the model's natural baseline
    natural_personality: str = ""           # e.g., "bubbly, sarcastic, sweet"
    natural_speaking_style: str = ""        # e.g., "gen z casual, lots of lol and emojis"
    languages_spoken: List[str] = field(default_factory=lambda: ["English"])

    # ── Content Boundaries ──
    will_do: List[str] = field(default_factory=list)       # e.g., ["solo", "toys", "lingerie", "implied boy-girl"]
    wont_do: List[str] = field(default_factory=list)       # e.g., ["face showing in explicit", "boy-girl actual"]
    face_in_explicit: bool = False                          # Critical: does face show in Tier 5-6 content?
    face_in_tease: bool = True                              # Does face show in Tier 1-2?

    # ── Content Logistics ──
    shooting_locations: List[str] = field(default_factory=list)  # ["bedroom", "bathroom", "kitchen", "living room"]
    wardrobe_available: List[str] = field(default_factory=list)  # ["oversized tee", "lingerie set", "bikini", "gym clothes"]
    toys_available: List[str] = field(default_factory=list)       # For Tier 6 content

    # ── Avatar Assignments ──
    # Which avatars this model is assigned to (usually all 10, since content is reused)
    assigned_avatar_ids: List[str] = field(default_factory=list)

    def to_content_context(self) -> Dict[str, Any]:
        """Generate context dict that the script writer uses to describe content accurately."""
        return {
            "ethnicity": self.ethnicity,
            "skin_tone": self.skin_tone,
            "hair": f"{self.hair_color} {self.hair_length} {self.hair_style}".strip(),
            "body": self.body_type,
            "height": self.height,
            "notable": self.notable_features,
            "face_in_explicit": self.face_in_explicit,
            "locations": self.shooting_locations,
            "wardrobe": self.wardrobe_available,
            "toys": self.toys_available,
            "boundaries": self.wont_do,
        }


# ═══════════════════════════════════════════════════════════════
# CONTENT PIECE - Individual image or video
# ═══════════════════════════════════════════════════════════════

class ContentType(Enum):
    IMAGE = "image"
    VIDEO = "video"


@dataclass
class ContentPiece:
    """
    A single image or video that has been analyzed and tagged.
    After the model bulk-creates content, each piece is analyzed
    (either manually or via vision AI) and tagged with metadata
    that the script writer needs.
    """
    content_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    file_path: str = ""                     # Path to actual file
    content_type: ContentType = ContentType.IMAGE
    tier: Optional[ContentTier] = None      # Which pricing tier this belongs to

    # ── Analysis Results ──
    # These are filled in after analyzing the image/video
    clothing: List[str] = field(default_factory=list)       # ["oversized tee", "no pants", "black bra"]
    clothing_state: str = ""                                 # "fully clothed", "partially clothed", "topless", "nude"
    body_parts_visible: List[str] = field(default_factory=list)  # ["legs", "cleavage", "stomach", "back"]
    pose: str = ""                                           # "laying in bed", "standing mirror", "sitting on couch"
    position: str = ""                                       # "front facing", "side angle", "from behind", "POV"
    location: str = ""                                       # "bedroom", "bathroom", "kitchen", "couch"
    lighting: str = ""                                       # "natural", "dim", "ring light", "candle lit"
    mood: str = ""                                           # "playful", "seductive", "innocent", "intense"
    facial_expression: str = ""                              # "smiling", "biting lip", "looking away", "eyes closed"
    face_visible: bool = True
    props: List[str] = field(default_factory=list)           # ["pillow", "mirror", "phone", "toy"]

    # Video-specific
    duration_seconds: Optional[int] = None
    action_description: str = ""             # "slowly removes shirt", "plays with hair", "touches self"
    has_audio: bool = False
    audio_description: str = ""              # "music playing", "moaning", "whispering"

    # ── Script Context ──
    # This is the one-line natural language description the script writer uses
    # to craft accurate captions and dirty talk
    script_context: str = ""                 # e.g., "Laying on bed in oversized white tee, no pants, legs showing, playful smile, natural light from window"

    # Usage tracking
    times_used: int = 0
    last_used_date: Optional[datetime] = None
    assigned_to_bundles: List[str] = field(default_factory=list)

    def generate_script_context(self) -> str:
        """Auto-generate script context from analyzed tags."""
        parts = []
        if self.pose:
            parts.append(self.pose)
        if self.clothing:
            parts.append(f"wearing {', '.join(self.clothing)}")
        if self.location:
            parts.append(f"in {self.location}")
        if self.body_parts_visible:
            parts.append(f"{', '.join(self.body_parts_visible)} visible")
        if self.facial_expression:
            parts.append(self.facial_expression)
        if self.lighting:
            parts.append(f"{self.lighting} lighting")
        if self.action_description and self.content_type == ContentType.VIDEO:
            parts.append(f"action: {self.action_description}")
        self.script_context = ". ".join(parts) if parts else "content piece"
        return self.script_context


# ═══════════════════════════════════════════════════════════════
# CONTENT BUNDLE - What actually gets sent as a PPV
# ═══════════════════════════════════════════════════════════════

@dataclass
class ContentBundle:
    """
    A PPV bundle = 3-4 images + 1-2 videos from the same tier.
    This is what the sub actually receives when they unlock a PPV.
    The script references the BUNDLE, not individual pieces.
    """
    bundle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    tier: ContentTier = ContentTier.TIER_1_BODY_TEASE
    price: float = 0.0

    # Content pieces in this bundle
    images: List[ContentPiece] = field(default_factory=list)
    videos: List[ContentPiece] = field(default_factory=list)

    # Script context for the ENTIRE bundle
    # This combines the contexts of all pieces into a coherent description
    bundle_context: str = ""
    primary_location: str = ""               # Most common location in bundle
    primary_clothing: str = ""               # Starting outfit
    primary_mood: str = ""                   # Overall mood of bundle

    # Script-ready description lines the bot can use
    tease_lines: List[str] = field(default_factory=list)     # What bot says BEFORE sending
    caption_lines: List[str] = field(default_factory=list)   # PPV caption text
    reaction_lines: List[str] = field(default_factory=list)  # What bot says AFTER sub unlocks

    # Usage tracking
    times_sent: int = 0
    times_purchased: int = 0
    conversion_rate: float = 0.0

    @property
    def total_pieces(self) -> int:
        return len(self.images) + len(self.videos)

    @property
    def is_valid(self) -> bool:
        """Check if bundle meets minimum requirements."""
        return (3 <= len(self.images) <= 4 and
                1 <= len(self.videos) <= 2)

    def generate_bundle_context(self):
        """Generate bundle-level context from individual pieces."""
        all_pieces = self.images + self.videos

        # Find most common location
        locations = [p.location for p in all_pieces if p.location]
        if locations:
            self.primary_location = max(set(locations), key=locations.count)

        # Find starting clothing
        if self.images:
            self.primary_clothing = ", ".join(self.images[0].clothing) if self.images[0].clothing else "unknown"

        # Find primary mood
        moods = [p.mood for p in all_pieces if p.mood]
        if moods:
            self.primary_mood = max(set(moods), key=moods.count)

        # Build bundle context
        tier_cfg = TIER_CONFIG[self.tier]
        contexts = [p.script_context for p in all_pieces if p.script_context]
        self.bundle_context = (
            f"Tier: {tier_cfg['name']} (${tier_cfg['price']}). "
            f"Location: {self.primary_location}. "
            f"Starting outfit: {self.primary_clothing}. "
            f"Mood: {self.primary_mood}. "
            f"Pieces: {len(self.images)} images, {len(self.videos)} videos. "
            f"Content: {'; '.join(contexts[:3])}"
        )


# ═══════════════════════════════════════════════════════════════
# CONTENT CATALOG - The full organized library
# ═══════════════════════════════════════════════════════════════

@dataclass
class ContentCatalog:
    """
    The complete organized content library for one model.
    Manages all content pieces, bundles, and usage tracking.
    """
    model_id: str = ""
    pieces: Dict[str, ContentPiece] = field(default_factory=dict)      # content_id → ContentPiece
    bundles: Dict[str, ContentBundle] = field(default_factory=dict)     # bundle_id → ContentBundle
    bundles_by_tier: Dict[ContentTier, List[str]] = field(default_factory=lambda: {
        tier: [] for tier in ContentTier
    })

    def add_piece(self, piece: ContentPiece):
        """Add an analyzed content piece to the catalog."""
        self.pieces[piece.content_id] = piece

    def add_bundle(self, bundle: ContentBundle):
        """Add an assembled bundle to the catalog."""
        self.bundles[bundle.bundle_id] = bundle
        self.bundles_by_tier[bundle.tier].append(bundle.bundle_id)

    def get_available_bundle(self, tier: ContentTier, exclude_ids: List[str] = None) -> Optional[ContentBundle]:
        """
        Get the next available bundle for a tier that hasn't been sent to a specific sub.
        Used by the engine to pick content for PPV sends.
        """
        exclude = set(exclude_ids or [])
        tier_bundle_ids = self.bundles_by_tier.get(tier, [])

        for bid in tier_bundle_ids:
            if bid not in exclude:
                return self.bundles.get(bid)

        # All bundles used — recycle least-used
        if tier_bundle_ids:
            candidates = [(self.bundles[bid].times_sent, bid) for bid in tier_bundle_ids]
            candidates.sort()
            return self.bundles[candidates[0][1]]

        return None

    def get_catalog_stats(self) -> Dict:
        """Get stats about the catalog."""
        tier_counts = {}
        for tier in ContentTier:
            bundle_ids = self.bundles_by_tier.get(tier, [])
            piece_count = 0
            for bid in bundle_ids:
                b = self.bundles.get(bid)
                if b:
                    piece_count += b.total_pieces
            tier_counts[tier.value] = {
                "bundles": len(bundle_ids),
                "pieces": piece_count,
                "price": TIER_CONFIG[tier]["price"],
            }

        return {
            "model_id": self.model_id,
            "total_pieces": len(self.pieces),
            "total_bundles": len(self.bundles),
            "tiers": tier_counts,
            "full_ladder_revenue": get_full_ladder_price(),
        }


# ═══════════════════════════════════════════════════════════════
# CONTENT ANALYZER INTERFACE
# ═══════════════════════════════════════════════════════════════

class ContentAnalyzer:
    """
    Interface for analyzing uploaded content.
    In production, this would use vision AI (Claude, GPT-4V, etc.)
    to automatically tag images and videos.

    For now, it provides the schema and manual entry flow.
    """

    # Auto-classification rules for tier assignment
    TIER_RULES = {
        ContentTier.TIER_1_BODY_TEASE: {
            "clothing_state": ["fully clothed", "casual clothed"],
            "requires": ["body visible"],
            "excludes": ["topless", "nude", "explicit"],
        },
        ContentTier.TIER_2_TOP_TEASE: {
            "clothing_state": ["partially clothed", "implied"],
            "requires": ["cleavage", "bra visible", "shirt pulling"],
            "excludes": ["bare chest", "nude", "explicit"],
        },
        ContentTier.TIER_3_TOP_REVEAL: {
            "clothing_state": ["topless"],
            "requires": ["bare chest", "playing with top"],
            "excludes": ["full nude", "bottom explicit"],
        },
        ContentTier.TIER_4_BOTTOM_REVEAL: {
            "clothing_state": ["bottomless", "bottom revealed"],
            "requires": ["bottoms off", "top on"],
            "excludes": ["full nude explicit"],
        },
        ContentTier.TIER_5_FULL_EXPLICIT: {
            "clothing_state": ["nude", "full nude"],
            "requires": ["full nudity", "self play"],
            "excludes": ["toys", "climax"],
        },
        ContentTier.TIER_6_CLIMAX: {
            "clothing_state": ["nude"],
            "requires_any": ["toys", "riding", "climax", "orgasm"],
        },
    }

    @staticmethod
    def analyze_image(
        file_path: str,
        manual_tags: Dict[str, Any] = None
    ) -> ContentPiece:
        """
        Analyze a single image and return a tagged ContentPiece.

        In production: Pass image to vision AI for auto-tagging.
        For now: Uses manual_tags dict.

        manual_tags example:
        {
            "clothing": ["oversized white tee", "no pants"],
            "clothing_state": "partially clothed",
            "body_parts_visible": ["legs", "cleavage", "stomach"],
            "pose": "laying on bed",
            "position": "front facing",
            "location": "bedroom",
            "lighting": "natural",
            "mood": "playful",
            "facial_expression": "biting lip",
            "face_visible": True,
            "props": ["pillow"],
        }
        """
        piece = ContentPiece(
            file_path=file_path,
            content_type=ContentType.IMAGE,
        )

        if manual_tags:
            piece.clothing = manual_tags.get("clothing", [])
            piece.clothing_state = manual_tags.get("clothing_state", "")
            piece.body_parts_visible = manual_tags.get("body_parts_visible", [])
            piece.pose = manual_tags.get("pose", "")
            piece.position = manual_tags.get("position", "")
            piece.location = manual_tags.get("location", "")
            piece.lighting = manual_tags.get("lighting", "")
            piece.mood = manual_tags.get("mood", "")
            piece.facial_expression = manual_tags.get("facial_expression", "")
            piece.face_visible = manual_tags.get("face_visible", True)
            piece.props = manual_tags.get("props", [])

        piece.generate_script_context()
        return piece

    @staticmethod
    def analyze_video(
        file_path: str,
        manual_tags: Dict[str, Any] = None
    ) -> ContentPiece:
        """Analyze a single video and return a tagged ContentPiece."""
        piece = ContentPiece(
            file_path=file_path,
            content_type=ContentType.VIDEO,
        )

        if manual_tags:
            piece.clothing = manual_tags.get("clothing", [])
            piece.clothing_state = manual_tags.get("clothing_state", "")
            piece.body_parts_visible = manual_tags.get("body_parts_visible", [])
            piece.pose = manual_tags.get("pose", "")
            piece.position = manual_tags.get("position", "")
            piece.location = manual_tags.get("location", "")
            piece.lighting = manual_tags.get("lighting", "")
            piece.mood = manual_tags.get("mood", "")
            piece.facial_expression = manual_tags.get("facial_expression", "")
            piece.face_visible = manual_tags.get("face_visible", True)
            piece.props = manual_tags.get("props", [])
            piece.duration_seconds = manual_tags.get("duration_seconds", 0)
            piece.action_description = manual_tags.get("action_description", "")
            piece.has_audio = manual_tags.get("has_audio", False)
            piece.audio_description = manual_tags.get("audio_description", "")

        piece.generate_script_context()
        return piece

    @staticmethod
    def auto_assign_tier(piece: ContentPiece) -> Optional[ContentTier]:
        """
        Attempt to auto-assign a tier based on content tags.
        Returns None if ambiguous — requires manual assignment.
        """
        state = piece.clothing_state.lower()
        body_parts = set(p.lower() for p in piece.body_parts_visible)
        props = set(p.lower() for p in piece.props)
        action = piece.action_description.lower()

        # Check from most explicit to least (Tier 6 → Tier 1)
        if any(w in action for w in ["toy", "riding", "climax", "orgasm", "vibrator", "dildo"]):
            return ContentTier.TIER_6_CLIMAX

        if any(w in action for w in ["playing with self", "touching self", "masturbat"]):
            if state in ["nude", "full nude", "fully nude"]:
                return ContentTier.TIER_5_FULL_EXPLICIT

        if state in ["bottomless", "bottom revealed"] or "bottoms off" in action:
            return ContentTier.TIER_4_BOTTOM_REVEAL

        if state == "topless" or "bare chest" in " ".join(body_parts):
            return ContentTier.TIER_3_TOP_REVEAL

        if state in ["partially clothed", "implied"]:
            if any(p in body_parts for p in ["cleavage", "bra"]):
                return ContentTier.TIER_2_TOP_TEASE

        if state in ["fully clothed", "casual clothed", "clothed"]:
            return ContentTier.TIER_1_BODY_TEASE

        return None  # Ambiguous — needs manual assignment


# ═══════════════════════════════════════════════════════════════
# BUNDLE ASSEMBLER
# ═══════════════════════════════════════════════════════════════

class BundleAssembler:
    """
    Assembles content pieces into PPV bundles.
    Each bundle = 3-4 images + 1-2 videos from the same tier,
    ideally from the same location/outfit for narrative coherence.
    """

    @staticmethod
    def assemble_bundles(
        pieces: List[ContentPiece],
        tier: ContentTier
    ) -> List[ContentBundle]:
        """
        Take all pieces assigned to a tier and assemble into bundles.
        Groups by location/outfit when possible for narrative flow.
        """
        cfg = TIER_CONFIG[tier]
        min_images, max_images = cfg["images_per_bundle"]
        min_videos, max_videos = cfg["videos_per_bundle"]

        # Separate images and videos
        images = [p for p in pieces if p.content_type == ContentType.IMAGE]
        videos = [p for p in pieces if p.content_type == ContentType.VIDEO]

        bundles = []

        # Group by location for narrative coherence
        location_groups: Dict[str, Dict[str, List[ContentPiece]]] = {}
        for img in images:
            loc = img.location or "unknown"
            if loc not in location_groups:
                location_groups[loc] = {"images": [], "videos": []}
            location_groups[loc]["images"].append(img)

        for vid in videos:
            loc = vid.location or "unknown"
            if loc not in location_groups:
                location_groups[loc] = {"images": [], "videos": []}
            location_groups[loc]["videos"].append(vid)

        # Assemble bundles from each location group
        for loc, group in location_groups.items():
            loc_images = group["images"]
            loc_videos = group["videos"]

            while len(loc_images) >= min_images and len(loc_videos) >= min_videos:
                # Take images and videos for one bundle
                bundle_images = loc_images[:max_images]
                loc_images = loc_images[max_images:]

                bundle_videos = loc_videos[:max_videos]
                loc_videos = loc_videos[max_videos:]

                bundle = ContentBundle(
                    tier=tier,
                    price=cfg["price"],
                    images=bundle_images,
                    videos=bundle_videos,
                )
                bundle.generate_bundle_context()

                # Mark pieces as assigned
                for p in bundle_images + bundle_videos:
                    p.assigned_to_bundles.append(bundle.bundle_id)

                bundles.append(bundle)

        return bundles


# ═══════════════════════════════════════════════════════════════
# ONBOARDING FLOW
# ═══════════════════════════════════════════════════════════════

class ModelOnboarding:
    """
    Manages the complete model onboarding flow.

    Steps:
    1. Create model profile (appearance, boundaries, logistics)
    2. Upload and analyze content pieces
    3. Assign content to tiers
    4. Assemble bundles
    5. Generate script context for each bundle
    6. System ready for script generation

    Usage:
        onboarding = ModelOnboarding()
        profile = onboarding.create_profile(...)
        onboarding.add_content(file_path, tags)
        onboarding.assign_tiers()
        onboarding.assemble_all_bundles()
        catalog = onboarding.get_catalog()
    """

    def __init__(self):
        self.profile: Optional[ModelProfile] = None
        self.catalog = ContentCatalog()
        self.analyzer = ContentAnalyzer()
        self.assembler = BundleAssembler()
        self._unassigned_pieces: List[ContentPiece] = []

    def create_profile(self, **kwargs) -> ModelProfile:
        """Step 1: Create the model profile."""
        self.profile = ModelProfile(**kwargs)
        self.catalog.model_id = self.profile.model_id
        return self.profile

    def add_content(
        self,
        file_path: str,
        content_type: str = "image",
        tags: Dict[str, Any] = None,
        tier: ContentTier = None,
    ) -> ContentPiece:
        """
        Step 2: Add and analyze a content piece.

        Args:
            file_path: Path to image/video file
            content_type: "image" or "video"
            tags: Analysis tags (manual or from vision AI)
            tier: Manual tier assignment (auto-detected if None)
        """
        if content_type == "video":
            piece = self.analyzer.analyze_video(file_path, tags)
        else:
            piece = self.analyzer.analyze_image(file_path, tags)

        # Auto-assign tier if not specified
        if tier:
            piece.tier = tier
        else:
            piece.tier = self.analyzer.auto_assign_tier(piece)

        if piece.tier:
            self.catalog.add_piece(piece)
        else:
            self._unassigned_pieces.append(piece)

        return piece

    def get_unassigned(self) -> List[ContentPiece]:
        """Get pieces that couldn't be auto-assigned to a tier."""
        return self._unassigned_pieces

    def assign_tier(self, content_id: str, tier: ContentTier):
        """Manually assign a tier to an unassigned piece."""
        for i, piece in enumerate(self._unassigned_pieces):
            if piece.content_id == content_id:
                piece.tier = tier
                self.catalog.add_piece(piece)
                self._unassigned_pieces.pop(i)
                return True
        return False

    def assemble_all_bundles(self) -> Dict[ContentTier, int]:
        """
        Step 3: Assemble all pieces into bundles by tier.
        Returns count of bundles created per tier.
        """
        results = {}
        for tier in ContentTier:
            tier_pieces = [
                p for p in self.catalog.pieces.values()
                if p.tier == tier
            ]
            if tier_pieces:
                bundles = self.assembler.assemble_bundles(tier_pieces, tier)
                for bundle in bundles:
                    self.catalog.add_bundle(bundle)
                results[tier] = len(bundles)
            else:
                results[tier] = 0
        return results

    def get_catalog(self) -> ContentCatalog:
        """Get the assembled content catalog."""
        return self.catalog

    def get_readiness_report(self) -> Dict:
        """Check if the model is ready to go live."""
        stats = self.catalog.get_catalog_stats()
        issues = []

        if not self.profile:
            issues.append("No model profile created")
        elif not self.profile.stage_name:
            issues.append("Model stage name not set")
        elif not self.profile.ethnicity:
            issues.append("Model ethnicity not set — bot needs this for accuracy")

        for tier in ContentTier:
            tier_bundles = len(self.catalog.bundles_by_tier.get(tier, []))
            if tier_bundles == 0:
                issues.append(f"No bundles for {TIER_CONFIG[tier]['name']} (${TIER_CONFIG[tier]['price']})")
            elif tier_bundles < 3:
                issues.append(f"Only {tier_bundles} bundles for {TIER_CONFIG[tier]['name']} — recommend 5+ for rotation")

        if self._unassigned_pieces:
            issues.append(f"{len(self._unassigned_pieces)} content pieces not assigned to a tier")

        return {
            "ready": len(issues) == 0,
            "issues": issues,
            "stats": stats,
            "profile_set": self.profile is not None,
            "unassigned_pieces": len(self._unassigned_pieces),
        }


# ═══════════════════════════════════════════════════════════════
# DEMO
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   Model Onboarding & Content Catalog System             ║")
    print("╚══════════════════════════════════════════════════════════╝")

    # Show pricing ladder
    print("\n  PRICING LADDER:")
    print(f"  {'─'*55}")
    total = 0
    for tier, cfg in TIER_CONFIG.items():
        print(f"  Tier {cfg['position_in_ladder']}: ${cfg['price']:>7.2f}  │  {cfg['name']}")
        print(f"         {' '*9}  │  {cfg['description'][:60]}")
        print(f"         {' '*9}  │  Bundle: {cfg['images_per_bundle'][0]}-{cfg['images_per_bundle'][1]} images + {cfg['videos_per_bundle'][0]}-{cfg['videos_per_bundle'][1]} videos")
        total += cfg["price"]
    print(f"  {'─'*55}")
    print(f"  FULL LADDER:  ${total:>7.2f}  │  Total if sub buys all 6 tiers")

    # Demo onboarding flow
    print(f"\n\n  ONBOARDING DEMO:")
    print(f"  {'─'*55}")

    onboarding = ModelOnboarding()

    # Step 1: Create profile
    profile = onboarding.create_profile(
        stage_name="Bella",
        age=23,
        ethnicity="latina",
        skin_tone="olive",
        hair_color="brunette",
        hair_length="long",
        hair_style="wavy",
        eye_color="brown",
        body_type="curvy",
        height="5'4",
        notable_features=["belly button piercing", "small tattoo on hip"],
        stated_location="Miami",
        natural_personality="flirty, playful, warm",
        shooting_locations=["bedroom", "bathroom", "kitchen", "living room"],
        wardrobe_available=["oversized tee", "black lingerie set", "red bikini",
                          "gym shorts", "sundress", "silk robe"],
        toys_available=["vibrator", "dildo"],
        will_do=["solo", "toys", "lingerie", "implied"],
        wont_do=["boy-girl", "anal"],
        face_in_explicit=False,
        face_in_tease=True,
    )
    print(f"  ✅ Profile created: {profile.stage_name}")

    # Step 2: Add analyzed content (simulated)
    sample_content = [
        {"file": "img_001.jpg", "type": "image", "tags": {
            "clothing": ["oversized white tee", "no visible pants"],
            "clothing_state": "fully clothed",
            "body_parts_visible": ["legs", "body silhouette"],
            "pose": "laying on bed",
            "location": "bedroom",
            "lighting": "natural",
            "mood": "playful",
            "facial_expression": "smiling",
        }},
        {"file": "img_002.jpg", "type": "image", "tags": {
            "clothing": ["oversized white tee"],
            "clothing_state": "fully clothed",
            "body_parts_visible": ["legs", "waist", "curves"],
            "pose": "standing mirror selfie",
            "location": "bedroom",
            "lighting": "natural",
            "mood": "casual",
            "facial_expression": "looking at phone",
        }},
        {"file": "img_003.jpg", "type": "image", "tags": {
            "clothing": ["oversized white tee", "visible bra strap"],
            "clothing_state": "fully clothed",
            "body_parts_visible": ["shoulder", "legs", "collarbone"],
            "pose": "sitting on bed",
            "location": "bedroom",
            "lighting": "natural",
            "mood": "innocent",
            "facial_expression": "looking away shyly",
        }},
        {"file": "vid_001.mp4", "type": "video", "tags": {
            "clothing": ["oversized white tee"],
            "clothing_state": "fully clothed",
            "body_parts_visible": ["legs", "body movement"],
            "pose": "walking to bed",
            "location": "bedroom",
            "lighting": "natural",
            "mood": "playful",
            "facial_expression": "biting lip",
            "duration_seconds": 15,
            "action_description": "walks to bed, lays down, pulls tee to show legs",
            "has_audio": False,
        }},
    ]

    for item in sample_content:
        piece = onboarding.add_content(
            file_path=item["file"],
            content_type=item["type"],
            tags=item["tags"],
        )
        tier_name = TIER_CONFIG[piece.tier]["name"] if piece.tier else "UNASSIGNED"
        print(f"  ✅ Added {item['type']}: {item['file']} → {tier_name}")
        print(f"     Context: {piece.script_context[:70]}...")

    # Step 3: Assemble bundles
    bundle_counts = onboarding.assemble_all_bundles()
    for tier, count in bundle_counts.items():
        if count > 0:
            print(f"  ✅ Assembled {count} bundle(s) for {TIER_CONFIG[tier]['name']}")

    # Step 4: Readiness check
    report = onboarding.get_readiness_report()
    print(f"\n  READINESS: {'✅ READY' if report['ready'] else '❌ NOT READY'}")
    for issue in report["issues"]:
        print(f"  ⚠️  {issue}")

    print(f"\n  When ready, the catalog provides the script factory with:")
    print(f"  - Exact descriptions of what's in each PPV bundle")
    print(f"  - Location, clothing, mood, pose for accurate dirty talk")
    print(f"  - Tier pricing that looks non-negotiable to subs")
    print(f"  - Bundle rotation to avoid sending the same content twice")
