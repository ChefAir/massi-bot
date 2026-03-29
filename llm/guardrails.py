"""
Massi-Bot LLM - Guardrails

Post-processing applied to every LLM response before it's sent to a subscriber.
Returns None if any guardrail trips → caller falls back to templates.

Rules:
  1. Reject if AI self-reference patterns found ("as an AI", "language model", etc.)
  2. Reject if AI vocabulary detected ("delve", "nuanced", "certainly", "great question", etc.)
  3. Reject if sycophantic opener detected ("Great question!", "Absolutely!", etc.)
  4. Reject if contact info patterns found (phone, email)
  5. Truncate to max 3 sentences (4 for selling/objection modes)
  6. Ensure at least one emoji is present (append one if missing)
  7. State-specific checks via GuardrailMode
"""

import re
import logging
import sys
import os
from enum import Enum

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# State-specific guardrail modes
# ─────────────────────────────────────────────

class GuardrailMode(Enum):
    STANDARD = "standard"       # GFE, retention, re-engagement, post-session
    QUALIFYING = "qualifying"   # No explicit, no prices, no PPV mentions
    SELLING = "selling"         # Explicit OK, but no price/dollar mentions
    OBJECTION = "objection"     # Ego language OK, no price negotiation

# ─────────────────────────────────────────────
# Blocklist patterns
# ─────────────────────────────────────────────

_AI_SELF_REFERENCES = [
    r"\bas an ai\b",
    r"\bi('m| am) an ai\b",
    r"\blanguage model\b",
    r"\bi cannot\b",
    r"\bi('m| am) not able to\b",
    r"\bopenai\b",
    r"\banthropics?\b",
    r"\bchatgpt\b",
    r"\bdolphin\b",
    r"\bllm\b",
    r"\bneural network\b",
    r"\bmodel\b.*\btraining\b",
]

# AI vocabulary patterns — words/phrases that signal AI generation, not human chat
# Source: ACM CUI 2024 analysis of top bot-detection signals
_AI_VOCABULARY = {
    "delve", "delving", "nuanced", "certainly", "absolutely", "definitely",
    "straightforward", "intricate", "multifaceted", "paramount", "pivotal",
    "embark", "endeavor", "leverage", "utilize", "facilitate", "demonstrate",
    "tapestry", "testament", "realm", "landscape", "groundbreaking", "revolutionary",
    "comprehensive", "notably", "furthermore", "moreover", "in summary", "to summarize",
    "it's important to note", "it's worth noting", "rest assured",
    "i'd be happy to", "i'd be glad to", "i hope this helps",
    "of course!", "certainly!", "absolutely!", "great question",
    "i understand your", "i appreciate your", "thank you for sharing",
}

# Sycophantic openers — phrases that start a response and immediately signal AI
_SYCOPHANTIC_OPENERS = (
    "great question",
    "what a great",
    "i love that question",
    "that's a great",
    "that's such a great",
    "that's an excellent",
    "excellent question",
    "what an interesting",
    "i appreciate you",
    "thank you for sharing",
    "i'm so glad you",
    "i'm so happy you",
    "of course! ",
    "certainly! ",
    "absolutely! ",
)

_CONTACT_PATTERNS = [
    r"\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}",        # phone numbers
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",  # emails
    r"\bmy (number|phone|insta|instagram|snap|snapchat|whatsapp)\b",
    r"\badd me on\b",
    r"\bdm me on\b",
]

# Fallback emojis to append if response has none
_FALLBACK_EMOJIS = ["😏", "😘", "🔥", "💕", "😍", "🥵", "❤️", "👀", "😂", "🙈"]

# Goth_domme only uses these 7 emoji — all others must be stripped
_GOTH_DOMME_ALLOWED_EMOJI = {"💀", "🖤", "😈", "🙄", "😏", "🫠", "👀"}
_GOTH_DOMME_BANNED_EMOJI = {"🥰", "😍", "💕", "❤️", "😘", "🥵", "🔥", "😂", "🙈",
                             "💋", "🥺", "😳", "💎", "💅", "🫣", "😩", "🤫"}
