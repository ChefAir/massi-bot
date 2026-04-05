"""
Massi-Bot LLM - Async Client

Provider abstraction layer supporting:
  - Venice.ai via OpenRouter (free default)
  - RunPod Serverless (upgrade path, OpenAI-compatible endpoint)

Both providers use the OpenAI client library — only the base_url and api_key differ.

Configuration via environment variables:
  LLM_PROVIDER = "venice" | "runpod"   (default: "venice")
  OPENROUTER_API_KEY                    (for Venice)
  RUNPOD_ENDPOINT_ID                    (for RunPod)
  RUNPOD_API_KEY                        (for RunPod)

Usage:
  client = LLMClient()
  response = await client.generate(messages, max_tokens=200, temperature=0.85)
  # Returns None on failure — triggers template fallback
"""

import os
import time
import logging
from typing import Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Provider defaults
# ─────────────────────────────────────────────

_PROVIDERS = {
    "venice": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "x-ai/grok-4.1-fast",
        "env_key": "OPENROUTER_API_KEY",
    },
}

# Ordered fallback list when primary model 429s or 404s.
# Paid models first (reliable, uncensored), free models as last resort.
_OPENROUTER_FALLBACKS = [
    "x-ai/grok-4.1-fast",                              # $0.20/$0.50/M — uncensored, instruction-following
    "x-ai/grok-4-fast",                                # $0.20/$0.50/M — fallback Grok
    "nousresearch/hermes-4-70b",                       # $0.13/$0.40/M — uncensored
    "meta-llama/llama-3.3-70b-instruct:free",           # free fallback
    "google/gemma-3-27b-it:free",                       # free fallback
]

_PROVIDERS["runpod"] = {
    "base_url_template": "https://api.runpod.ai/v2/{endpoint_id}/openai/v1",
    "model": "cognitivecomputations/Dolphin3.0-Llama3.1-8B",
    "env_key": "RUNPOD_API_KEY",
}

DEFAULT_MAX_TOKENS = 200
DEFAULT_TEMPERATURE = 0.7    # Research sweet spot: 0.6-0.8 (was 0.85 — too creative)
DEFAULT_FREQUENCY_PENALTY = 0.4  # Reduces repetitive phrases
DEFAULT_PRESENCE_PENALTY = 0.4   # Encourages topic variety
REQUEST_TIMEOUT = 15.0   # seconds — must be well under Telegram's 30s response window


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────

