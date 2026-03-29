"""
Massi-Bot — Media Handler

Downloads and analyzes media from fan messages.
Returns structured text descriptions for the Media Reactor agent.

NOT an LLM agent — code + API calls only.

Supports: images, voice messages, videos, GIFs.
"""

import os
import io
import json
import base64
import logging
import tempfile
import subprocess
from typing import Optional
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

MAX_MEDIA_SIZE = 50 * 1024 * 1024  # 50MB limit


@dataclass
class MediaAnalysis:
    """Result of media analysis."""
    media_type: str              # "image", "voice", "video", "gif"
    description: str             # Human-readable description for the agent
    transcript: Optional[str]    # Voice/video audio transcript (None for images/gifs)
    is_explicit: bool            # Whether the media contains explicit/NSFW content
    is_selfie: bool              # Whether it appears to be a self-portrait
    mood: str                    # "flirty", "casual", "explicit", "emotional", "funny"
    raw_vision_output: str       # Full vision model output (for debugging)


# ─────────────────────────────────────────────
# VISION ANALYSIS (images, video frames, gifs)
# ─────────────────────────────────────────────

_VISION_MODELS = [
    "meta-llama/llama-3.2-11b-vision-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "x-ai/grok-2-vision-1212",
]

_VISION_PROMPT = """Describe this image in 1-2 sentences as if you're telling a friend what someone sent you in a private chat. Be natural and specific.

Focus on:
- Is this a selfie, mirror selfie, or photo of something else?
- What does the person look like? (build, clothing, expression, setting)
- Is this NSFW/explicit? If yes, describe in clinical terms (shirtless, nude, etc.)
- What mood does this convey? (flirty, casual, showing off, emotional, funny)

Examples:
- "Young man, shirtless selfie in bathroom mirror, muscular build, smiling"
- "Guy at a bar with friends, casual photo, wearing a baseball cap"
- "Explicit photo - nude male, taken from above"
- "Meme screenshot - funny text exchange about dating"
- "Landscape photo - sunset at a beach"

1-2 sentences max. Be brief and factual."""


async def analyze_image(image_bytes: bytes, content_type: str = "image/jpeg") -> MediaAnalysis:
    """Analyze an image using vision models."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return MediaAnalysis(
            media_type="image", description="Fan sent an image",
            transcript=None, is_explicit=False, is_selfie=False,
            mood="unknown", raw_vision_output="",
        )

    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=15.0,
    )

    for model in _VISION_MODELS:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }],
                max_tokens=150,
                temperature=0.0,
            )
            desc = response.choices[0].message.content.strip()

            desc_lower = desc.lower()
            is_explicit = any(w in desc_lower for w in [
                "nude", "naked", "explicit", "nsfw", "dick", "penis", "genitals",
                "shirtless", "underwear", "bulge",
            ])
            is_selfie = any(w in desc_lower for w in [
                "selfie", "mirror", "self-portrait", "taken of himself",
                "front camera", "self-shot",
            ])
            mood = _detect_mood(desc_lower)

            return MediaAnalysis(
                media_type="image",
                description=desc,
                transcript=None,
                is_explicit=is_explicit,
                is_selfie=is_selfie,
                mood=mood,
                raw_vision_output=desc,
            )
        except Exception as e:
            logger.warning("Vision model %s failed: %s", model, str(e)[:80])
            continue

    return MediaAnalysis(
        media_type="image", description="Fan sent an image (could not analyze)",
        transcript=None, is_explicit=False, is_selfie=False,
        mood="unknown", raw_vision_output="",
    )


# ─────────────────────────────────────────────
# SPEECH-TO-TEXT (voice messages, video audio)
# ─────────────────────────────────────────────

async def transcribe_audio(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Transcribe audio using Whisper (OpenAI or Groq fallback)."""
    # OpenAI Whisper
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            client = AsyncOpenAI(api_key=api_key, timeout=30.0)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = filename
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )
            return transcript.strip()
        except Exception as e:
            logger.warning("OpenAI Whisper failed: %s", str(e)[:80])

    # Groq Whisper fallback (free)
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=30.0) as http:
                resp = await http.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    files={"file": (filename, audio_bytes)},
                    data={"model": "whisper-large-v3", "response_format": "text"},
                )
                if resp.status_code == 200:
                    return resp.text.strip()
        except Exception as e:
            logger.warning("Groq Whisper failed: %s", str(e)[:80])

    return ""


# ─────────────────────────────────────────────
# VIDEO PROCESSING
# ─────────────────────────────────────────────