# Avatars where emoji should NOT be force-added when missing
# (goth_domme uses emoji ~1 in 4 messages, not every message)
_SPARSE_EMOJI_AVATARS = {"goth_domme"}

# Goth_domme-specific banned phrases
_GOTH_DOMME_BANNED_PHRASES = [
    "real talk", "let me be real", "truth be told", "i must admit",
    "i have to say", "i appreciate that", "that means a lot",
    "worth every penny", "put my all into this",
    "im not like other girls", "i'm not like other girls",
    "darkness is my home", "i feed on your soul",
]

# Generic goth cringe phrases — blocked for goth_domme
_GOTH_CRINGE_PATTERN = re.compile(
    r"\b(darkness is my home|i feed on your soul|embrace the darkness|"
    r"queen of darkness|dark goddess|creature of the night|"
    r"my dark heart|souls? (?:are|is) my|born from darkness)\b",
    re.IGNORECASE,
)

# Regex to detect any emoji presence
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F"   # emoticons
    "\U0001F300-\U0001F5FF"   # symbols & pictographs
    "\U0001F680-\U0001F6FF"   # transport & map
    "\U0001F1E0-\U0001F1FF"   # flags
    "\U0001F900-\U0001F9FF"   # supplemental symbols (🥵🥰🤗🥺 etc.)
    "\U0001FA70-\U0001FAFF"   # symbols extended-A (🫠🫣🫶 etc.)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "❤️💕💔💓💗💖💘💝💟"
    "]+",
    flags=re.UNICODE,
)


# ─────────────────────────────────────────────
# Guardrail functions
# ─────────────────────────────────────────────

def _truncate_to_sentences(text: str, max_sentences: int = 3) -> str:
    """Truncate text to at most max_sentences sentences."""
    # Split on '. ', '! ', '? ' followed by uppercase or end of string
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    kept = sentences[:max_sentences]
    result = " ".join(kept)
    # Ensure it ends with punctuation
    if result and result[-1] not in ".!?":
        result += "."
    return result


def _has_ai_reference(text: str) -> bool:
    lower = text.lower()
    for pattern in _AI_SELF_REFERENCES:
        if re.search(pattern, lower):
            return True
    return False


def _has_ai_vocabulary(text: str) -> bool:
    """Return True if the text contains known AI-generated vocabulary patterns."""
    lower = text.lower()
    # Check multi-word phrases first
    for phrase in _AI_VOCABULARY:
        if " " in phrase and phrase in lower:
            return True
    # Check single words with word boundary
    words = set(re.findall(r"\b\w+\b", lower))
    for vocab in _AI_VOCABULARY:
        if " " not in vocab and vocab in words:
            return True
    return False


def _has_sycophantic_opener(text: str) -> bool:
    """Return True if the response opens with a sycophantic AI-style greeting."""
    lower = text.lower().lstrip()
    return any(lower.startswith(opener) for opener in _SYCOPHANTIC_OPENERS)


def _has_contact_info(text: str) -> bool:
    lower = text.lower()
    for pattern in _CONTACT_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return True
    return False


def _has_emoji(text: str) -> bool:
    return bool(_EMOJI_RE.search(text))


def _append_emoji(text: str, avatar_emojis: list[str] | None = None) -> str:
    """Append a random emoji from avatar style or default set.
    Inserts emoji before trailing punctuation so the response still ends with .!?
    """
    import random
    pool = avatar_emojis if avatar_emojis else _FALLBACK_EMOJIS
    emoji = random.choice(pool)
    if text and text[-1] in ".!?":
        return f"{text[:-1]} {emoji}{text[-1]}"
    return f"{text} {emoji}"


def _strip_disallowed_emoji(text: str, allowed: set[str]) -> str:
    """Remove any emoji from text that isn't in the allowed set.
    Uses regex to find all emoji sequences, then keeps only allowed ones.
    """
    def _replace(match: re.Match) -> str:
        emoji_str = match.group()
        # Check if this emoji (or any substring of it) is in the allowed set
        for a in allowed:
            if a in emoji_str:
                return a
        return ""  # Strip disallowed emoji

    return _EMOJI_RE.sub(_replace, text)


