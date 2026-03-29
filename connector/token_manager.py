"""
Massi-Bot - Fanvue OAuth Token Manager

Handles access/refresh token storage in Redis and proactive background refresh.
Tokens expire in 1 hour; we refresh at 55 minutes to stay ahead of expiry.

Multi-model support: tokens are stored per creator UUID.
  - fanvue:tokens:{creator_uuid}  -- per-model tokens
  - fanvue:tokens                 -- legacy key (migrated on first access)

Usage:
    await token_manager.ensure_started()   # call once on app startup
    token = await token_manager.get_access_token(creator_uuid)
"""

import os
import json
import time
import hmac
import asyncio
import logging
import base64
from typing import Optional, Dict

import httpx
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

LEGACY_REDIS_KEY = "fanvue:tokens"
REDIS_KEY_PREFIX = "fanvue:tokens:"
TOKEN_URL = "https://auth.fanvue.com/oauth2/token"
REFRESH_BEFORE_EXPIRY = 300   # refresh 5 min before expiry
REFRESH_INTERVAL = 55 * 60    # check every 55 minutes


def _extract_sub_from_jwt(access_token: str) -> Optional[str]:
    """Extract the 'sub' (creator UUID) from a Fanvue JWT without verification."""
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        payload = json.loads(base64.b64decode(payload_b64))
        return payload.get("sub")
    except Exception:
        return None


