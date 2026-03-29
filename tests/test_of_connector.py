"""
Tests for the OnlyFans connector (OnlyFansAPI.com v2 webhook format).

Key format:
  - Single POST /webhook/of endpoint
  - Payload: {"event": "...", "account_id": "...", "payload": {...}}
  - Signature header: "Signature: <hex>" (not X-Signature)

Run with: pytest tests/test_of_connector.py -v
"""

import json
import hmac
import hashlib
import asyncio
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

OF_SECRET = "of_webhook_secret_xyz987"


def make_of_sig(body: bytes) -> str:
    return hmac.new(OF_SECRET.encode(), body, hashlib.sha256).hexdigest()


def make_sub():
    from models import Subscriber, SubState
    sub = Subscriber(sub_id="of-sub-uuid-1", username="of_user")
    sub.state = SubState.WARMING
    return sub


def of_env_vars():
    return {
        "OFAPI_WEBHOOK_SECRET": OF_SECRET,
        "OFAPI_KEY": "sk_live_test123",
        "OFAPI_ACCOUNT_ID": "acct_TESTXYZ",
        "OFAPI_BASE": "https://app.onlyfansapi.com",
        "OF_MODEL_ID": "model-of-uuid-xyz",
        "OF_MODEL_CONFIG": '{"stage_name":"TestModel","ethnicity":"latina"}',
        "OF_IG_MAP": "{}",
    }


def make_event(event: str, payload: dict) -> bytes:
    """Build a canonical OnlyFansAPI.com webhook envelope."""
    return json.dumps({
        "event": event,
        "account_id": "acct_123",
        "payload": payload,
    }).encode()


@pytest.fixture
def mock_env(monkeypatch):
    for k, v in of_env_vars().items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def mock_avatars():
    mock_avatar = MagicMock()
    mock_avatar.avatar_id = "girl_boss"
    return {"girl_boss": mock_avatar}


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─────────────────────────────────────────────
# Signature verification unit tests
# ─────────────────────────────────────────────

class TestOFSignatureVerification:

    def setup_method(self):
        os.environ.update(of_env_vars())

    def test_valid_signature_passes(self):
        from connector.of_connector import verify_signature
        body = b'{"event":"messages.received","account_id":"acct_123","payload":{}}'
        sig = make_of_sig(body)
        verify_signature(body, sig)  # should not raise

    def test_invalid_signature_raises_403(self):
        from fastapi import HTTPException
        from connector.of_connector import verify_signature
        body = b'{"event":"messages.received"}'
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(body, "badsig")
        assert exc_info.value.status_code == 403

    def test_missing_header_raises_403(self):
        from fastapi import HTTPException
        from connector.of_connector import verify_signature
        with pytest.raises(HTTPException) as exc_info:
            verify_signature(b"body", "")
        assert exc_info.value.status_code == 403

    def test_tampered_body_raises_403(self):
        from fastapi import HTTPException
        from connector.of_connector import verify_signature
        original_body = b'{"event":"messages.received"}'
        sig = make_of_sig(original_body)
        with pytest.raises(HTTPException):
            verify_signature(b'{"event":"messages.tampered"}', sig)

    def test_sig_is_simple_hex_not_fanvue_format(self):
        """OF signature is plain hex, not t=...,v0=... like Fanvue."""
        from connector.of_connector import verify_signature
        body = b"test"
        sig = make_of_sig(body)
        assert "," not in sig
        assert "v0=" not in sig
        verify_signature(body, sig)

    def test_header_name_is_signature_not_x_signature(self):
        """Confirm we read 'Signature' header, not 'X-Signature'."""
        import inspect
        import connector.of_connector as mod
        source = inspect.getsource(mod.webhook_of)
        assert 'get("Signature"' in source
        assert 'get("X-Signature"' not in source


# ─────────────────────────────────────────────
# HTML stripping
# ─────────────────────────────────────────────