def _check_goth_domme_phrases(text: str) -> bool:
    """Return True if text contains goth_domme-banned phrases. True = violation found."""
    lower = text.lower()
    for phrase in _GOTH_DOMME_BANNED_PHRASES:
        if phrase in lower:
            logger.warning("Guardrail [GOTH_DOMME]: banned phrase '%s' found", phrase)
            return True
    if _GOTH_CRINGE_PATTERN.search(text):
        logger.warning("Guardrail [GOTH_DOMME]: generic goth cringe detected")
        return True
    return False


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def post_process(
    response: str,
    avatar_emojis: list[str] | None = None,
    avatar_id: str = "",
) -> str | None:
    """
    Apply all guardrails to an LLM response.

    Returns:
        Clean, safe response string — or None if guardrails reject it.
        None triggers fallback to template response in the router.

    Args:
        response: Raw LLM output string.
        avatar_emojis: Optional list of emoji from the avatar's voice config
                       used to pick an appropriate emoji to append if missing.
        avatar_id: Avatar key (e.g. "goth_domme") for avatar-specific rules.
    """
    if not response or not response.strip():
        logger.warning("Guardrail: empty LLM response")
        return None

    text = response.strip()

    # 0. Replace em-dashes — telltale sign of AI-generated text
    text = text.replace("\u2014", "...").replace("\u2013", "-")  # — → ... and – → -

    # 1. Reject if AI self-reference found
    if _has_ai_reference(text):
        logger.warning("Guardrail: AI self-reference detected — falling back to template")
        return None

    # 2. Reject if AI vocabulary detected (signals bot generation, not human speech)
    if _has_ai_vocabulary(text):
        logger.warning("Guardrail: AI vocabulary detected — falling back to template")
        return None

    # 3. Reject if sycophantic opener detected
    if _has_sycophantic_opener(text):
        logger.warning("Guardrail: sycophantic opener detected — falling back to template")
        return None

    # 4. Reject if contact info found
    if _has_contact_info(text):
        logger.warning("Guardrail: contact info detected — falling back to template")
        return None

    # 4b. Reject if feminine endearment used toward male fan
    # Some avatars (e.g. goth_domme) use "darling" in-character, so use reduced pattern
    _fem_pattern = (
        _FEMININE_ENDEARMENT_PATTERN_NO_DARLING
        if avatar_id in _DARLING_ALLOWED_AVATARS
        else _FEMININE_ENDEARMENT_PATTERN
    )
    if _fem_pattern.search(text):
        logger.warning("Guardrail: feminine endearment detected — falling back to template")
        return None

    # 4c. Reject if system terminology found
    if _SYSTEM_TERMINOLOGY_PATTERN.search(text):
        logger.warning("Guardrail: system terminology leak detected — falling back to template")
        return None

    # 4d. Reject if content description reveals what's in a PPV
    if _CONTENT_REVEAL_PATTERN.search(text):
        logger.warning("Guardrail: content description leak — never reveal PPV contents")
        return None

    # 4e. Reject fake exclusivity claims ("I've never sent this to anyone")
    if _FAKE_EXCLUSIVITY_PATTERN.search(text):
        logger.warning("Guardrail: fake exclusivity detected — he knows she sends to others")
        return None

    # 4f. Reject "other fans" references ("my other fans don't hesitate")
    if _OTHER_FANS_PATTERN.search(text):
        logger.warning("Guardrail: other fans reference — kills intimacy illusion")
        return None

    # 5. Truncate to 3 sentences
    text = _truncate_to_sentences(text, max_sentences=3)

    # 5b. Avatar-specific post-processing
    if avatar_id == "goth_domme":
        # Strip disallowed emoji (only 💀🖤😈🙄😏🫠👀 allowed)
        text = _strip_disallowed_emoji(text, _GOTH_DOMME_ALLOWED_EMOJI)
        # Check goth_domme-specific banned phrases
        if _check_goth_domme_phrases(text):
            return None
        # Do NOT force-add emoji — she uses emoji ~1 in 4 messages
    else:
        # 6. Ensure at least one emoji (non-goth avatars)
        if not _has_emoji(text):
            text = _append_emoji(text, avatar_emojis)

    return text


