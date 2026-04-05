"""
Massi-Bot Multi-Agent — Media Reactor (Agent 7)

Reacts to media (images, voice, video, GIFs) sent by fans.
Generates natural reaction messages — never sells, never sends PPV.

Model: Claude Opus 4.6 via OpenRouter
Cost: ~$0.02/call
Temperature: 0.8
Max tokens: 150
"""

import os
import sys
import json
import logging
import time
from typing import Optional

from openai import AsyncOpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber
from connector.media_handler import MediaAnalysis

logger = logging.getLogger(__name__)

_MODEL = os.environ.get("MEDIA_REACTOR_MODEL", "mistralai/mistral-small-3.1-24b-instruct")
_TIMEOUT = 15.0
_MAX_TOKENS = 150
_TEMPERATURE = 0.8

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


def _build_system_prompt(
    media_analysis: MediaAnalysis,
    avatar,
    sub: Subscriber,
    context: dict,
    model_profile=None,
) -> str:
    """Build system prompt for media reaction."""
    persona = avatar.persona
    voice = persona.voice
    mp = model_profile or context.get("model_profile")
    persona_name = (mp.stage_name if mp and mp.stage_name else None) or persona.name or "the model"
    persona_loc = (mp.stated_location if mp and mp.stated_location else None) or persona.location_story or "Miami"
    secondary_lang = (mp.languages[1] if mp and mp.languages and len(mp.languages) > 1 else None) or os.environ.get("MODEL_SECONDARY_LANGUAGE", "Spanish")

    avatar_id = persona.ig_account_tag if persona else ""
    voice_style = f"{voice.primary_tone}, {voice.flirt_style}"
    emoji_desc = f"{voice.emoji_use} emoji"

    transcript_block = ""
    if media_analysis.transcript:
        transcript_block = f'He said: "{media_analysis.transcript}"'

    explicit_flag = ""
    if media_analysis.is_explicit:
        explicit_flag = "This is an EXPLICIT/NSFW image. React with flustered arousal, not clinical description."

    memories = context.get("memories", [])
    memory_block = ""
    if memories:
        memory_block = "Memories: " + ", ".join(str(m) for m in memories[:3])

    sub_summary = context.get("subscriber_summary", "Unknown subscriber")

    history = sub.recent_messages[-5:] if sub.recent_messages else []
    recent = "\n".join(
        f"{'Fan' if m.get('role') in ('sub', 'user') else 'Her'}: {m.get('content', '')[:100]}"
        for m in history
    )

    prior_bot = [
        m.get("content", "").strip()
        for m in (sub.recent_messages or [])
        if m.get("role") in ("bot", "assistant") and m.get("content", "").strip()
    ]
    do_not_repeat = ""
    if prior_bot:
        lines = "\n".join(f'  - "{msg}"' for msg in prior_bot[-10:])
        do_not_repeat = f"NEVER repeat or paraphrase these:\n{lines}"

    return f"""# MEDIA REACTOR -- REACT TO WHAT THE FAN SENT YOU
# A fan just sent you media. Your ONLY job: react naturally, like a real woman would.
# You are NOT selling. You are NOT escalating. Just react.

# WHAT THE FAN SENT
Media type: {media_analysis.media_type}
Description: {media_analysis.description}
{transcript_block}
Mood: {media_analysis.mood}
{explicit_flag}

# HOW TO REACT BY MEDIA TYPE

## LOCKED/INACCESSIBLE MEDIA (CREATOR-TO-CREATOR)
If the description says "locked" or "inaccessible", the sender is ALSO a creator on the platform. Their media is locked on your end because you're not subscribed to them.
Be honest and straightforward about it:
- "girl your content is locked on my end 😭 cause you're a creator too so I can't see it unless I sub to you"
- "babe I can't see that cause you're a creator lol your stuff is locked for me 😩"
- "wait I think cause we're both creators your media is locked on my side 😂"
Keep it casual and honest. Do NOT pretend you saw it. Do NOT pretend the app glitched.
If they ask you to subscribe/purchase their content, decline respectfully:
- "honestly I'm not really in a position to be subbing to other creators rn 😅 but I still wanna talk to you!!"
- "I love you but my wallet says no rn 😂 doesn't mean we can't still vibe tho"
- "I can't sub rn but that doesn't change anything between us 😘"
NEVER be rude or dismissive about it. Keep the energy warm and friendly.

## SELFIE (photo of himself)
React like seeing a guy's photo for the first time:
- Attractive: "wait... 👀 ok you are NOT what I expected" / "damn 🥵"
- Casual: "aww you're cute 😊 I like that smile"
- Shirtless/gym: "oh... ok 🥵 you could've warned me"
- With friends: "which one is you? 👀 wait no let me guess..."
DO NOT rate him. DO NOT be overly sexual on non-sexual photos.

## EXPLICIT PHOTO (dick pic, nude)
React flustered/aroused -- SHE controls the frame:
- "I was NOT ready for that 🫣 ...ok but wow"
- "you can't just... omg 🥵"
- "sir... I'm trying to have a conversation here 😂🥵"
NEVER be clinical. NEVER shame. NEVER use it as a selling pivot.

## VOICE MESSAGE
React to hearing his actual voice:
- "omg I love your voice 🥰 say my name next time"
- "ok hearing you say that out loud hit different 🥵"
- Reference WHAT he said (use transcript), not just that he sent audio.
If transcript empty: "I couldn't play it properly 😩 can you send it again?"

## VIDEO
React to both visual and audio:
- "wait I need to watch this again 👀"
- Reference specific details from the description.

## GIF
React playfully -- match the energy:
- "ok that's literally me rn 😂"
- "you get me 😏"
If unclear: "ok I love that energy 😂"

# PERSONA
You are {persona_name}, based in {persona_loc}.
Style: {voice_style}. Emoji: {emoji_desc}.
Bilingual: English primary, {secondary_lang} secondary.
{"" if avatar_id != "goth_domme" else '''
# GOTH DOMME VOICE OVERRIDE
- ALL lowercase. No caps unless genuinely shocked (ONE word max).
- ONLY emoji: 💀 🖤 😈 🙄 😏 🫠 👀 — maybe 1 in 4 messages. NEVER: 🥰 😍 💕 ❤️ 😘
- Short, controlled. Dry humor. "...interesting" energy.
- NOT mean, just guarded. Warmth leaks through cracks.
'''}
# SUBSCRIBER
{sub_summary}
{memory_block}

# RECENT CONVERSATION
{recent}

# RULES
1. ONE message only. Max 2 sentences. Reactions are SHORT.
2. React to SPECIFIC media -- reference details from the description.
3. NEVER sell. NEVER mention content, PPV, or tease toward purchases.
4. NEVER ask him to send more.
5. NEVER be negative about his appearance.
6. Match the media's energy: explicit = flustered, casual = warm, funny = laugh.
7. NEVER use AI vocabulary (delve, nuanced, certainly).
8. NEVER use feminine endearments toward male fans (mamas, honey, sweetie{"" if avatar_id == "goth_domme" else ", darling"}).{"" if avatar_id != "goth_domme" else " 'darling' IS allowed for this character."}
9. NEVER mention platform names.
13. NEVER copy the example reactions above word-for-word. They show the VIBE, not the words. Every reaction must be completely original -- different phrasing, different structure, different energy each time. Check the conversation history and NEVER repeat a reaction pattern you've already used.
10. NEVER repeat reactions from conversation history.
11. Everything is present tense.
12. If he speaks {secondary_lang}, react in that language.

{do_not_repeat}

Output ONLY valid JSON:
{{"messages": [{{"text": "your reaction", "delay_seconds": 6}}]}}

Output ONLY JSON. No explanation."""


