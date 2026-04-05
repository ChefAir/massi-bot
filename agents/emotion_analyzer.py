"""
Massi-Bot Multi-Agent — Emotion Analyzer (Agent 1)

Analyzes the fan's emotional state, engagement level, and buy readiness
from their message. Runs in parallel with the Sales Strategist.

Model: Claude Opus 4.6 via OpenRouter
Cost: ~$0.02/call
Latency: 2-3s (parallel with Strategist, doesn't add to total)
"""

import os
import sys
import json
import logging
import time
from typing import Optional

from openai import AsyncOpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from models import Subscriber

logger = logging.getLogger(__name__)

_MODEL = os.environ.get("EMOTION_MODEL", "mistralai/mistral-small-3.1-24b-instruct")
_TIMEOUT = 10.0
_MAX_TOKENS = 150

_client: Optional[AsyncOpenAI] = None


def _get_client() -> Optional[AsyncOpenAI]:
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    _client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=_TIMEOUT,
    )
    return _client


_SYSTEM_PROMPT = """You are an emotional intelligence analyzer for a private messaging platform. Your job is to read a fan's message and output a structured emotional analysis.

You will receive:
- The fan's latest message
- Recent conversation history
- Basic subscriber profile

Output ONLY valid JSON with these fields:
{
  "emotion": "<primary emotion>",
  "engagement": <1-10>,
  "buy_readiness": <1-10>,
  "key_signals": ["<signal1>", "<signal2>"],
  "fan_time_of_day": "<time>"
}

EMOTION options: "aroused", "excited", "flirty", "curious", "neutral", "frustrated", "bored", "angry", "sad", "confused", "impatient", "grateful", "affectionate", "playful"

ENGAGEMENT scale:
1-2: Minimal (one-word replies, seems distracted)
3-4: Low (short replies, not asking questions)
5-6: Medium (conversational, responding to prompts)
7-8: High (initiating topics, asking questions, using emojis)
9-10: Very high (multiple messages, emotional investment, sharing personal details)

BUY_READINESS scale:
1-2: Not ready (just chatting, no desire signals)
3-4: Warming up (flirty but not asking for content)
5-6: Building desire (mentioning wanting to see more, physical reactions)
7-8: Ready (explicitly asking for content, describing physical arousal)
9-10: Desperate (begging, multiple messages about wanting content)

KEY_SIGNALS: Extract specific signals like "mentioned his name", "described physical arousal", "asked about content", "time reference (morning/night)", "shared personal detail", "expressed frustration", "used pet name", "sent multiple messages", "short reply", "emoji heavy"

FAN_TIME_OF_DAY: Based on what the fan says or implies. "morning", "afternoon", "evening", "night", or "unknown"

Output ONLY the JSON. No explanation."""


async def analyze_emotion(
    message: str,
    conversation_history: str,
    subscriber_summary: str,
) -> dict:
    """
    Analyze the fan's emotional state from their message.

    Returns:
        Dict with emotion, engagement, buy_readiness, key_signals, fan_time_of_day.
        Returns defaults on failure.
    """
    client = _get_client()
    if client is None:
        return _defaults()

    start = time.monotonic()
    try:
        user_content = f"""SUBSCRIBER PROFILE:
{subscriber_summary}

RECENT CONVERSATION:
{conversation_history}

FAN'S LATEST MESSAGE:
"{message}"

Analyze this message and output JSON."""

        completion = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=0.0,
        )

        raw = completion.choices[0].message.content.strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        # Parse JSON (strip markdown fences if present)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        logger.info(
            "Emotion analysis (%dms): emotion=%s engagement=%s buy_readiness=%s",
            elapsed_ms,
            result.get("emotion", "?"),
            result.get("engagement", "?"),
            result.get("buy_readiness", "?"),
        )
        return result

    except json.JSONDecodeError as e:
        logger.warning("Emotion analyzer JSON parse error: %s — raw: %s", e, raw[:100] if 'raw' in dir() else "?")
        return _defaults()
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Emotion analyzer failed (%dms): %s", elapsed_ms, str(e)[:100])
        return _defaults()


def _defaults() -> dict:
    return {
        "emotion": "neutral",
        "engagement": 5,
        "buy_readiness": 3,
        "key_signals": [],
        "fan_time_of_day": "unknown",
    }