# ─────────────────────────────────────────────
# State-specific guardrail checks
# ─────────────────────────────────────────────

# Price/dollar patterns — LLM must NEVER set prices
_PRICE_PATTERN = re.compile(
    r"\$\d|dollars?|bucks|\d+\s*(?:dollars|bucks)"
    r"|(?:costs?|price[ds]?|pay|paid|charge)\s+\d",
    re.IGNORECASE,
)

# Explicit content markers — blocked in QUALIFYING mode
_EXPLICIT_PATTERN = re.compile(
    r"\b(cock|dick|pussy|fuck|cum|orgasm|naked|nude|"
    r"stroking|masturbat|topless|nipple|ass\b(?!ist)|tits?|"
    r"ride you|suck|blow\s*job|wet for you)\b",
    re.IGNORECASE,
)

# Soft objection responses — blocked in OBJECTION mode (LLM must not cave)
_SOFT_OBJECTION_PATTERN = re.compile(
    r"\b(it's okay|that's okay|don't worry|no pressure|no worries|"
    r"I understand if you can't|take your time|whenever you're ready|"
    r"it's fine|totally fine|no rush|maybe later)\b",
    re.IGNORECASE,
)

# Feminine-only endearments — NEVER use toward male subscribers
# These are terms men use toward women; using them emasculates the fan's libido
_FEMININE_ENDEARMENT_PATTERN = re.compile(
    r"\b(mamas?|mami|sis|girl(?:ie)?|queen|girlfriend|bestie|honey|hon|hun|sweetie|sweetheart|darling)\b",
    re.IGNORECASE,
)

# Avatars that may use "darling" as a character-defining term of address
_DARLING_ALLOWED_AVATARS = {"goth_domme"}

# Reduced pattern without "darling" for avatars that use it in-character
_FEMININE_ENDEARMENT_PATTERN_NO_DARLING = re.compile(
    r"\b(mamas?|mami|sis|girl(?:ie)?|queen|girlfriend|bestie|honey|hon|hun|sweetie|sweetheart)\b",
    re.IGNORECASE,
)

# Fake exclusivity claims — NEVER claim she's never done this / he's the first
# Guys on OF/Fanvue know she sends content to others. Insulting their intelligence.
_FAKE_EXCLUSIVITY_PATTERN = re.compile(
    r"(?:I(?:'ve| have)? never (?:sent|shown|shared|done|let anyone|done this|showed))"
    r"|(?:you(?:'re| are) the (?:first|only) (?:person|one|guy|man))"
    r"|(?:(?:never|no one|nobody) (?:has )?(?:ever )?(?:seen|received) this)"
    r"|(?:I don'?t (?:usually|normally) (?:share|send|show) this)",
    re.IGNORECASE,
)

# Other fans/guys references — NEVER mention other subscribers during objections or anytime
# Reminds him he's one of many and kills the intimacy illusion
_OTHER_FANS_PATTERN = re.compile(
    r"\b(?:my )?(?:other )?(?:fans?|subscribers?|guys?|boys?|men|people|dudes?|followers?)"
    r"\s+(?:don'?t|never|always|would|wouldn'?t|usually|even)",
    re.IGNORECASE,
)

# Session-ending phrases — blocked in SELLING mode (LLM must not end session early)
_SESSION_END_PATTERN = re.compile(
    r"\b(goodnight|good night|gotta go|have to go|need to sleep|"
    r"going to bed|heading to bed|talk tomorrow|see you tomorrow|"
    r"bye bye|bye for now|sweet dreams|nighty night|"
    r"time for bed|sleepy|falling asleep)\b",
    re.IGNORECASE,
)

# Content revelation patterns — NEVER describe what's actually in a PPV
_CONTENT_REVEAL_PATTERN = re.compile(
    r"\b(that'?s me|this is me|you'?ll see me|watch me|it'?s me)\s+"
    r"(riding|fingering|touching|playing|cumming|orgasm|climax|squirt|using|with.{0,10}toy)",
    re.IGNORECASE,
)

