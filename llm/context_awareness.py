"""
Massi-Bot LLM - Live Context Awareness

Provides real-time time, weather, and day context for system prompts.
Detects fan's apparent time of day from their messages.
Uses Open-Meteo API (free, no API key needed, no rate limits for reasonable usage).
"""

import re
import time
import logging
from datetime import datetime
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Fan time detection from messages
# ─────────────────────────────────────────────

_MORNING_SIGNALS = re.compile(
    r"\b(morning|wak(?:e|ing) up|just woke|sunrise|breakfast|coffee|"
    r"kids? (?:are |is )?(?:waking|getting) up|getting ready|"
    r"heading to work|on my way to work|before work|"
    r"start(?:ing)? my day|early)\b",
    re.IGNORECASE,
)

_AFTERNOON_SIGNALS = re.compile(
    r"\b(afternoon|lunch|midday|after school|"
    r"on (?:my )?break|work break|back from lunch)\b",
    re.IGNORECASE,
)

_EVENING_SIGNALS = re.compile(
    r"\b(evening|dinner|after work|got home|just got home|"
    r"cooking dinner|watching tv|relaxing after|wind(?:ing)? down)\b",
    re.IGNORECASE,
)

_NIGHT_SIGNALS = re.compile(
    r"\b(night|bedtime|going to (?:bed|sleep)|about to sleep|"
    r"can't sleep|in bed|laying in bed|late|"
    r"kids? (?:are |is )?(?:asleep|sleeping|in bed)|"
    r"goodnight|nighty|tucked in)\b",
    re.IGNORECASE,
)


def detect_fan_time(message: str) -> Optional[str]:
    """
    Detect the fan's apparent time of day from their message.
    Returns: 'morning', 'afternoon', 'evening', 'night', or None if unclear.
    """
    if _MORNING_SIGNALS.search(message):
        return "morning"
    if _AFTERNOON_SIGNALS.search(message):
        return "afternoon"
    if _EVENING_SIGNALS.search(message):
        return "evening"
    if _NIGHT_SIGNALS.search(message):
        return "night"
    return None


def detect_fan_time_from_history(recent_messages: list) -> Optional[str]:
    """Check recent messages (last 5) for time signals."""
    for msg in reversed(recent_messages[-5:]):
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        detected = detect_fan_time(content)
        if detected:
            return detected
    return None


# ─────────────────────────────────────────────
# Weather API (Open-Meteo - free, no key needed)
# ─────────────────────────────────────────────

# City coordinates + timezone for avatar/model locations
_CITY_COORDS = {
    "miami": (25.76, -80.19, "US/Eastern"),
    "nyc": (40.71, -74.01, "US/Eastern"),
    "new york": (40.71, -74.01, "US/Eastern"),
    "la": (34.05, -118.24, "US/Pacific"),
    "los angeles": (34.05, -118.24, "US/Pacific"),
    "austin": (30.27, -97.74, "US/Central"),
    "nashville": (36.16, -86.78, "US/Central"),
    "dallas": (32.78, -96.80, "US/Central"),
    "atlanta": (33.75, -84.39, "US/Eastern"),
    "chicago": (41.88, -87.63, "US/Central"),
    "denver": (39.74, -104.99, "US/Mountain"),
    "las vegas": (36.17, -115.14, "US/Pacific"),
    "vegas": (36.17, -115.14, "US/Pacific"),
    "phoenix": (33.45, -112.07, "US/Arizona"),
    "virginia": (37.54, -77.44, "US/Eastern"),
    "portland": (45.52, -122.68, "US/Pacific"),
}

# Cache weather results for 30 minutes
_weather_cache: dict = {}
_CACHE_TTL = 1800  # 30 minutes


def _parse_city(location_story: str) -> Optional[tuple]:
    """Extract first recognized city from location string. Returns (lat, lon, timezone)."""
    lower = location_story.lower()
    for city, data in _CITY_COORDS.items():
        if city in lower:
            return data
    return None


