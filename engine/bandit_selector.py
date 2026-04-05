"""
Massi-Bot Engine — Contextual Bandit Template Selector

Uses Thompson Sampling with Beta distributions to learn which
message templates perform best per context (avatar + state + time period).

Templates that drive engagement get selected more often.
Templates that kill conversations get deprioritized.
Learns automatically from outcome signals — no manual tuning needed.
"""

import logging
import hashlib
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Prior parameters (weakly informative — 1 success, 1 failure = uniform prior)
_ALPHA_PRIOR = 1.0
_BETA_PRIOR = 1.0


def _hash_template(text: str) -> str:
    """Stable hash for a template string."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _get_supabase():
    """Lazy Supabase client (avoids import-time failures)."""
    try:
        from persistence.supabase_client import get_client
        return get_client()
    except Exception:
        return None


def select_template(
    candidates: list[str],
    avatar_id: str = "",
    state: str = "",
    time_period: str = "",
) -> str:
    """
    Select the best template from candidates using Thompson Sampling.

    For each candidate, samples from its Beta(alpha, beta) posterior.
    Returns the candidate with the highest sample.
    Falls back to random selection if Supabase is unavailable.

    Args:
        candidates: List of template strings to choose from.
        avatar_id: Current avatar persona ID.
        state: Current conversation state (e.g., "warming", "looping").
        time_period: Current time period (e.g., "morning", "evening").

    Returns:
        The selected template string.
    """
    if not candidates:
        return ""
    if len(candidates) == 1:
        return candidates[0]

    sb = _get_supabase()
    if not sb:
        return candidates[np.random.randint(len(candidates))]

    # Load reward counts for all candidate hashes in this context
    hashes = [_hash_template(t) for t in candidates]

    try:
        result = sb.table("template_rewards") \
            .select("template_hash, successes, failures") \
            .eq("avatar_id", avatar_id) \
            .eq("state", state) \
            .eq("time_period", time_period) \
            .in_("template_hash", hashes) \
            .execute()

        reward_map = {}
        for row in (result.data or []):
            reward_map[row["template_hash"]] = (
                row.get("successes", 0),
                row.get("failures", 0),
            )
    except Exception as e:
        logger.debug("Bandit lookup failed (using random): %s", e)
        return candidates[np.random.randint(len(candidates))]

    # Thompson Sampling: sample from Beta posterior for each candidate
    best_idx = 0
    best_sample = -1.0

    for i, (template, thash) in enumerate(zip(candidates, hashes)):
        s, f = reward_map.get(thash, (0, 0))
        alpha = _ALPHA_PRIOR + s
        beta = _BETA_PRIOR + f
        sample = np.random.beta(alpha, beta)

        if sample > best_sample:
            best_sample = sample
            best_idx = i

    selected = candidates[best_idx]
    logger.debug(
        "Bandit selected template %s (sample=%.3f) from %d candidates [%s/%s/%s]",
        _hash_template(selected), best_sample, len(candidates),
        avatar_id, state, time_period,
    )
    return selected


def record_outcome(
    template_text: str,
    avatar_id: str = "",
    state: str = "",
    time_period: str = "",
    success: bool = True,
) -> None:
    """
    Record the outcome of a template interaction.

    Call this when you observe whether the subscriber responded
    (success=True) or went silent (success=False) after a template
    was sent.

    Args:
        template_text: The template string that was sent.
        avatar_id: Avatar persona ID.
        state: Conversation state when sent.
        time_period: Time period when sent.
        success: True if subscriber responded/purchased, False otherwise.
    """
    sb = _get_supabase()
    if not sb:
        return

    thash = _hash_template(template_text)
    col = "successes" if success else "failures"

    try:
        # Upsert: create row if not exists, increment the relevant counter
        existing = sb.table("template_rewards") \
            .select("id, successes, failures") \
            .eq("template_hash", thash) \
            .eq("avatar_id", avatar_id) \
            .eq("state", state) \
            .eq("time_period", time_period) \
            .execute()

        if existing.data:
            row = existing.data[0]
            new_val = row.get(col, 0) + 1
            sb.table("template_rewards") \
                .update({col: new_val, "updated_at": "now()"}) \
                .eq("id", row["id"]) \
                .execute()
        else:
            sb.table("template_rewards").insert({
                "template_hash": thash,
                "avatar_id": avatar_id,
                "state": state,
                "time_period": time_period,
                "successes": 1 if success else 0,
                "failures": 0 if success else 1,
            }).execute()
    except Exception as e:
        logger.debug("Bandit record_outcome failed: %s", e)