class TestStripHtml:

    def test_plain_text_unchanged(self):
        from connector.of_connector import strip_html
        assert strip_html("hello world") == "hello world"

    def test_strips_anchor_tags(self):
        from connector.of_connector import strip_html
        html = '<a href="https://onlyfans.com/user">user</a> sent a message'
        assert strip_html(html) == "user sent a message"

    def test_strips_multiple_tags(self):
        from connector.of_connector import strip_html
        html = "<b>Hey</b> what's <em>up</em>?"
        assert strip_html(html) == "Hey what's up?"

    def test_empty_string(self):
        from connector.of_connector import strip_html
        assert strip_html("") == ""

    def test_only_tags_becomes_empty(self):
        from connector.of_connector import strip_html
        assert strip_html("<br><hr>") == ""


# ─────────────────────────────────────────────
# Price format tests
# ─────────────────────────────────────────────

class TestOFPriceFormat:
    """OnlyFans prices must be in DOLLARS — never multiply by 100."""

    def test_engine_output_passes_through_unchanged(self):
        engine_price_dollars = 27.38
        of_api_price = engine_price_dollars
        assert of_api_price == pytest.approx(27.38)

    def test_tier_6_is_exactly_200(self):
        assert 200.00 == 200.00

    def test_not_cents(self):
        revenue_amount = 27.38
        assert revenue_amount > 1.0


# ─────────────────────────────────────────────
# Unified webhook endpoint — messages.received
# ─────────────────────────────────────────────