async def get_weather(location_story: str) -> Optional[dict]:
    """
    Get current weather for the avatar's city via Open-Meteo API.
    Free, no API key needed.
    Returns: {temp_f, description, is_day} or None.
    """
    coords = _parse_city(location_story)
    if not coords:
        return None

    cache_key = f"{coords[0]},{coords[1]}"
    cached = _weather_cache.get(cache_key)
    if cached and time.time() - cached["fetched_at"] < _CACHE_TTL:
        return cached["data"]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": coords[0],
                    "longitude": coords[1],
                    "current": "temperature_2m,is_day,weather_code",
                    "temperature_unit": "fahrenheit",
                    "timezone": "auto",
                },
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            current = data.get("current", {})
            temp_f = current.get("temperature_2m", 0)
            is_day = current.get("is_day", 1)
            code = current.get("weather_code", 0)

            # WMO weather code to description
            desc = _wmo_description(code)

            result = {
                "temp_f": round(temp_f),
                "description": desc,
                "is_day": bool(is_day),
            }
            _weather_cache[cache_key] = {"data": result, "fetched_at": time.time()}
            return result

    except Exception as exc:
        logger.debug("Weather fetch failed: %s", exc)
        return None


def _wmo_description(code: int) -> str:
    """Convert WMO weather code to simple description."""
    if code == 0:
        return "clear sky"
    elif code in (1, 2, 3):
        return "partly cloudy"
    elif code in (45, 48):
        return "foggy"
    elif code in (51, 53, 55, 56, 57):
        return "drizzle"
    elif code in (61, 63, 65, 66, 67):
        return "rainy"
    elif code in (71, 73, 75, 77):
        return "snowing"
    elif code in (80, 81, 82):
        return "rain showers"
    elif code in (85, 86):
        return "snow showers"
    elif code in (95, 96, 99):
        return "thunderstorm"
    return "cloudy"


# ─────────────────────────────────────────────
# Build context block for system prompt
# ─────────────────────────────────────────────

def build_context_block(
    fan_messages: list,
    avatar_location: str,
    weather: Optional[dict] = None,
) -> str:
    """
    Build a real-time context block for the system prompt.
    Includes: current time/day in the model's timezone, fan's apparent time, weather.
    """
    # Get timezone-aware time for the model's location
    city_data = _parse_city(avatar_location)
    if city_data and len(city_data) >= 3:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(city_data[2]))
        except (ImportError, KeyError):
            now = datetime.now()
    else:
        now = datetime.now()

    parts = []

    # Current day + general time period (NEVER exact time — prevents timezone leaks)
    day_name = now.strftime("%A")
    hour = now.hour
    if 5 <= hour < 12:
        period = "morning"
    elif 12 <= hour < 17:
        period = "afternoon"
    elif 17 <= hour < 21:
        period = "evening"
    else:
        period = "night"
    parts.append(f"It's {day_name} {period}.")
    parts.append("NEVER state a specific time (e.g., '6am', '2:42'). If asked what time it is, deflect playfully ('too late lol', 'late enough that I should be sleeping'). Revealing exact time can contradict the fan's timezone.")

    # Weather
    if weather:
        parts.append(f"Weather: {weather['temp_f']}°F, {weather['description']}.")

    # Fan's apparent time of day — ONLY used for anti-contradiction, NOT for proactive time references
    fan_time = detect_fan_time_from_history(fan_messages)
    if fan_time:
        parts.append(f"The fan seems to be in {fan_time} time.")
        if fan_time == "morning":
            parts.append("Do NOT say goodnight or sleep references — contradicts his time.")
        elif fan_time == "night":
            parts.append("Do NOT say good morning — contradicts his time.")

    # IMPORTANT: Do NOT proactively reference time of day, weather, or timezone differences.
    # Most people assume others are on the same time as them.
    # Only mirror the fan's time references if HE brings them up first.
    # NEVER say "goodnight" unless the fan says it first.
    # NEVER initiate morning/evening/night references unprompted.
    parts.append("⚠️ Do NOT initiate time-of-day or weather references. Only respond to time if the fan mentions it first.")

    return "\n".join(parts)
