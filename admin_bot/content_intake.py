"""
Massi-Bot Admin Bot - Content Intake (v2)

Handles the full content registration pipeline:
  1. Admin sends photo/video(s) via Telegram
  2. Bot asks: tier or continuation?
  3. Bot asks: session + tier number (if tier)
  4. Bot asks: describe the content (setting, outfit, mood)
  5. Bot uploads to Fanvue vault via API
  6. Bot registers Fanvue UUID in content_catalog
  7. Admin uploads same files to OF vault manually, sends to model's OF account
  8. Admin types /register_of — bot auto-pulls OF media IDs and registers them

Conversation states:
  WAITING_TYPE → WAITING_SESSION → WAITING_TIER → WAITING_DESCRIPTION → PROCESSING
"""

import os
import sys
import json
import logging
import uuid
import asyncio
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    CallbackQueryHandler, CommandHandler, filters,
)

from persistence.supabase_client import get_client
from onboarding import ContentTier, TIER_CONFIG
from admin_bot.alerts import alert_content_uploaded

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Conversation states
# ─────────────────────────────────────────────

WAITING_TYPE = 1
WAITING_SESSION = 2
WAITING_TIER = 3
WAITING_DESCRIPTION = 4

# Context data keys
_CTX_FILES = "ci_files"           # list of {file_id, media_type, file_unique_id}
_CTX_CONTENT_TYPE = "ci_type"     # "tier" or "continuation"
_CTX_SESSION = "ci_session"
_CTX_TIER = "ci_tier"
_CTX_GROUP_ID = "ci_group_id"     # media group ID for batch uploads
_CTX_GROUP_TIMER = "ci_group_timer"

# Constants
# OnlyFans user ID of the model account (used for /register_of media pull)
# Set via OF_MODEL_CHAT_ID env var or update this default
MODEL_OF_CHAT_ID = int(os.environ.get("OF_MODEL_CHAT_ID", "0"))
SOURCE_VALUE = "live"

_TIER_LABELS = {
    1: "Tier 1 -- Body Tease $27.38",
    2: "Tier 2 -- Top Tease $36.56",
    3: "Tier 3 -- Top Reveal $77.35",
    4: "Tier 4 -- Bottom Reveal $92.46",
    5: "Tier 5 -- Full Explicit $127.45",
    6: "Tier 6 -- Climax $200.00",
}

_TIER_PRICES_CENTS = {
    0: 2000,   # continuation
    1: 2738, 2: 3656, 3: 7735,
    4: 9246, 5: 12745, 6: 20000,
}


def _get_model_id() -> str:
    mid = os.environ.get("FANVUE_MODEL_ID", "")
    if not mid:
        raise RuntimeError("FANVUE_MODEL_ID not set in .env")
    return mid


def _get_model_short_name() -> str:
    return os.environ.get("MODEL_SHORT_NAME", "model")


# ─────────────────────────────────────────────
# Fanvue Upload
# ─────────────────────────────────────────────

def _get_fanvue_token() -> str:
    """Get current Fanvue access token from Redis."""
    import redis
    r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    raw = r.get("fanvue:tokens")
    if not raw:
        domain = os.environ.get("DOMAIN", "your-domain.com")
        raise RuntimeError(f"No Fanvue tokens in Redis. Re-authorize at https://{domain}/oauth/start")
    tokens = json.loads(raw)
    return tokens["access_token"]


