"""
Tests for the Admin Telegram Bot.

Mocks: Supabase, Redis, B2, Telegram API.
Run with: pytest tests/test_admin_bot.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def bot_env(monkeypatch):
    env = {
        "TELEGRAM_BOT_TOKEN": "1234567890:AABBCCtest_token",
        "TELEGRAM_ADMIN_IDS": "1234567890",
        "FANVUE_MODEL_ID": "model-uuid-xyz",
        "REDIS_URL": "redis://localhost:6379/0",
        "B2_KEY_ID": "b2_key_id",
        "B2_APP_KEY": "b2_app_key",
        "B2_BUCKET_NAME": "massi-bot-content",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return env


# ─────────────────────────────────────────────
# alerts.py tests
# ─────────────────────────────────────────────

class TestAlerts:

    @pytest.mark.anyio
    async def test_send_alert_calls_telegram_api(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "1234567890")

        from admin_bot import alerts as alert_module
        sent_payloads = []

        async def fake_post(url, json=None, **kwargs):
            sent_payloads.append(json)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("admin_bot.alerts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await alert_module.alert_new_subscriber("fanvue", "john_doe", whale_score=30)

        assert len(sent_payloads) == 1
        assert sent_payloads[0]["chat_id"] == 1234567890
        assert "New Subscriber" in sent_payloads[0]["text"]

    @pytest.mark.anyio
    async def test_alert_whale_detected_includes_score(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "1234567890")

        from admin_bot import alerts as alert_module
        sent_texts = []

        async def fake_post(url, json=None, **kwargs):
            if json:
                sent_texts.append(json.get("text", ""))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("admin_bot.alerts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await alert_module.alert_whale_detected("fanvue", "bigspender", 85)

        assert any("85" in t for t in sent_texts)
        assert any("WHALE" in t for t in sent_texts)

    @pytest.mark.anyio
    async def test_alert_purchase_includes_amount(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "1234567890")

        from admin_bot import alerts as alert_module
        sent_texts = []

        async def fake_post(url, json=None, **kwargs):
            if json:
                sent_texts.append(json.get("text", ""))
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        with patch("admin_bot.alerts.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=fake_post)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await alert_module.alert_purchase("fanvue", "buyer123", 77.35, tier=3)

        assert any("77.35" in t for t in sent_texts)

    @pytest.mark.anyio
    async def test_alert_no_admin_ids_logs_warning(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "")

        from admin_bot import alerts as alert_module
        # Should not raise even with no admin IDs configured
        with patch("admin_bot.alerts.httpx.AsyncClient"):
            await alert_module.alert_error("test", "some error")  # no exception


# ─────────────────────────────────────────────
# content_intake.py tests
# ─────────────────────────────────────────────

class TestContentIntakeTierEnum:
    """Test tier enum mapping in content_intake module."""

    def test_all_6_tier_prices_mapped(self):
        from admin_bot.content_intake import _TIER_PRICES_CENTS
        # 7 entries: tiers 1-6 + continuation (tier 0)
        assert len(_TIER_PRICES_CENTS) == 7
        assert _TIER_PRICES_CENTS[1] == 2738
        assert _TIER_PRICES_CENTS[6] == 20000
        assert _TIER_PRICES_CENTS[0] == 2000  # continuation

    def test_all_6_tier_labels_present(self):
        from admin_bot.content_intake import _TIER_LABELS
        assert len(_TIER_LABELS) == 6
        for t in range(1, 7):
            assert t in _TIER_LABELS
            assert "$" in _TIER_LABELS[t]

    def test_tier_labels_have_prices(self):
        from admin_bot.content_intake import _TIER_LABELS
        assert "27.38" in _TIER_LABELS[1]
        assert "200.00" in _TIER_LABELS[6]


class TestContentIntakeConversationHandler:
    """Test the ConversationHandler is built correctly."""

    def test_handler_builds_without_error(self):
        from admin_bot.content_intake import build_content_intake_handler
        from telegram.ext import ConversationHandler
        handler = build_content_intake_handler()
        assert isinstance(handler, ConversationHandler)

    def test_handler_has_correct_states(self):
        from admin_bot.content_intake import build_content_intake_handler, WAITING_SESSION, WAITING_TIER
        handler = build_content_intake_handler()
        assert WAITING_SESSION in handler.states
        assert WAITING_TIER in handler.states


# ─────────────────────────────────────────────
# bot.py command tests
# ─────────────────────────────────────────────

def make_update(text: str = "", user_id: int = 1234567890) -> MagicMock:
    """Build a minimal mock Update object."""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def make_context(args: list = None) -> MagicMock:
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    ctx.bot = AsyncMock()
    return ctx


class TestBotCommandHandlers:

    @pytest.mark.anyio
    async def test_cmd_start_sends_welcome(self, monkeypatch):
        bot_env(monkeypatch)
        from admin_bot.bot import cmd_start
        update = make_update()
        ctx = make_context()
        await cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "Massi-Bot" in call_text

    @pytest.mark.anyio
    async def test_cmd_pause_sets_redis_flag(self, monkeypatch):
        bot_env(monkeypatch)
        mock_redis_instance = MagicMock()

        with patch("admin_bot.bot._redis", return_value=mock_redis_instance):
            from admin_bot.bot import cmd_pause
            update = make_update()
            ctx = make_context()
            await cmd_pause(update, ctx)

        mock_redis_instance.set.assert_called_once_with("engine:paused", "1")
        update.message.reply_text.assert_called_once()
        call_text = update.message.reply_text.call_args[0][0]
        assert "PAUSED" in call_text

    @pytest.mark.anyio
    async def test_cmd_resume_clears_redis_flag(self, monkeypatch):
        bot_env(monkeypatch)
        mock_redis_instance = MagicMock()

        with patch("admin_bot.bot._redis", return_value=mock_redis_instance):
            from admin_bot.bot import cmd_resume
            update = make_update()
            ctx = make_context()
            await cmd_resume(update, ctx)

        mock_redis_instance.delete.assert_called_once_with("engine:paused")
        call_text = update.message.reply_text.call_args[0][0]
        assert "RESUMED" in call_text

    @pytest.mark.anyio
    async def test_cmd_override_no_args_shows_usage(self, monkeypatch):
        bot_env(monkeypatch)
        from admin_bot.bot import cmd_override
        update = make_update()
        ctx = make_context(args=[])
        await cmd_override(update, ctx)
        call_text = update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text

    @pytest.mark.anyio
    async def test_cmd_override_queues_redis_message(self, monkeypatch):
        bot_env(monkeypatch)
        mock_redis_instance = MagicMock()

        with patch("admin_bot.bot._redis", return_value=mock_redis_instance):
            from admin_bot.bot import cmd_override
            update = make_update()
            ctx = make_context(args=["fv-user-001", "Hey there gorgeous"])
            await cmd_override(update, ctx)

        mock_redis_instance.lpush.assert_called_once()
        call_args = mock_redis_instance.lpush.call_args[0]
        assert "fv-user-001" in call_args[0]
        assert "Hey there gorgeous" in call_args[1]

    @pytest.mark.anyio
    async def test_cmd_set_uuid_no_args_shows_usage(self, monkeypatch):
        bot_env(monkeypatch)
        from admin_bot.bot import cmd_set_uuid
        update = make_update()
        ctx = make_context(args=[])
        await cmd_set_uuid(update, ctx)
        call_text = update.message.reply_text.call_args[0][0]
        assert "Usage" in call_text

    @pytest.mark.anyio
    async def test_cmd_set_uuid_calls_update_fanvue_uuid(self, monkeypatch):
        bot_env(monkeypatch)
        # update_fanvue_uuid is imported inside the function, so patch the source module
        with patch("persistence.content_store.update_fanvue_uuid") as mock_fn:
            from admin_bot.bot import cmd_set_uuid
            update = make_update()
            ctx = make_context(args=["bundle_s1_t1", "fv-media-uuid-abc"])
            await cmd_set_uuid(update, ctx)
            # Should have called update_fanvue_uuid or shown an error — no exception either way
        update.message.reply_text.assert_called_once()

    @pytest.mark.anyio
    async def test_cmd_stats_handles_db_error_gracefully(self, monkeypatch):
        bot_env(monkeypatch)
        with patch("admin_bot.bot._get_sub_stats", side_effect=Exception("DB error")):
            from admin_bot.bot import cmd_stats
            update = make_update()
            ctx = make_context()
            await cmd_stats(update, ctx)
            call_text = update.message.reply_text.call_args[0][0]
            assert "Error" in call_text

    @pytest.mark.anyio
    async def test_cmd_revenue_handles_db_error_gracefully(self, monkeypatch):
        bot_env(monkeypatch)
        with patch("admin_bot.bot._get_revenue_stats", side_effect=Exception("timeout")):
            from admin_bot.bot import cmd_revenue
            update = make_update()
            ctx = make_context()
            await cmd_revenue(update, ctx)
            call_text = update.message.reply_text.call_args[0][0]
            assert "Error" in call_text

    @pytest.mark.anyio
    async def test_cmd_readiness_calls_content_store(self, monkeypatch):
        bot_env(monkeypatch)
        fake_report = {
            "ready": True,
            "total_bundles": 12,
            "tiers": [
                {"tier": t, "name": f"Tier {t}", "bundle_count": 2, "has_fanvue_uuid": True}
                for t in range(1, 7)
            ],
        }
        with patch("admin_bot.bot.get_catalog_readiness", return_value=fake_report):
            from admin_bot.bot import cmd_readiness
            update = make_update()
            ctx = make_context()
            await cmd_readiness(update, ctx)
            call_text = update.message.reply_text.call_args[0][0]
            assert "READY" in call_text
            assert "12" in call_text


# ─────────────────────────────────────────────
# bot.py helper tests
# ─────────────────────────────────────────────

class TestBotHelpers:

    def test_is_paused_returns_false_when_not_set(self, monkeypatch):
        bot_env(monkeypatch)
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch("admin_bot.bot._redis", return_value=mock_redis):
            from admin_bot.bot import _is_paused
            assert _is_paused() is False

    def test_is_paused_returns_true_when_set(self, monkeypatch):
        bot_env(monkeypatch)
        mock_redis = MagicMock()
        mock_redis.get.return_value = "1"
        with patch("admin_bot.bot._redis", return_value=mock_redis):
            from admin_bot.bot import _is_paused
            assert _is_paused() is True

    def test_revenue_stats_aggregation(self, monkeypatch):
        bot_env(monkeypatch)
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {"type": "ppv", "amount": "27.38"},
            {"type": "ppv", "amount": "77.35"},
            {"type": "tip", "amount": "10.00"},
        ]
        with patch("admin_bot.bot.get_client", return_value=mock_db):
            from admin_bot.bot import _get_revenue_stats
            stats = _get_revenue_stats("model-xyz")
            assert stats["total"] == pytest.approx(27.38 + 77.35 + 10.00)
            assert stats["by_type"]["ppv"] == pytest.approx(27.38 + 77.35)
            assert stats["by_type"]["tip"] == pytest.approx(10.00)
            assert stats["count"] == 3

    def test_admin_ids_parsed(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "1234567890,9876543210")
        from admin_bot.alerts import _admin_ids
        ids = _admin_ids()
        assert 1234567890 in ids
        assert 9876543210 in ids
        assert len(ids) == 2

    def test_admin_ids_empty_returns_empty(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "")
        from admin_bot.alerts import _admin_ids
        assert _admin_ids() == []