class LLMClient:
    """
    Async LLM client with provider abstraction and automatic failure handling.

    On any exception (rate limit, timeout, network error), generate() returns None
    so the caller can fall back to templates without crashing.
    """

    def __init__(self):
        provider_name = os.environ.get("LLM_PROVIDER", "venice").lower()
        if provider_name not in _PROVIDERS:
            logger.warning("Unknown LLM_PROVIDER '%s' — defaulting to venice", provider_name)
            provider_name = "venice"

        self._provider_name = provider_name
        self._client: Optional[AsyncOpenAI] = None
        self._model: str = ""
        self._available: bool = True   # flips to False on repeated failures
        # Fallback model rotation for 429 rate limits (OpenRouter/venice only)
        self._model_idx: int = 0
        self._retry_count: int = 0     # tracks retries within a single generate() call
        # Circuit breaker: track consecutive failures per model
        self._model_failures: dict[str, int] = {}  # model_name -> consecutive failure count
        self._model_cooldown: dict[str, float] = {}  # model_name -> cooldown_until timestamp

    def _get_client(self) -> tuple[AsyncOpenAI, str]:
        """Initialize and return the (AsyncOpenAI client, model_name) pair."""
        if self._client is not None:
            return self._client, self._model

        config = _PROVIDERS[self._provider_name]

        if self._provider_name == "venice":
            api_key = os.environ.get(config["env_key"], "")
            if not api_key:
                raise RuntimeError("OPENROUTER_API_KEY not set — LLM disabled")
            base_url = config["base_url"]
            # Use current fallback model (rotates on 429)
            # Circuit breaker: skip models in cooldown
            model = self._get_next_available_model()

        elif self._provider_name == "runpod":
            api_key = os.environ.get(config["env_key"], "")
            endpoint_id = os.environ.get("RUNPOD_ENDPOINT_ID", "")
            if not api_key or not endpoint_id:
                raise RuntimeError("RUNPOD_API_KEY or RUNPOD_ENDPOINT_ID not set")
            base_url = config["base_url_template"].format(endpoint_id=endpoint_id)
            model = os.environ.get("RUNPOD_MODEL", config["model"])
        else:
            raise RuntimeError(f"Unsupported provider: {self._provider_name}")

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=REQUEST_TIMEOUT,
        )
        self._model = model
        logger.info("LLM client initialized: provider=%s model=%s", self._provider_name, model)
        return self._client, self._model

    def _get_next_available_model(self) -> str:
        """Get the next model that isn't in cooldown. Circuit breaker pattern."""
        now = time.time()
        for i in range(len(_OPENROUTER_FALLBACKS)):
            idx = (self._model_idx + i) % len(_OPENROUTER_FALLBACKS)
            model = _OPENROUTER_FALLBACKS[idx]
            cooldown_until = self._model_cooldown.get(model, 0)
            if now >= cooldown_until:
                self._model_idx = idx
                return model
        # All models in cooldown — use primary anyway (cooldown will have expired by now for longest)
        logger.warning("All LLM models in cooldown — using primary %s", _OPENROUTER_FALLBACKS[0])
        self._model_idx = 0
        self._model_cooldown.clear()
        return _OPENROUTER_FALLBACKS[0]

    def _record_model_failure(self, model: str) -> None:
        """Record a failure for circuit breaker tracking."""
        count = self._model_failures.get(model, 0) + 1
        self._model_failures[model] = count
        if count >= 3:
            # Trip circuit breaker: cool down for 5 minutes
            self._model_cooldown[model] = time.time() + 300
            self._model_failures[model] = 0
            logger.warning("Circuit breaker tripped for %s — skipping for 5 minutes", model)

    def _record_model_success(self, model: str) -> None:
        """Reset failure count on success."""
        self._model_failures[model] = 0
        self._model_cooldown.pop(model, None)

    @property
    def is_available(self) -> bool:
        """False if the provider has been disabled due to missing config or repeated failures."""
        if not self._available:
            return False
        # Check that the required env var exists
        config = _PROVIDERS[self._provider_name]
        return bool(os.environ.get(config["env_key"]))

    async def generate(
        self,
        messages: list[dict],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        frequency_penalty: float = DEFAULT_FREQUENCY_PENALTY,
        presence_penalty: float = DEFAULT_PRESENCE_PENALTY,
    ) -> Optional[str]:
        """
        Generate a response from the LLM.

        Args:
            messages: List of {role, content} dicts (system + history + user).
            max_tokens: Maximum tokens in the response (default 200).
            temperature: Sampling temperature (0.7 — research-validated sweet spot).
            frequency_penalty: Reduces repetitive phrase patterns (0.4).
            presence_penalty: Encourages topic variety (0.4).

        Returns:
            Response text string, or None on any failure.
        """
        if not self.is_available:
            return None

        start = time.monotonic()
        try:
            client, model = self._get_client()
            completion = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)

            content = completion.choices[0].message.content
            tokens = getattr(completion.usage, "total_tokens", 0) if completion.usage else 0

            logger.info(
                "LLM response: provider=%s model=%s latency=%dms tokens=%d",
                self._provider_name, model, elapsed_ms, tokens,
            )
            self._retry_count = 0  # Reset on success
            self._record_model_success(model)
            return content

        except RuntimeError as exc:
            # Config error — disable permanently
            logger.error("LLM config error (disabling): %s", exc)
            self._available = False
            self._retry_count = 0
            return None

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            exc_str = str(exc)

            # 429 rate limit or 404 model not found — rotate to next fallback model
            # Max retries = number of fallback models (try each once)
            max_retries = len(_OPENROUTER_FALLBACKS)
            # Record failure for circuit breaker
            current_model = _OPENROUTER_FALLBACKS[self._model_idx % len(_OPENROUTER_FALLBACKS)]
            self._record_model_failure(current_model)

            if (("429" in exc_str or "404" in exc_str)
                    and self._provider_name == "venice"
                    and self._retry_count < max_retries):
                # Find next available model (circuit breaker aware)
                self._client = None
                self._model = ""
                self._model_idx = (self._model_idx + 1) % len(_OPENROUTER_FALLBACKS)
                next_model = self._get_next_available_model()
                logger.warning(
                    "429/404 on model %s — rotating to %s (retry %d/%d)",
                    current_model, next_model,
                    self._retry_count + 1, max_retries,
                )
                self._retry_count += 1
                return await self.generate(
                    messages, max_tokens, temperature,
                    frequency_penalty, presence_penalty,
                )

            logger.warning(
                "LLM request failed after %dms (%s: %s) — using template fallback",
                elapsed_ms, type(exc).__name__, exc_str[:150],
            )
            self._retry_count = 0  # Reset for next call
            return None

    async def generate_opus(
        self,
        messages: list[dict],
        max_tokens: int = 200,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        Generate a response using Claude Opus 4.6 via OpenRouter.

        Used as the primary generator in the 3-layer architecture:
        Opus generates (clean) → Grok uncensors → Opus validates.

        Opus excels at instruction-following, natural conversation,
        and reacting to context — but refuses explicit NSFW content.
        """
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            return None

        start = time.monotonic()
        try:
            # Use a separate client instance for Opus to avoid interfering with Grok's state
            client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=20.0,  # Opus may be slightly slower
            )
            completion = await client.chat.completions.create(
                model=os.environ.get("OPUS_MODEL", "anthropic/claude-sonnet-4-6"),
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = completion.choices[0].message.content
            tokens = getattr(completion.usage, "total_tokens", 0) if completion.usage else 0
            logger.info(
                "Opus response: latency=%dms tokens=%d",
                elapsed_ms, tokens,
            )
            return content
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "Opus generate failed after %dms: %s — falling back to Grok",
                elapsed_ms, str(exc)[:150],
            )
            return None


# Singleton instance — shared across requests
llm_client = LLMClient()