async def _upload_to_fanvue(file_bytes: bytes, filename: str, content_type: str) -> Optional[str]:
    """
    Upload media to Fanvue via API.
    Returns the media UUID on success, None on failure.
    """
    try:
        token = _get_fanvue_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Fanvue-API-Version": "2025-06-26",
        }

        files = {"file": (filename, file_bytes, content_type)}

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.fanvue.com/media",
                headers=headers,
                files=files,
            )

        if resp.status_code not in (200, 201):
            logger.error("Fanvue upload failed: %d %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        # Extract UUID from response
        media_uuid = (
            data.get("data", {}).get("uuid")
            or data.get("uuid")
            or data.get("data", {}).get("id")
        )
        if media_uuid:
            logger.info("Fanvue upload success: %s -> %s", filename, media_uuid)
        return media_uuid

    except Exception as exc:
        logger.error("Fanvue upload error: %s", exc)
        return None


# ─────────────────────────────────────────────
# OF Media ID Pull
# ─────────────────────────────────────────────

async def pull_of_media_from_model_chat() -> list[dict]:
    """
    Get media IDs from the most recent creator-sent message
    in the model's chat on OnlyFans.
    """
    account_id = os.environ.get("OFAPI_ACCOUNT_ID", "")
    api_key = os.environ.get("OFAPI_KEY", "")
    base = os.environ.get("OFAPI_BASE", "https://app.onlyfansapi.com")

    if not account_id or not api_key:
        return []

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base}/api/{account_id}/chats/{MODEL_OF_CHAT_ID}/messages",
                headers=headers,
            )

        msgs = resp.json().get("data", [])

        for msg in msgs:
            media = msg.get("media", [])
            from_user = msg.get("fromUser", {})
            if media and from_user.get("id") != MODEL_OF_CHAT_ID:
                return [
                    {"id": str(m["id"]), "type": m.get("type", "photo")}
                    for m in media
                ]
    except Exception as exc:
        logger.error("OF media pull failed: %s", exc)

    return []


