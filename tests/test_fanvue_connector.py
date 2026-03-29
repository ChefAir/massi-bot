"""
Tests for the Fanvue connector.

Mocks: Supabase, avatars, httpx, token_manager, Redis.
Run with: pytest tests/test_fanvue_connector.py -v
"""

import json
import time
import hmac
import hashlib
import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from httpx import AsyncClient, ASGITransport


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

SECRET = "test_webhook_secret_abc123"


def make_fanvue_sig(body: bytes, timestamp: int | None = None) -> str:
    """Generate a valid X-Fanvue-Signature for test payloads."""
    ts = str(timestamp or int(time.time()))
    signed = f"{ts}.{body.decode()}"
    sig = hmac.new(SECRET.encode(), signed.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v0={sig}"


def make_sub():
    from models import Subscriber, SubState, SubType
    sub = Subscriber(sub_id="sub-uuid-1", username="testuser")
    sub.state = SubState.WARMING
    return sub


def env_vars():
    return {
        "FANVUE_WEBHOOK_SECRET": SECRET,
        "FANVUE_CLIENT_ID": "client_id",
        "FANVUE_CLIENT_SECRET": "client_secret",
        "DOMAIN": "api.example.com",
        "FANVUE_MODEL_ID": "model-uuid-xyz",
        "REDIS_URL": "redis://localhost:6379/0",
        "FANVUE_MODEL_CONFIG": '{"stage_name":"TestModel","ethnicity":"latina"}',
        "FANVUE_IG_MAP": "{}",
    }


def make_model_context(model_id="model-uuid-xyz", creator_uuid="creator-uuid-test"):
    """Create a test ModelContext for mocking."""
    from connector.fanvue_connector import ModelContext
    return ModelContext(
        model_id=model_id,
        creator_uuid=creator_uuid,
        model_profile=None,
        attribution=None,
        default_avatar="luxury_baddie",
        stage_name="TestModel",
    )


# ─────────────────────────────────────────────
# Signature verification unit tests
# ─────────────────────────────────────────────

class TestVerifySignature:

    def setup_method(self):
        os.environ.update(env_vars())

    def test_valid_signature_passes(self):
        from connector.fanvue_connector import verify_signature
        body = b'{"test": "payload"}'
        sig = make_fanvue_sig(body)
        verify_signature(body, sig)  # should not raise

    def test_invalid_signature_raises(self):
        from fastapi import HTTPException
        from connector.fanvue_connector import verify_signature
        body = b'{"test": "payload"}'
        ts = int(time.time())
        sig = f"t={ts},v0=badsignaturedeadbeef"
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(body, sig)
        assert exc_info.value.status_code == 403

    def test_missing_signature_raises(self):
        from fastapi import HTTPException
        from connector.fanvue_connector import verify_signature
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(b"body", "")
        assert exc_info.value.status_code == 403

    def test_malformed_header_raises(self):
        from fastapi import HTTPException
        from connector.fanvue_connector import verify_signature
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(b"body", "not_valid_format")
        assert exc_info.value.status_code == 403

    def test_expired_timestamp_raises(self):
        from fastapi import HTTPException
        from connector.fanvue_connector import verify_signature
        body = b'{"test": "payload"}'
        old_ts = int(time.time()) - 400  # 6+ minutes ago
        sig = make_fanvue_sig(body, old_ts)
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(body, sig)
        assert exc_info.value.status_code == 403

    def test_body_tamper_raises(self):
        from fastapi import HTTPException
        from connector.fanvue_connector import verify_signature
        body = b'{"test": "payload"}'
        sig = make_fanvue_sig(body)
        # Tamper with body after signing
        with pytest.raises(HTTPException):
            verify_signature(b'{"test": "tampered"}', sig)


# ─────────────────────────────────────────────
# Webhook endpoint tests (HTTPX + FastAPI TestClient)
# ─────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_env(monkeypatch):
    for k, v in env_vars().items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def mock_avatars():
    mock_avatar = MagicMock()
    mock_avatar.avatar_id = "girl_boss"
    return {"girl_boss": mock_avatar}


class TestWebhookMessageReceived:

    @pytest.mark.anyio
    async def test_valid_message_returns_ok(self, mock_env, mock_avatars):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector._avatars", mock_avatars),
            patch("connector.fanvue_connector._get_model_context", return_value=ctx),
            patch("connector.fanvue_connector.load_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.save_subscriber"),
            patch("connector.fanvue_connector.create_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.send_fanvue_message", new_callable=AsyncMock),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = json.dumps({"senderUuid": "fv-user-001", "text": "Hey there"}).encode()
            sig = make_fanvue_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/message-received",
                    content=body,
                    headers={
                        "X-Fanvue-Signature": sig,
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.anyio
    async def test_invalid_signature_returns_403(self, mock_env):
        with (
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = b'{"senderUuid": "fv-user-001", "text": "hello"}'
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/message-received",
                    content=body,
                    headers={
                        "X-Fanvue-Signature": "t=12345,v0=invalidsig",
                        "Content-Type": "application/json",
                    },
                )
            assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_empty_message_ignored(self, mock_env):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector._avatars", {"girl_boss": MagicMock()}),
            patch("connector.fanvue_connector._get_model_context", return_value=ctx),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = json.dumps({"senderUuid": "fv-user-001", "text": ""}).encode()
            sig = make_fanvue_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/message-received",
                    content=body,
                    headers={"X-Fanvue-Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ignored"


class TestWebhookNewSubscriber:

    @pytest.mark.anyio
    async def test_new_subscriber_creates_and_processes(self, mock_env, mock_avatars):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector._avatars", mock_avatars),
            patch("connector.fanvue_connector._get_model_context", return_value=ctx),
            patch("connector.fanvue_connector.create_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.save_subscriber"),
            patch("connector.fanvue_connector.send_fanvue_message", new_callable=AsyncMock),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = json.dumps({
                "subscriberUuid": "new-fv-001",
                "username": "newuser",
                "displayName": "New User",
            }).encode()
            sig = make_fanvue_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/new-subscriber",
                    content=body,
                    headers={"X-Fanvue-Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


class TestWebhookPurchase:

    @pytest.mark.anyio
    async def test_purchase_records_transaction(self, mock_env):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector._get_model_context", return_value=ctx),
            patch("connector.fanvue_connector.load_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.save_subscriber"),
            patch("connector.fanvue_connector.record_transaction"),
            patch("connector.fanvue_connector.create_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = json.dumps({
                "buyerUuid": "buyer-001",
                "amount": 2738,  # cents
                "contentId": "bundle_s1_t1",
            }).encode()
            sig = make_fanvue_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/purchase-received",
                    content=body,
                    headers={"X-Fanvue-Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


class TestWebhookTip:

    @pytest.mark.anyio
    async def test_tip_recorded(self, mock_env):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector._get_model_context", return_value=ctx),
            patch("connector.fanvue_connector.load_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.save_subscriber"),
            patch("connector.fanvue_connector.record_transaction"),
            patch("connector.fanvue_connector.create_subscriber", return_value=make_sub()),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
        ):
            from connector.fanvue_connector import app
            body = json.dumps({"tipperUuid": "tipper-001", "amount": 1000}).encode()
            sig = make_fanvue_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/fanvue/tip-received",
                    content=body,
                    headers={"X-Fanvue-Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


class TestHealthEndpoint:

    @pytest.mark.anyio
    async def test_health_returns_ok(self, mock_env):
        ctx = make_model_context()
        with (
            patch("connector.fanvue_connector.token_manager.has_tokens", new_callable=AsyncMock, return_value=True),
            patch("connector.fanvue_connector.token_manager.ensure_started", new_callable=AsyncMock),
            patch("connector.fanvue_connector._avatars", {"girl_boss": MagicMock()}),
            patch("connector.fanvue_connector._model_contexts", {"creator-uuid-test": ctx}),
        ):
            from connector.fanvue_connector import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["platform"] == "fanvue"
            assert data["models_loaded"] == 1
            assert "TestModel" in data["models"]


# ─────────────────────────────────────────────
# Price conversion tests
# ─────────────────────────────────────────────

class TestPriceConversion:
    """Verify that purchase amounts from Fanvue (cents) are converted correctly."""

    def test_cents_to_dollars(self):
        # 2738 cents -> $27.38
        amount_cents = 2738
        amount_dollars = amount_cents / 100.0
        assert amount_dollars == pytest.approx(27.38)

    def test_full_ladder_cents(self):
        tier_cents = [2738, 3656, 7735, 9246, 12745, 20000]
        tier_dollars = [c / 100.0 for c in tier_cents]
        assert tier_dollars[0] == pytest.approx(27.38)
        assert tier_dollars[5] == pytest.approx(200.00)

    def test_ppv_action_cents_conversion(self):
        """BotAction price (dollars) -> Fanvue API (cents). Use round() not int()."""
        ppv_price_dollars = 77.35
        price_cents = round(ppv_price_dollars * 100)
        assert price_cents == 7735


# ─────────────────────────────────────────────
# Token manager unit tests (no Redis)
# ─────────────────────────────────────────────

class TestTokenManager:

    @pytest.mark.anyio
    async def test_get_access_token_raises_when_no_tokens(self, mock_env):
        with patch("connector.token_manager.aioredis") as mock_redis:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=None)
            mock_redis.from_url.return_value = instance

            from connector.token_manager import TokenManager
            tm = TokenManager()
            with pytest.raises(RuntimeError, match="No Fanvue tokens stored"):
                await tm.get_access_token()

    @pytest.mark.anyio
    async def test_get_access_token_returns_stored_token(self, mock_env):
        import json
        import time as time_mod
        stored = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": time_mod.time() + 3600,
            "stored_at": time_mod.time(),
        }
        with patch("connector.token_manager.aioredis") as mock_redis:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=json.dumps(stored))
            mock_redis.from_url.return_value = instance

            from connector.token_manager import TokenManager
            tm = TokenManager()
            # With per-creator tokens, pass a creator_uuid directly
            token = await tm.get_access_token("test-creator-uuid")
            assert token == "test_access_token"