# System terminology leaks — NEVER expose internal mechanics to subscribers
_SYSTEM_TERMINOLOGY_PATTERN = re.compile(
    r"\b(tier\s*\d|tier\s*(one|two|three|four|five|six)|"
    r"level\s*\d|ppv|pay.per.view|content\s*drop|"
    r"unlock\s*(level|tier|content)|"
    r"session\s*(number|#?\d)|pricing\s*ladder|"
    r"escalat(e|ion)\s*(tier|level|phase)|"
    r"conversion\s*rate|script\s*(factory|phase)|"
    r"template|state\s*machine|qualifying\s*phase|"
    r"warming\s*phase|looping\s*(state|phase)|"
    r"retention\s*(state|mode)|re.engagement\s*(state|mode)|"
    r"brokey\s*(flag|treatment)|timewaster|whale\s*score)\b",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────
# Tier-specific explicit word blocklists — ARCHITECTURAL enforcement
# These REGEX patterns are BLOCKED at each tier level regardless of what the LLM generates.
# Using regex instead of substring matching to catch contractions and variations.
# ─────────────────────────────────────────────

def _build_tier_patterns(word_list: list[str]) -> list[re.Pattern]:
    """Convert blocked word strings into regex patterns that handle contractions."""
    patterns = []
    for word in word_list:
        # Handle multi-word phrases with potential contractions/variations
        if " off" in word:
            # "top off" → matches "top off", "top's off", "tops off", "top came off", "top coming off"
            base = word.replace(" off", "")
            pattern = re.compile(
                rf"\b{re.escape(base)}'?s?\s+(?:off|coming\s+off|came\s+off|falls?\s+off)\b",
                re.IGNORECASE,
            )
        elif "taking " in word:
            # "taking off" → matches "taking off", "taking it off", "taking it all off", "taking this off"
            rest = word.replace("taking ", "")
            pattern = re.compile(
                rf"\btaking\s+(?:it\s+|this\s+|that\s+)?(?:all\s+)?{re.escape(rest)}\b",
                re.IGNORECASE,
            )
        elif "removing" in word or "slipping" in word or "pulled" in word:
            # Handle verb variations: removing/slipping/pulled + "off"
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        elif " " in word:
            # Multi-word phrase: use word boundaries
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        else:
            # Single word: word boundary match
            pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        patterns.append(pattern)
    return patterns


_TIER_BLOCKED_WORDS_RAW: dict[int, list[str]] = {
    0: ["pussy", "dick", "cock", "clit", "nipple", "nipples", "bare", "naked", "nude", "topless",
        "dripping", "wet for", "soaking", "fingering", "stroking", "orgasm", "cum", "cumming",
        "riding", "fuck me", "inside me", "spread", "moaning", "squirt",
        "comes off", "taking off", "take off", "removing", "slipping off", "pulled off",
        "top off", "shirt off", "bra off", "pants off", "panties off"],
    1: ["pussy", "clit", "naked", "nude", "topless", "bare chest", "bare breast",
        "dripping", "wet for", "soaking", "fingering", "orgasm", "cum", "cumming", "riding",
        "inside me", "spread", "squirt", "self-play",
        "comes off", "taking off", "take off", "removing", "slipping off", "pulled off",
        "top off", "shirt off", "bra off", "pants off", "panties off"],
    2: ["pussy", "clit", "naked below", "nude below", "wet for", "soaking", "fingering", "orgasm", "cum",
        "riding", "inside me", "spread legs", "squirt", "self-play", "touching myself down",
        "topless", "bare chest", "bare breast", "nipple", "nipples", "naked", "nude",
        "top off", "shirt off", "bra off",
        "taking off", "taking it all off",
        "fully bare", "completely naked", "nothing on"],
    3: ["pussy fully", "fingering myself", "orgasm", "cum", "riding", "toys",
        "squirt", "dildo", "vibrator", "climax",
        "pants off", "panties off", "bottoms off", "nothing below"],
    4: ["toys", "dildo", "vibrator", "climax", "orgasm", "squirt", "riding toy"],
    5: ["toy", "toys", "dildo", "vibrator", "climax", "orgasm", "riding toy"],
    6: [],
}

# Pre-compile regex patterns for each tier
_TIER_BLOCKED_PATTERNS: dict[int, list[re.Pattern]] = {
    tier: _build_tier_patterns(words)
    for tier, words in _TIER_BLOCKED_WORDS_RAW.items()
}


def _check_tier_boundary(text: str, tier_level: int) -> bool:
    """
    Return True if text PASSES tier boundary check.
    Return False if text contains words forbidden at this tier level.
    Uses regex patterns to catch contractions and variations.
    """
    if tier_level >= 6 or tier_level < 0:
        return True
    patterns = _TIER_BLOCKED_PATTERNS.get(tier_level, [])
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            logger.warning(
                "Guardrail [TIER %d]: blocked pattern '%s' matched '%s' in response",
                tier_level, pattern.pattern, match.group(),
            )
            return False
    return True


def _check_mode_specific(text: str, mode: GuardrailMode, avatar_id: str = "") -> bool:
    """
    Return True if the text PASSES mode-specific checks.
    Return False if it should be rejected.
    """
    # Universal check: system terminology leaks blocked in ALL modes
    if _SYSTEM_TERMINOLOGY_PATTERN.search(text):
        logger.warning("Guardrail: system terminology leak (%s)", _SYSTEM_TERMINOLOGY_PATTERN.search(text).group())
        return False

    # Universal check: feminine endearments blocked in ALL modes
    # Some avatars (e.g. goth_domme) use "darling" in-character
    _fem_pattern = (
        _FEMININE_ENDEARMENT_PATTERN_NO_DARLING
        if avatar_id in _DARLING_ALLOWED_AVATARS
        else _FEMININE_ENDEARMENT_PATTERN
    )
    if _fem_pattern.search(text):
        logger.warning("Guardrail: feminine endearment detected (emasculates male fan)")
        return False

    # Universal check: fake exclusivity blocked in ALL modes
    if _FAKE_EXCLUSIVITY_PATTERN.search(text):
        logger.warning("Guardrail: fake exclusivity detected (he knows she sends to others)")
        return False

    # Universal check: other fans references blocked in ALL modes
    if _OTHER_FANS_PATTERN.search(text):
        logger.warning("Guardrail: other fans reference detected (kills intimacy illusion)")
        return False

    if mode == GuardrailMode.QUALIFYING:
        if _EXPLICIT_PATTERN.search(text):
            logger.warning("Guardrail [QUALIFYING]: explicit content in qualifying response")
            return False
        if _PRICE_PATTERN.search(text):
            logger.warning("Guardrail [QUALIFYING]: price mention in qualifying response")
            return False

    elif mode == GuardrailMode.SELLING:
        if _PRICE_PATTERN.search(text):
            logger.warning("Guardrail [SELLING]: price mention in selling response")
            return False
        if _SESSION_END_PATTERN.search(text):
            logger.warning("Guardrail [SELLING]: session-ending phrase during selling — blocks early exit")
            return False
        if _CONTENT_REVEAL_PATTERN.search(text):
            logger.warning("Guardrail [SELLING]: content description leak — never reveal PPV contents")
            return False

    elif mode == GuardrailMode.OBJECTION:
        if _PRICE_PATTERN.search(text):
            logger.warning("Guardrail [OBJECTION]: price mention in objection response")
            return False
        if _SOFT_OBJECTION_PATTERN.search(text):
            logger.warning("Guardrail [OBJECTION]: soft/caving language in objection response")
            return False
        if _SESSION_END_PATTERN.search(text):
            logger.warning("Guardrail [OBJECTION]: session-ending phrase during objection — blocks early exit")
            return False

    # STANDARD mode has no additional checks beyond feminine endearments
    return True


# Map SubState values to GuardrailMode
_STATE_TO_MODE: dict[str, GuardrailMode] = {
    "new": GuardrailMode.QUALIFYING,
    "welcome_sent": GuardrailMode.QUALIFYING,
    "qualifying": GuardrailMode.QUALIFYING,
    "classified": GuardrailMode.QUALIFYING,
    "gfe_building": GuardrailMode.QUALIFYING,
    "sext_consent": GuardrailMode.QUALIFYING,
    "warming": GuardrailMode.SELLING,
    "tension_build": GuardrailMode.SELLING,
    "first_ppv_ready": GuardrailMode.SELLING,
    "first_ppv_sent": GuardrailMode.SELLING,
    "looping": GuardrailMode.SELLING,
    "custom_pitch": GuardrailMode.SELLING,
    "gfe_active": GuardrailMode.STANDARD,
    "post_session": GuardrailMode.STANDARD,
    "retention": GuardrailMode.STANDARD,
    "re_engagement": GuardrailMode.STANDARD,
    "cooled_off": GuardrailMode.STANDARD,
    "disqualified": GuardrailMode.STANDARD,
}


def get_mode_for_state(state_value: str) -> GuardrailMode:
    """Map a SubState value string to the appropriate GuardrailMode."""
    return _STATE_TO_MODE.get(state_value, GuardrailMode.STANDARD)


def post_process_stateful(
    response: str,
    mode: GuardrailMode = GuardrailMode.STANDARD,
    avatar_emojis: list[str] | None = None,
    fan_word_count: int = 0,
    tier_level: int = -1,
    avatar_id: str = "",
) -> str | None:
    """
    Apply all guardrails including state-specific checks.

    Wraps post_process() and adds mode-specific filtering.
    Used by route_full() for full-LLM mode.

    Args:
        response: Raw LLM output string.
        mode: GuardrailMode for state-specific checks.
        avatar_emojis: Optional emoji list from avatar voice config.
        fan_word_count: Word count of the fan's message. When the fan writes
                        a long emotional message (>30 words), allow more sentences
                        in the response to match their energy.
        tier_level: Current tier for boundary enforcement (-1 = skip check).
        avatar_id: Avatar key (e.g. "goth_domme") for avatar-specific rules.

    Returns:
        Clean, safe response string — or None if guardrails reject it.
    """
    if not response or not response.strip():
        return None

    text = response.strip()

    # 0. Replace em-dashes — telltale sign of AI-generated text
    text = text.replace("\u2014", "...").replace("\u2013", "-")

    # 1-4: Standard checks (AI self-ref, AI vocab, sycophantic, contact info)
    if _has_ai_reference(text):
        logger.warning("Guardrail: AI self-reference detected")
        return None
    if _has_ai_vocabulary(text):
        logger.warning("Guardrail: AI vocabulary detected")
        return None
    if _has_sycophantic_opener(text):
        logger.warning("Guardrail: sycophantic opener detected")
        return None
    if _has_contact_info(text):
        logger.warning("Guardrail: contact info detected")
        return None

    # 5: Mode-specific checks
    if not _check_mode_specific(text, mode, avatar_id=avatar_id):
        return None

    # 5b: Tier boundary enforcement (architectural — LLM cannot bypass)
    if tier_level >= 0 and not _check_tier_boundary(text, tier_level):
        logger.warning("Guardrail: tier %d boundary violation — rejecting", tier_level)
        return None

    # 6: Dynamic truncation — match fan's energy
    #    Short fan message (<15 words) → 3 sentences (snappy)
    #    Medium fan message (15-30 words) → 3-4 sentences
    #    Long fan message (>30 words) → 5 sentences (mirror depth)
    #    Selling/objection modes always get at least 4
    if fan_word_count > 30:
        max_sent = 5
    elif fan_word_count > 15:
        max_sent = 4
    else:
        max_sent = 3
    # Selling/objection modes get at least 4
    if mode in (GuardrailMode.SELLING, GuardrailMode.OBJECTION):
        max_sent = max(max_sent, 4)
    text = _truncate_to_sentences(text, max_sentences=max_sent)

    # 7: Avatar-specific emoji handling
    if avatar_id in _SPARSE_EMOJI_AVATARS:
        # Strip disallowed emoji for sparse-emoji avatars
        if avatar_id == "goth_domme":
            text = _strip_disallowed_emoji(text, _GOTH_DOMME_ALLOWED_EMOJI)
            # Check goth_domme-specific banned phrases
            if _check_goth_domme_phrases(text):
                return None
        # Do NOT force-add emoji — sparse emoji avatars don't need one in every message
    else:
        # Ensure at least one emoji for standard avatars
        if not _has_emoji(text):
            text = _append_emoji(text, avatar_emojis)

    return text
