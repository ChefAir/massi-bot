"""
Massi-Bot LLM - Typo Injector (U11)

Simulates natural mobile typing errors at a 2.3% character error rate
(Aalto University study on smartphone keyboard usage).

Error types (weighted):
  40%  Adjacent-key swap   — "teh" → "tge" (QWERTY proximity)
  25%  Transposition        — "the" → "teh" (finger swap)
  25%  Autocorrect failure  — "cant" → "can't" gone wrong, capitalization errors
  10%  Character omission   — "you" → "yo"

Self-correction (30% of errors):
  Sends the typo message, then a follow-up asterisk correction:
  msg1: "I thnk about you a lot 🥵"
  msg2: "*think"
  This is the #1 humanization signal per ACM CUI 2024 (Zhou & Leiva).

Note: This module only injects errors into LLM-generated text (GFE, retention,
re-engagement states). Template selling messages are NOT typo-injected — they
represent more "composed" messages rather than rapid-fire chat.

Source: Aalto University smartphone typing study; ACM CUI 2024 hesitation paper.
"""

import random
import string
from typing import Optional

# ─────────────────────────────────────────────
# QWERTY adjacent key map (lowercase)
# ─────────────────────────────────────────────

_ADJACENT_KEYS: dict[str, str] = {
    "q": "was",   "w": "qeasd",  "e": "wrsd",   "r": "etdf",   "t": "ryfg",
    "y": "tugh",  "u": "yijh",   "i": "uojk",   "o": "ipkl",   "p": "ol",
    "a": "qwszx", "s": "aedwxz", "d": "serfxc", "f": "drtgvc", "g": "ftyhvb",
    "h": "gyujbn", "j": "huikbn", "k": "jiolm",  "l": "kop",    "z": "asx",
    "x": "zasdc", "c": "xsdvf",  "v": "cfgb",   "b": "vghn",   "n": "bhjm",
    "m": "njk",
}

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────

TYPO_RATE = 0.000           # DISABLED — typos were getting detected as bot behavior in testing
SELF_CORRECTION_PROB = 0.30 # 30% chance typo triggers a follow-up correction
MIN_WORD_LENGTH = 5         # Don't corrupt short words (looks too obvious)
MAX_TYPOS_PER_MESSAGE = 0   # DISABLED — 0 typos per message


# ─────────────────────────────────────────────
# Error generators
# ─────────────────────────────────────────────

def _adjacent_key_swap(word: str) -> Optional[str]:
    """Replace one character with an adjacent QWERTY key."""
    candidates = [
        (i, c) for i, c in enumerate(word.lower())
        if c in _ADJACENT_KEYS and i > 0  # don't corrupt first char
    ]
    if not candidates:
        return None
    idx, char = random.choice(candidates)
    replacement = random.choice(_ADJACENT_KEYS[char])
    # Preserve original case
    if word[idx].isupper():
        replacement = replacement.upper()
    return word[:idx] + replacement + word[idx + 1:]


def _transposition(word: str) -> Optional[str]:
    """Swap two adjacent characters."""
    if len(word) < 3:
        return None
    # Pick a swap point (not first or last char to keep word recognizable)
    idx = random.randint(1, len(word) - 2)
    chars = list(word)
    chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
    return "".join(chars)


def _omission(word: str) -> Optional[str]:
    """Drop one interior character."""
    if len(word) < 4:
        return None
    idx = random.randint(1, len(word) - 2)
    return word[:idx] + word[idx + 1:]


def _autocorrect_failure(word: str) -> Optional[str]:
    """
    Simulate autocorrect going wrong. Simple heuristic: lowercase a word
    that would normally stay lowercase, or drop an apostrophe, or double
    a letter unexpectedly.
    """
    choices = []
    if "'" in word:
        # Remove the apostrophe (autocorrect removed it)
        choices.append(word.replace("'", ""))
    if len(word) > 3:
        # Double a random interior letter
        idx = random.randint(1, len(word) - 2)
        choices.append(word[:idx] + word[idx] + word[idx:])
    if not choices:
        return None
    return random.choice(choices)


def _corrupt_word(word: str) -> Optional[str]:
    """Apply one random error type to a word, weighted by research distribution."""
    r = random.random()
    if r < 0.40:
        return _adjacent_key_swap(word)
    elif r < 0.65:
        return _transposition(word)
    elif r < 0.90:
        return _autocorrect_failure(word)
    else:
        return _omission(word)


# ─────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────

class TypoResult:
    """Result from inject_typos — contains the (possibly modified) message
    and an optional self-correction follow-up."""
    __slots__ = ("message", "correction")

    def __init__(self, message: str, correction: Optional[str] = None):
        self.message = message
        self.correction = correction  # asterisk correction string, or None


def inject_typos(text: str) -> str:
    """
    Simple wrapper — returns just the (possibly typo-injected) string.
    For burst/correction support, use inject_typos_full().

    The caller (llm_router) can call inject_typos_full() if it wants
    to generate the self-correction follow-up message.
    """
    return inject_typos_full(text).message


def inject_typos_full(text: str) -> TypoResult:
    """
    Inject natural typing errors into an LLM-generated message.

    Returns a TypoResult with:
      .message    — the possibly-corrupted message to send first
      .correction — asterisk correction string to send after (or None)

    Example:
      text = "I think about you all the time"
      → TypoResult(message="I thnk about you all the time", correction="*think")
    """
    if not text or len(text) < 10:
        return TypoResult(text)

    words = text.split()
    eligible = [
        i for i, w in enumerate(words)
        if len(w.strip(string.punctuation)) >= MIN_WORD_LENGTH
        and w.isalpha()  # skip emoji/punctuation-heavy tokens
    ]

    if not eligible:
        return TypoResult(text)

    # Decide how many words to corrupt based on TYPO_RATE × total chars
    total_chars = sum(len(w) for w in words)
    expected_errors = total_chars * TYPO_RATE
    num_typos = min(int(expected_errors + 0.5), MAX_TYPOS_PER_MESSAGE)

    # Probabilistic: if expected < 1, use it as a probability
    if expected_errors < 1.0:
        if random.random() > expected_errors:
            return TypoResult(text)
        num_typos = 1

    if num_typos == 0:
        return TypoResult(text)

    # Apply corruption to randomly selected eligible words
    corrupt_indices = random.sample(eligible, min(num_typos, len(eligible)))
    corrupted_words = list(words)
    first_corrupted_original = None
    first_corrupted_new = None

    for idx in corrupt_indices:
        original = words[idx]
        corrupted = _corrupt_word(original)
        if corrupted and corrupted != original:
            corrupted_words[idx] = corrupted
            if first_corrupted_original is None:
                first_corrupted_original = original.lower().strip(string.punctuation)
                first_corrupted_new = corrupted

    result_text = " ".join(corrupted_words)

    # 30% chance: generate self-correction follow-up
    correction = None
    if (first_corrupted_original
            and first_corrupted_original != corrupted_words[corrupt_indices[0]]
            and random.random() < SELF_CORRECTION_PROB):
        correction = f"*{first_corrupted_original}"

    return TypoResult(message=result_text, correction=correction)