def _find_pending_of_bundle() -> Optional[str]:
    """Find the most recent bundle that has Fanvue UUIDs but no OF media IDs."""
    db = get_client()
    result = (
        db.table("content_catalog")
        .select("bundle_id")
        .not_.is_("fanvue_media_uuid", "null")
        .is_("of_media_id", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["bundle_id"]
    return None


def _register_of_ids(bundle_id: str, media_ids: list[dict]) -> int:
    """
    Match OF media IDs to existing content_catalog entries for this bundle.
    Entries already have Fanvue UUIDs -- we're adding the OF IDs.
    """
    db = get_client()

    result = (
        db.table("content_catalog")
        .select("id, media_type")
        .eq("bundle_id", bundle_id)
        .order("created_at")
        .execute()
    )

    entries = result.data or []
    updated = 0

    for i, entry in enumerate(entries):
        if i < len(media_ids):
            db.table("content_catalog").update({
                "of_media_id": media_ids[i]["id"],
            }).eq("id", entry["id"]).execute()
            updated += 1

    return updated


# ─────────────────────────────────────────────
# /register_of command
# ─────────────────────────────────────────────

async def cmd_register_of(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /register_of [bundle_id]

    Pulls the latest message sent to the model's OF account,
    extracts media IDs, and registers them in content_catalog.
    """
    args = context.args or []

    if args:
        bundle_id = args[0]
    else:
        bundle_id = _find_pending_of_bundle()
        if not bundle_id:
            await update.message.reply_text(
                "No pending bundles need OF registration.\n"
                "Usage: /register_of <bundle_id>"
            )
            return

    await update.message.reply_text("Pulling latest media from model chat...")

    media_ids = await pull_of_media_from_model_chat()

    if not media_ids:
        await update.message.reply_text(
            "No media found in latest model chat message.\n"
            "Did you send the files to the model's OF account?"
        )
        return

    updated = _register_of_ids(bundle_id, media_ids)

    await update.message.reply_text(
        f"Registered {updated} OF media IDs for bundle <code>{bundle_id}</code>\n"
        f"Media: {len(media_ids)} items ({sum(1 for m in media_ids if m['type'] == 'photo')} photos, "
        f"{sum(1 for m in media_ids if m['type'] == 'video')} videos)",
        parse_mode="HTML",
    )
    logger.info("Registered %d OF media IDs for bundle %s", updated, bundle_id)


# ─────────────────────────────────────────────
# Conversation handlers
# ─────────────────────────────────────────────

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point: admin sends a photo or video.
    Handles both single files and media groups (batches).
    """
    msg = update.message

    # Determine file info
    if msg.photo:
        file_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        media_type = "video"
    elif msg.document and msg.document.mime_type and (
        msg.document.mime_type.startswith("image/") or
        msg.document.mime_type.startswith("video/")
    ):
        file_id = msg.document.file_id
        media_type = "video" if msg.document.mime_type.startswith("video/") else "photo"
    else:
        return ConversationHandler.END

    # Initialize files list
    if _CTX_FILES not in context.user_data:
        context.user_data[_CTX_FILES] = []

    context.user_data[_CTX_FILES].append({
        "file_id": file_id,
        "media_type": media_type,
    })

    # Handle media groups (multiple files sent at once)
    media_group_id = msg.media_group_id
    if media_group_id:
        context.user_data[_CTX_GROUP_ID] = media_group_id

        # Cancel previous timer if exists
        old_timer = context.user_data.get(_CTX_GROUP_TIMER)
        if old_timer and not old_timer.done():
            old_timer.cancel()

        # Wait 2 seconds for more files in the group
        async def _ask_after_delay():
            await asyncio.sleep(2.0)
            count = len(context.user_data.get(_CTX_FILES, []))
            photos = sum(1 for f in context.user_data.get(_CTX_FILES, []) if f["media_type"] == "photo")
            videos = count - photos
            await msg.reply_text(
                f"Received <b>{count} files</b> ({photos} photos, {videos} videos)\n\n"
                "Is this for a <b>selling tier</b> or <b>continuation</b>?\n"
                "Reply: <code>tier</code> or <code>continuation</code>",
                parse_mode="HTML",
            )

        context.user_data[_CTX_GROUP_TIMER] = asyncio.create_task(_ask_after_delay())
        return WAITING_TYPE

    # Single file
    await msg.reply_text(
        "Received <b>1 file</b>\n\n"
        "Is this for a <b>selling tier</b> or <b>continuation</b>?\n"
        "Reply: <code>tier</code> or <code>continuation</code>",
        parse_mode="HTML",
    )
    return WAITING_TYPE


async def handle_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin replies with 'tier' or 'continuation'."""
    text = update.message.text.strip().lower()

    # Handle additional media arriving during type selection
    if update.message.photo or update.message.video:
        return await handle_media(update, context)

    if text in ("continuation", "cont", "c"):
        context.user_data[_CTX_CONTENT_TYPE] = "continuation"
        context.user_data[_CTX_SESSION] = 0
        context.user_data[_CTX_TIER] = 0
        await update.message.reply_text(
            "Continuation content.\n\n"
            "Describe the content briefly:\n"
            "Setting, outfit, mood\n\n"
            "Example: <i>bedroom selfies, casual outfits, girlfriend energy</i>",
            parse_mode="HTML",
        )
        return WAITING_DESCRIPTION

    if text in ("tier", "t", "selling"):
        context.user_data[_CTX_CONTENT_TYPE] = "tier"
        await update.message.reply_text(
            "Which <b>session number</b>? (1-12)",
            parse_mode="HTML",
        )
        return WAITING_SESSION

    await update.message.reply_text(
        "Please reply <code>tier</code> or <code>continuation</code>",
        parse_mode="HTML",
    )
    return WAITING_TYPE


async def handle_session_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin replies with session number."""
    text = update.message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 12):
        await update.message.reply_text("Please send a number between 1 and 12.")
        return WAITING_SESSION

    context.user_data[_CTX_SESSION] = int(text)

    keyboard = [
        [InlineKeyboardButton(_TIER_LABELS[t], callback_data=f"tier:{t}")]
        for t in range(1, 7)
    ]
    await update.message.reply_text(
        f"Session <b>{text}</b>. Pick the <b>content tier</b>:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return WAITING_TIER


async def handle_tier_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin taps a tier button."""
    query = update.callback_query
    await query.answer()

    tier_int = int(query.data.split(":")[1])
    context.user_data[_CTX_TIER] = tier_int

    await query.edit_message_text(
        f"Session {context.user_data[_CTX_SESSION]}, Tier {tier_int}.\n\n"
        "Describe the content:\n"
        "- <b>Setting</b> (bedroom, bathroom, mirror, etc.)\n"
        "- <b>Outfit</b> (black lingerie, white tank top, etc.)\n"
        "- <b>Mood</b> (teasing, confident, playful, etc.)\n"
        "- <b>Video</b> (what happens, if applicable)\n\n"
        "Example: <i>corner of bedroom, white tank top and jean skirt, just got home energy, posing for you</i>",
        parse_mode="HTML",
    )
    return WAITING_DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin describes the content. Process everything."""
    description = update.message.text.strip()
    files = context.user_data.get(_CTX_FILES, [])
    content_type = context.user_data.get(_CTX_CONTENT_TYPE, "tier")
    session = context.user_data.get(_CTX_SESSION, 1)
    tier = context.user_data.get(_CTX_TIER, 1)

    if not files:
        await update.message.reply_text("No files found. Start over by sending photos/videos.")
        _cleanup_context(context)
        return ConversationHandler.END

    model_id = _get_model_id()
    short_name = _get_model_short_name()

    # Build bundle ID
    if content_type == "continuation":
        bundle_id = f"{short_name}_continuation"
    else:
        bundle_id = f"{short_name}_s{session}_t{tier}"

    price_cents = _TIER_PRICES_CENTS.get(tier, 2738)

    await update.message.reply_text(
        f"Uploading {len(files)} files to Fanvue...",
    )

    # Upload each file to Fanvue and register in content_catalog
    db = get_client()
    uploaded = 0
    failed = 0
    fanvue_uuids = []

    for i, f in enumerate(files):
        try:
            # Download from Telegram
            tg_file = await update.message.get_bot().get_file(f["file_id"])
            file_bytes = await tg_file.download_as_bytearray()

            ext = "jpg" if f["media_type"] == "photo" else "mp4"
            content_type_header = "image/jpeg" if f["media_type"] == "photo" else "video/mp4"
            filename = f"{bundle_id}_{i+1}.{ext}"

            # Upload to Fanvue
            fv_uuid = await _upload_to_fanvue(bytes(file_bytes), filename, content_type_header)

            # Register in content_catalog
            row = {
                "model_id": model_id,
                "session_number": session,
                "tier": tier,
                "bundle_id": bundle_id,
                "fanvue_media_uuid": fv_uuid,
                "media_type": f["media_type"],
                "price_cents": price_cents,
                "source": SOURCE_VALUE,
                "bundle_context": description,
                "clothing_description": description,
                "mood": description,
            }
            db.table("content_catalog").insert(row).execute()

            if fv_uuid:
                fanvue_uuids.append(fv_uuid)
            uploaded += 1

        except Exception as exc:
            logger.error("Failed to process file %d: %s", i + 1, exc)
            failed += 1

    # Build result message
    photos = sum(1 for f in files if f["media_type"] == "photo")
    videos = len(files) - photos

    result_lines = [
        f"<b>Content registered!</b>\n",
        f"Bundle: <code>{bundle_id}</code>",
        f"Session: {session}, Tier: {tier}",
        f"Files: {uploaded} uploaded ({photos} photos, {videos} videos)",
        f"Fanvue: {'uploaded' if fanvue_uuids else 'FAILED (upload manually)'}",
        f"Price: ${price_cents / 100:.2f}",
    ]

    if failed:
        result_lines.append(f"\n{failed} files failed to upload")

    result_lines.extend([
        f"\n<b>Next step:</b>",
        f"1. Upload the same files to the OF vault",
        f"2. Send them to the model's OF account as a message (NOT PPV)",
        f"3. Type /register_of {bundle_id}",
    ])

    await update.message.reply_text("\n".join(result_lines), parse_mode="HTML")

    if uploaded > 0:
        try:
            await alert_content_uploaded(model_id, session, tier, bundle_id)
        except Exception:
            pass

    _cleanup_context(context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the content intake conversation."""
    _cleanup_context(context)
    await update.message.reply_text("Upload cancelled.")
    return ConversationHandler.END


def _cleanup_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clean up all conversation context data."""
    for key in (_CTX_FILES, _CTX_CONTENT_TYPE, _CTX_SESSION, _CTX_TIER,
                _CTX_GROUP_ID, _CTX_GROUP_TIMER):
        context.user_data.pop(key, None)


# ─────────────────────────────────────────────
# ConversationHandler factory
# ─────────────────────────────────────────────

def build_content_intake_handler() -> ConversationHandler:
    """
    Returns a ConversationHandler that manages the full content upload flow.
    """
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media),
            CommandHandler("upload", lambda u, c: u.message.reply_text(
                "Send photos/videos to begin the upload flow."
            )),
        ],
        states={
            WAITING_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_type_selection),
                MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media),
            ],
            WAITING_SESSION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_session_number),
            ],
            WAITING_TIER: [
                CallbackQueryHandler(handle_tier_selection, pattern=r"^tier:\d$"),
            ],
            WAITING_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="content_intake",
        persistent=False,
    )