class TokenManager:
    """
    Manages Fanvue OAuth tokens with automatic proactive refresh.
    Backed by Redis for persistence across restarts.

    Multi-model: stores separate tokens per creator_uuid.
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        # Track all known creator UUIDs with tokens for background refresh
        self._known_creators: set[str] = set()

    def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                os.environ["REDIS_URL"],
                decode_responses=True,
            )
        return self._redis

    async def ensure_started(self):
        """Start the background refresh task. Call once on app startup."""
        # Migrate legacy tokens if they exist
        await self._migrate_legacy_tokens()
        # Discover all existing per-creator token keys
        await self._discover_token_keys()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh_loop())
            logger.info("Token refresh background task started (%d creators)",
                       len(self._known_creators))

    async def stop(self):
        """Cancel the background task on shutdown."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def get_access_token(self, creator_uuid: str = "") -> str:
        """
        Return the access token for a specific creator, refreshing if needed.
        If creator_uuid is empty, returns any available token (backwards compat).
        Raises RuntimeError if no tokens are stored.
        """
        if creator_uuid:
            tokens = await self._load_tokens(creator_uuid)
            if tokens is None:
                raise RuntimeError(
                    f"No Fanvue tokens for creator {creator_uuid[:8]}. "
                    "Log into this creator's Fanvue account and visit /oauth/start"
                )
            if time.time() >= tokens["expires_at"] - REFRESH_BEFORE_EXPIRY:
                logger.info("Token near expiry for %s — refreshing", creator_uuid[:8])
                return await self._do_refresh(tokens["refresh_token"], creator_uuid)
            return tokens["access_token"]

        # No creator specified — return any available token (legacy compat)
        for cid in self._known_creators:
            tokens = await self._load_tokens(cid)
            if tokens:
                if time.time() >= tokens["expires_at"] - REFRESH_BEFORE_EXPIRY:
                    return await self._do_refresh(tokens["refresh_token"], cid)
                return tokens["access_token"]
        raise RuntimeError(
            "No Fanvue tokens stored. Complete the OAuth flow by visiting /oauth/start"
        )

    async def has_tokens(self, creator_uuid: str = "") -> bool:
        """Check whether tokens are present for a creator (or any creator if empty)."""
        if creator_uuid:
            tokens = await self._load_tokens(creator_uuid)
            return tokens is not None
        return len(self._known_creators) > 0

    async def get_token_status(self) -> Dict[str, bool]:
        """Return {creator_uuid: has_valid_token} for all known creators."""
        status = {}
        for cid in self._known_creators:
            tokens = await self._load_tokens(cid)
            status[cid] = tokens is not None and time.time() < tokens.get("expires_at", 0)
        return status

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        """
        Exchange an authorization code for tokens.
        Auto-detects the creator UUID from the JWT 'sub' claim.
        """
        client_id = os.environ["FANVUE_CLIENT_ID"]
        client_secret = os.environ["FANVUE_CLIENT_SECRET"]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"https://{os.environ['DOMAIN']}/oauth/callback",
                    "code_verifier": code_verifier,
                },
                auth=(client_id, client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
        if resp.status_code != 200:
            logger.error(
                "OAuth token exchange failed: status=%d body=%s",
                resp.status_code, resp.text[:500],
            )
            resp.raise_for_status()

        token_data = resp.json()

        # Extract creator UUID from JWT
        creator_uuid = _extract_sub_from_jwt(token_data["access_token"])
        if creator_uuid:
            await self._store_tokens(token_data, creator_uuid)
            self._known_creators.add(creator_uuid)
            logger.info("OAuth exchange complete — tokens stored for creator %s",
                       creator_uuid[:8])
        else:
            # Fallback: store under legacy key
            await self._store_tokens(token_data, "")
            logger.warning("OAuth exchange complete — could not extract creator UUID from JWT")

        return token_data

    # ─────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────

    def _redis_key(self, creator_uuid: str) -> str:
        if creator_uuid:
            return f"{REDIS_KEY_PREFIX}{creator_uuid}"
        return LEGACY_REDIS_KEY

    async def _load_tokens(self, creator_uuid: str = "") -> Optional[dict]:
        try:
            raw = await self._get_redis().get(self._redis_key(creator_uuid))
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.error("Failed to load tokens from Redis: %s", exc)
            return None

    async def _store_tokens(self, token_data: dict, creator_uuid: str = ""):
        payload = {
            "access_token": token_data["access_token"],
            "refresh_token": token_data["refresh_token"],
            "expires_at": time.time() + token_data.get("expires_in", 3600),
            "stored_at": time.time(),
            "creator_uuid": creator_uuid,
        }
        try:
            await self._get_redis().set(
                self._redis_key(creator_uuid),
                json.dumps(payload),
                ex=7 * 24 * 3600,  # Redis key TTL = 7 days
            )
        except Exception as exc:
            logger.error("Failed to store tokens in Redis: %s", exc)

    async def _migrate_legacy_tokens(self):
        """Migrate legacy fanvue:tokens to per-creator key if possible."""
        try:
            raw = await self._get_redis().get(LEGACY_REDIS_KEY)
            if not raw:
                return
            tokens = json.loads(raw)
            creator_uuid = _extract_sub_from_jwt(tokens.get("access_token", ""))
            if creator_uuid:
                # Store under per-creator key
                await self._get_redis().set(
                    self._redis_key(creator_uuid),
                    raw,
                    ex=7 * 24 * 3600,
                )
                self._known_creators.add(creator_uuid)
                logger.info("Migrated legacy tokens to creator %s", creator_uuid[:8])
        except Exception as exc:
            logger.warning("Legacy token migration failed: %s", exc)

    async def _discover_token_keys(self):
        """Discover all fanvue:tokens:* keys in Redis."""
        try:
            keys = []
            async for key in self._get_redis().scan_iter(f"{REDIS_KEY_PREFIX}*"):
                keys.append(key)
            for key in keys:
                creator_uuid = key.replace(REDIS_KEY_PREFIX, "")
                if creator_uuid:
                    self._known_creators.add(creator_uuid)
            if self._known_creators:
                logger.info("Discovered tokens for %d creators: %s",
                           len(self._known_creators),
                           ", ".join(c[:8] for c in self._known_creators))
        except Exception as exc:
            logger.warning("Token key discovery failed: %s", exc)

    async def _do_refresh(self, refresh_token: str, creator_uuid: str = "") -> str:
        """Perform the refresh token exchange and return the new access token."""
        async with self._lock:
            # Re-read after acquiring lock — another coroutine may have refreshed
            tokens = await self._load_tokens(creator_uuid)
            if tokens and time.time() < tokens["expires_at"] - REFRESH_BEFORE_EXPIRY:
                return tokens["access_token"]

            client_id = os.environ["FANVUE_CLIENT_ID"]
            client_secret = os.environ["FANVUE_CLIENT_SECRET"]
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                    auth=(client_id, client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15.0,
                )

            if resp.status_code != 200:
                logger.error("Token refresh failed for %s: %d %s",
                           creator_uuid[:8] if creator_uuid else "legacy",
                           resp.status_code, resp.text)
                raise RuntimeError(f"Token refresh failed: {resp.status_code}")

            new_tokens = resp.json()
            # Detect creator from new token if not already known
            if not creator_uuid:
                creator_uuid = _extract_sub_from_jwt(new_tokens["access_token"]) or ""
            await self._store_tokens(new_tokens, creator_uuid)
            if creator_uuid:
                self._known_creators.add(creator_uuid)
            logger.info("Tokens refreshed for %s",
                       creator_uuid[:8] if creator_uuid else "legacy")
            return new_tokens["access_token"]

    async def _refresh_loop(self):
        """Background task: proactively refresh tokens for all creators."""
        while True:
            try:
                await asyncio.sleep(REFRESH_INTERVAL)
                for creator_uuid in list(self._known_creators):
                    tokens = await self._load_tokens(creator_uuid)
                    if tokens:
                        try:
                            await self._do_refresh(tokens["refresh_token"], creator_uuid)
                        except Exception as exc:
                            logger.error("Refresh failed for %s: %s",
                                        creator_uuid[:8], exc)
                    else:
                        logger.warning("No tokens for %s — skipping refresh",
                                      creator_uuid[:8])
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Background token refresh error: %s", exc)


# Singleton instance used by the connector
token_manager = TokenManager()