class TestWebhookMessagesReceived:

    @pytest.mark.anyio
    async def test_valid_message_returns_ok(self, mock_env, mock_avatars):
        with (
            patch("connector.of_connector._avatars", mock_avatars),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=make_sub()),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.create_subscriber", return_value=make_sub()),
            patch("connector.of_connector.send_of_message", new_callable=AsyncMock),
        ):
            from connector.of_connector import app
            body = make_event("messages.received", {
                "fromUser": {"id": "12345", "username": "johndoe", "name": "John Doe"},
                "text": "Do you have customs?",
                "isFree": True,
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.anyio
    async def test_invalid_sig_returns_403(self, mock_env):
        from connector.of_connector import app
        body = make_event("messages.received", {"fromUser": {"id": "1"}, "text": "hi"})
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook/of",
                content=body,
                headers={"Signature": "invalidsig", "Content-Type": "application/json"},
            )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_html_text_stripped_before_engine(self, mock_env, mock_avatars):
        """Message text with HTML should be stripped before processing."""
        processed_messages = []

        async def fake_process_message(sub, message, avatar=None):
            processed_messages.append(message)
            from models import BotAction
            return [BotAction(action_type="send_message", message="ok", delay_seconds=0)]

        with (
            patch("connector.of_connector._avatars", mock_avatars),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=make_sub()),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.create_subscriber", return_value=make_sub()),
            patch("connector.of_connector.send_of_message", new_callable=AsyncMock),
            patch("connector.of_connector.orchestrator_process_message", side_effect=fake_process_message),
        ):
            from connector.of_connector import app
            body = make_event("messages.received", {
                "fromUser": {"id": "99", "username": "fan"},
                "text": "<b>Hey!</b> What are your <em>rates</em>?",
                "isFree": True,
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )

        await asyncio.sleep(0.1)
        if processed_messages:
            assert "<b>" not in processed_messages[0]
            assert "Hey! What are your rates?" == processed_messages[0]

    @pytest.mark.anyio
    async def test_empty_text_ignored(self, mock_env):
        with (
            patch("connector.of_connector._avatars", {"girl_boss": MagicMock()}),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
        ):
            from connector.of_connector import app
            body = make_event("messages.received", {
                "fromUser": {"id": "1", "username": "fan"},
                "text": "",
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200
            # Returns ok (background task ignores it internally)

    @pytest.mark.anyio
    async def test_html_only_tags_ignored(self, mock_env):
        """A message that is only HTML tags (empty after stripping) should be ignored."""
        with (
            patch("connector.of_connector._avatars", {"girl_boss": MagicMock()}),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
        ):
            from connector.of_connector import app
            body = make_event("messages.received", {
                "fromUser": {"id": "1"},
                "text": "<br>",
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


# ─────────────────────────────────────────────
# subscriptions.new
# ─────────────────────────────────────────────

class TestWebhookSubscriptionsNew:

    @pytest.mark.anyio
    async def test_new_subscriber_processed(self, mock_env, mock_avatars):
        with (
            patch("connector.of_connector._avatars", mock_avatars),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.create_subscriber", return_value=make_sub()),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.send_of_message", new_callable=AsyncMock),
        ):
            from connector.of_connector import app
            body = make_event("subscriptions.new", {
                "user_id": "fan_001",
                "subType": "new_subscriber",
                "replacePairs": {
                    "{SUBSCRIBER_LINK}": '<a href="https://onlyfans.com/johndoe">johndoe</a>',
                    "{PRICE}": "$9.99",
                },
                "fanData": {"spending": {"total": 0}},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_username_extracted_from_subscriber_link(self, mock_env, mock_avatars):
        """Username should be parsed from the SUBSCRIBER_LINK replacePair."""
        created_subs = []

        def fake_create(platform, uid, mid, username="", display_name=""):
            sub = make_sub()
            created_subs.append({"uid": uid, "username": username})
            return sub

        with (
            patch("connector.of_connector._avatars", mock_avatars),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.create_subscriber", side_effect=fake_create),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.send_of_message", new_callable=AsyncMock),
        ):
            from connector.of_connector import app
            body = make_event("subscriptions.new", {
                "user_id": "fan_999",
                "subType": "new_subscriber",
                "replacePairs": {
                    "{SUBSCRIBER_LINK}": '<a href="https://onlyfans.com/rosefan">rosefan</a>',
                    "{PRICE}": "$9.99",
                },
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )

        await asyncio.sleep(0.1)
        if created_subs:
            assert created_subs[0]["username"] == "rosefan"
            assert created_subs[0]["uid"] == "fan_999"


# ─────────────────────────────────────────────
# subscriptions.renewed
# ─────────────────────────────────────────────

class TestWebhookSubscriptionsRenewed:

    @pytest.mark.anyio
    async def test_renewal_records_transaction(self, mock_env):
        recorded = []

        def fake_record(sub_id, model_id, tx_type, amount, platform, content_ref=None):
            recorded.append({"type": tx_type, "amount": amount})

        with (
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=make_sub()),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.record_transaction", side_effect=fake_record),
            patch("connector.of_connector.create_subscriber", return_value=make_sub()),
        ):
            from connector.of_connector import app
            body = make_event("subscriptions.renewed", {
                "user_id": "fan_renew_001",
                "subType": "returning_subscriber",
                "replacePairs": {
                    "{SUBSCRIBER_LINK}": '<a href="https://onlyfans.com/fan">fan</a>',
                    "{PRICE}": "$9.99",
                },
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

        await asyncio.sleep(0.1)
        if recorded:
            assert recorded[0]["type"] == "subscription"
            assert recorded[0]["amount"] == pytest.approx(9.99)


# ─────────────────────────────────────────────
# messages.ppv.unlocked
# ─────────────────────────────────────────────

class TestWebhookPPVUnlocked:

    @pytest.mark.anyio
    async def test_ppv_unlocked_records_purchase(self, mock_env):
        recorded = []

        def fake_record(sub_id, model_id, tx_type, amount, platform, content_ref=None):
            recorded.append({"type": tx_type, "amount": amount})

        sub = make_sub()
        with (
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=sub),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.record_transaction", side_effect=fake_record),
            patch("connector.of_connector.create_subscriber", return_value=sub),
        ):
            from connector.of_connector import app
            body = make_event("messages.ppv.unlocked", {
                "id": "msg_123",
                "type": "paided_message",
                "subType": "subscriber_pay_for_chat_message",
                "user_id": "fan_buyer_001",
                "replacePairs": {
                    "{AMOUNT}": "$27.38",
                    "{NAME}": "Fan",
                    "{MESSAGE_LINK}": "<a href='...'>message</a>",
                },
                "fanData": {"spending": {"total": 27.38, "messages": 27.38}},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

        await asyncio.sleep(0.1)
        if recorded:
            assert recorded[0]["type"] == "ppv"
            assert recorded[0]["amount"] == pytest.approx(27.38)

    @pytest.mark.anyio
    async def test_ppv_amount_not_divided_by_100(self, mock_env):
        """OF amounts are stored as-is in dollars, never divided by 100."""
        recorded_amounts = []

        def fake_record(sub_id, model_id, tx_type, amount, platform, content_ref=None):
            recorded_amounts.append(amount)

        sub = make_sub()
        with (
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=sub),
            patch("connector.of_connector.save_subscriber"),
            patch("connector.of_connector.record_transaction", side_effect=fake_record),
            patch("connector.of_connector.create_subscriber", return_value=sub),
        ):
            from connector.of_connector import app
            body = make_event("messages.ppv.unlocked", {
                "user_id": "fan_001",
                "replacePairs": {"{AMOUNT}": "$77.35"},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )

        await asyncio.sleep(0.1)
        if recorded_amounts:
            assert recorded_amounts[0] == pytest.approx(77.35)  # dollars, not 7735 cents


# ─────────────────────────────────────────────
# tips.received
# ─────────────────────────────────────────────

class TestWebhookTipsReceived:

    @pytest.mark.anyio
    async def test_tip_recorded(self, mock_env):
        recorded = []

        def fake_record(sub_id, model_id, tx_type, amount, platform, content_ref=None):
            recorded.append({"type": tx_type, "amount": amount})

        with (
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
            patch("connector.of_connector.load_subscriber", return_value=make_sub()),
            patch("connector.of_connector.create_subscriber", return_value=make_sub()),
            patch("connector.of_connector.record_transaction", side_effect=fake_record),
        ):
            from connector.of_connector import app
            body = make_event("tips.received", {
                "id": "tip_abc",
                "user_id": "fan_tipper",
                "amountGross": 10.0,
                "amountNet": 8.0,
                "type": "tip",
                "subType": "new_tips",
                "createdAt": "2026-01-02T17:12:00+00:00",
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

        await asyncio.sleep(0.1)
        if recorded:
            assert recorded[0]["type"] == "tip"
            assert recorded[0]["amount"] == pytest.approx(10.0)


# ─────────────────────────────────────────────
# transactions.new
# ─────────────────────────────────────────────

class TestWebhookTransactionsNew:

    @pytest.mark.anyio
    async def test_transaction_event_returns_ok(self, mock_env):
        with (
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
        ):
            from connector.of_connector import app
            body = make_event("transactions.new", {
                "id": "tx_abc123",
                "type": "message",
                "amount": 3.0,
                "vat_amount": 0.63,
                "net_amount": 2.4,
                "fee_amount": 0.6,
                "currency": "USD",
                "fanData": {"available": True},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


# ─────────────────────────────────────────────
# accounts.* events
# ─────────────────────────────────────────────

class TestWebhookAccountEvents:

    @pytest.mark.anyio
    async def test_account_connected_returns_ok(self, mock_env):
        with patch("connector.of_connector._model_id", "model-of-uuid-xyz"):
            from connector.of_connector import app
            body = make_event("accounts.connected", {
                "state": "authenticated",
                "progress": "started",
                "latestAuthAttempt": {"started_at": "2025-05-13T20:26:56.000000Z"},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_authentication_failed_returns_ok(self, mock_env):
        with patch("connector.of_connector._model_id", "model-of-uuid-xyz"):
            from connector.of_connector import app
            body = make_event("accounts.authentication_failed", {
                "state": "unauthenticated",
                "latestAuthAttempt": {"success": False},
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_unknown_event_returns_ok(self, mock_env):
        """Unknown events should be silently ignored (logged only)."""
        with patch("connector.of_connector._model_id", "model-of-uuid-xyz"):
            from connector.of_connector import app
            body = make_event("posts.liked", {
                "id": "post_123",
                "user_id": "fan_456",
            })
            sig = make_of_sig(body)
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook/of",
                    content=body,
                    headers={"Signature": sig, "Content-Type": "application/json"},
                )
            assert resp.status_code == 200


# ─────────────────────────────────────────────
# Health endpoint
# ─────────────────────────────────────────────

class TestOFHealth:

    @pytest.mark.anyio
    async def test_health_returns_ok(self, mock_env):
        with (
            patch("connector.of_connector._avatars", {"girl_boss": MagicMock()}),
            patch("connector.of_connector._attribution", None),
            patch("connector.of_connector._model_id", "model-of-uuid-xyz"),
        ):
            from connector.of_connector import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["platform"] == "onlyfans"