async def analyze_video(video_bytes: bytes) -> MediaAnalysis:
    """Analyze a video: extract key frame + audio, run vision + STT."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    frame_path = tmp_path.replace(".mp4", "_frame.jpg")
    audio_path = tmp_path.replace(".mp4", "_audio.ogg")

    try:
        import asyncio

        # Extract frame at 1 second (non-blocking)
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-i", tmp_path, "-ss", "1", "-frames:v", "1",
             "-q:v", "2", frame_path, "-y"],
            capture_output=True, timeout=15,
        )

        # Extract audio track (non-blocking)
        await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-i", tmp_path, "-vn", "-acodec", "libopus",
             audio_path, "-y"],
            capture_output=True, timeout=15,
        )

        # Analyze frame
        visual_analysis = None
        if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
            with open(frame_path, "rb") as f:
                visual_analysis = await analyze_image(f.read())

        # Transcribe audio
        transcript = ""
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            with open(audio_path, "rb") as f:
                transcript = await transcribe_audio(f.read(), "audio.ogg")

        visual_desc = visual_analysis.description if visual_analysis else "Video content"

        return MediaAnalysis(
            media_type="video",
            description=f"Video: {visual_desc}",
            transcript=transcript if transcript else None,
            is_explicit=visual_analysis.is_explicit if visual_analysis else False,
            is_selfie=visual_analysis.is_selfie if visual_analysis else False,
            mood=visual_analysis.mood if visual_analysis else "unknown",
            raw_vision_output=visual_desc,
        )
    finally:
        for path in [tmp_path, frame_path, audio_path]:
            try:
                os.unlink(path)
            except OSError:
                pass


# ─────────────────────────────────────────────
# GIF + VOICE PROCESSING
# ─────────────────────────────────────────────

async def analyze_gif(gif_bytes: bytes) -> MediaAnalysis:
    """Analyze a GIF by treating it as an image."""
    analysis = await analyze_image(gif_bytes, content_type="image/gif")
    analysis.media_type = "gif"
    return analysis


async def analyze_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> MediaAnalysis:
    """Process a voice message: transcribe and return."""
    transcript = await transcribe_audio(audio_bytes, filename)

    if not transcript:
        return MediaAnalysis(
            media_type="voice",
            description="Fan sent a voice message (could not transcribe)",
            transcript=None, is_explicit=False, is_selfie=False,
            mood="unknown", raw_vision_output="",
        )

    t_lower = transcript.lower()
    is_explicit = any(w in t_lower for w in [
        "fuck", "cock", "pussy", "cum", "hard", "wet", "horny", "dick",
    ])
    mood = "explicit" if is_explicit else _detect_mood(t_lower)

    return MediaAnalysis(
        media_type="voice",
        description=f'Voice message: "{transcript}"',
        transcript=transcript,
        is_explicit=is_explicit,
        is_selfie=False,
        mood=mood,
        raw_vision_output="",
    )


# ─────────────────────────────────────────────
# MEDIA DOWNLOAD FROM PLATFORM
# ─────────────────────────────────────────────

async def download_fanvue_media(media_url: str, access_token: str) -> Optional[bytes]:
    """Download media from Fanvue API using OAuth token."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.get(
                media_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "X-Fanvue-API-Version": "2025-06-26",
                },
            )
            if resp.status_code == 200 and len(resp.content) < MAX_MEDIA_SIZE:
                return resp.content
            logger.warning("Fanvue media download: status=%d size=%d", resp.status_code, len(resp.content))
    except Exception as e:
        logger.warning("Fanvue media download error: %s", str(e)[:80])
    return None


async def download_of_media(media_url: str) -> Optional[bytes]:
    """Download media from OnlyFansAPI.com or direct URL."""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
            headers = {}
            api_key = os.environ.get("OFAPI_KEY", "")
            if api_key and "onlyfansapi.com" in media_url:
                headers["Authorization"] = f"Bearer {api_key}"
            resp = await http.get(media_url, headers=headers)
            if resp.status_code == 200 and len(resp.content) < MAX_MEDIA_SIZE:
                return resp.content
            logger.warning("OF media download: status=%d size=%d", resp.status_code, len(resp.content))
    except Exception as e:
        logger.warning("OF media download error: %s", str(e)[:80])
    return None


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

async def process_media(
    media_url: str,
    media_type: str,
    platform: str,
    access_token: str = "",
) -> Optional[MediaAnalysis]:
    """
    Download and analyze media from a fan message.

    Args:
        media_url: URL to download the media from.
        media_type: "image", "voice", "video", or "gif"
        platform: "fanvue" or "onlyfans"
        access_token: OAuth token for Fanvue (not needed for OF).

    Returns:
        MediaAnalysis or None on download failure.
    """
    if not os.environ.get("MEDIA_PROCESSING_ENABLED", "").lower() == "true":
        return None

    # Download
    if platform == "fanvue":
        media_bytes = await download_fanvue_media(media_url, access_token)
    else:
        media_bytes = await download_of_media(media_url)

    if not media_bytes:
        return None

    # Analyze
    if media_type == "image":
        return await analyze_image(media_bytes)
    elif media_type == "voice":
        return await analyze_voice(media_bytes)
    elif media_type == "video":
        return await analyze_video(media_bytes)
    elif media_type == "gif":
        return await analyze_gif(media_bytes)
    else:
        logger.warning("Unknown media type: %s", media_type)
        return None


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def detect_media_type(attachment: dict) -> Optional[str]:
    """Detect media type from attachment metadata."""
    mime = (attachment.get("mimeType") or attachment.get("type") or
            attachment.get("content_type") or "").lower()
    url = (attachment.get("url") or attachment.get("src") or "").lower()
    kind = (attachment.get("kind") or attachment.get("mediaType") or "").lower()

    if "voice" in kind or "audio" in mime or url.endswith((".ogg", ".mp3", ".m4a", ".wav")):
        return "voice"
    if "video" in mime or "video" in kind or url.endswith((".mp4", ".mov", ".webm")):
        return "video"
    if "gif" in mime or url.endswith(".gif"):
        return "gif"
    if "image" in mime or url.endswith((".jpg", ".jpeg", ".png", ".webp")):
        return "image"

    return "image" if mime or url else None


def _detect_mood(text_lower: str) -> str:
    """Detect mood from description or transcript text."""
    if any(w in text_lower for w in [
        "nude", "naked", "explicit", "nsfw", "dick", "shirtless", "underwear",
    ]):
        return "explicit"
    if any(w in text_lower for w in [
        "flirt", "wink", "smil", "teas", "seductive", "sexy", "showing off",
    ]):
        return "flirty"
    if any(w in text_lower for w in ["laugh", "funny", "meme", "joke", "lol", "haha"]):
        return "funny"
    if any(w in text_lower for w in ["sad", "cry", "emotional", "miss", "lonely", "hurt"]):
        return "emotional"
    return "casual"