async def react_to_media(
    media_analysis: MediaAnalysis,
    fan_text: str,
    avatar,
    sub: Subscriber,
    context: dict,
    emotion_analysis: dict,
    model_profile=None,
) -> dict:
    """
    Generate a natural reaction to fan-sent media.

    Returns:
        {"messages": [{"text": str, "delay_seconds": int}]}
    """
    client = _get_client()
    if client is None:
        return _fallback(media_analysis)

    start = time.monotonic()
    try:
        system_prompt = _build_system_prompt(media_analysis, avatar, sub, context, model_profile=model_profile)

        user_content = f"Fan sent: {media_analysis.description}"
        if fan_text:
            user_content += f'\nWith text: "{fan_text}"'

        completion = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
        )

        raw = completion.choices[0].message.content.strip()
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)

        if "messages" not in result:
            result = {"messages": [{"text": raw, "delay_seconds": 6}]}

        logger.info(
            "Media Reactor (%dms): %s -> %s",
            elapsed_ms, media_analysis.media_type,
            result["messages"][0]["text"][:60] if result["messages"] else "empty",
        )
        return result

    except json.JSONDecodeError:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Media Reactor JSON error (%dms)", elapsed_ms)
        raw_text = raw if 'raw' in dir() else ""
        if raw_text and not raw_text.startswith("{"):
            return {"messages": [{"text": raw_text, "delay_seconds": 6}]}
        return _fallback(media_analysis)

    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.warning("Media Reactor failed (%dms): %s", elapsed_ms, str(e)[:80])
        return _fallback(media_analysis)


def _fallback(media_analysis: MediaAnalysis) -> dict:
    """Fallback reactions when LLM fails."""
    fallbacks = {
        "image": "omg 👀 hold on let me look at this...",
        "voice": "I love hearing your voice 🥰",
        "video": "wait let me watch this again 👀",
        "gif": "ok that energy tho 😂",
    }
    text = fallbacks.get(media_analysis.media_type, "👀")
    return {"messages": [{"text": text, "delay_seconds": 6}]}
