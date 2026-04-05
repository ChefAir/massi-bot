"""
Massi-Bot LLM — Prompt Cache Helper

Splits system prompts into static (cacheable) and dynamic (per-message)
portions for OpenRouter/Anthropic prompt caching.

Cached tokens cost 0.1x base input price (90% discount).
First request pays 1.25x for cache write; subsequent reads are 0.1x.
Cache TTL: 5 minutes (default) or 1 hour (extended).

Only works for Anthropic models (Claude Haiku, Sonnet, Opus) on OpenRouter.
Non-Anthropic models silently fall back to standard prompts.
"""

import logging

logger = logging.getLogger(__name__)

# Models that support Anthropic-style prompt caching on OpenRouter
_CACHEABLE_MODELS = {
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-haiku-4.5",
}


def is_cacheable_model(model: str) -> bool:
    """Check if a model supports prompt caching."""
    return any(m in model for m in ("anthropic/claude",))


def build_cached_system_message(
    static_prompt: str,
    dynamic_prompt: str,
    model: str = "",
) -> dict:
    """
    Build a system message with cache_control on the static portion.

    For Anthropic models on OpenRouter:
      - static_prompt gets cache_control: {"type": "ephemeral"}
      - dynamic_prompt is sent as a second text block (not cached)
      - Cached tokens cost 0.1x on reads (90% discount)

    For non-Anthropic models:
      - Falls back to a single content string (no caching)

    Args:
        static_prompt: Persona, personality, rules — stable across messages.
        dynamic_prompt: Subscriber context, memories, current state — changes each message.
        model: The model being called (to check caching support).

    Returns:
        A message dict ready for the messages array.
    """
    if is_cacheable_model(model):
        return {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": static_prompt,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": dynamic_prompt,
                },
            ],
        }
    else:
        # Non-Anthropic: standard single string
        return {
            "role": "system",
            "content": f"{static_prompt}\n\n{dynamic_prompt}",
        }


def split_system_prompt(full_prompt: str) -> tuple[str, str]:
    """
    Split a system prompt into static and dynamic portions.

    Heuristic: everything before "# SUBSCRIBER CONTEXT" is static
    (persona, personality, rules). Everything after is dynamic
    (subscriber data, memories, emotional baseline, current context).

    Returns:
        (static_prompt, dynamic_prompt) tuple.
    """
    # Try to split at SUBSCRIBER CONTEXT
    markers = [
        "# SUBSCRIBER CONTEXT",
        "# SUBSCRIBER",
        "# CONTEXT",
    ]

    for marker in markers:
        if marker in full_prompt:
            idx = full_prompt.index(marker)
            static = full_prompt[:idx].rstrip()
            dynamic = full_prompt[idx:]
            return static, dynamic

    # Fallback: treat entire prompt as dynamic (no caching benefit)
    logger.debug("Could not find split marker in system prompt — no caching applied")
    return "", full_prompt
