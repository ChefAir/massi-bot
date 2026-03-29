"""
Tests for the persistence layer (supabase_client, subscriber_store, content_store).

All Supabase calls are mocked — no real DB connection required.
Run with: pytest tests/test_persistence.py -v
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
import sys
import os

# Make engine and persistence importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import (
    Subscriber, SubState, SubType, ScriptPhase,
    QualifyingData, SpendingHistory,
)
from onboarding import ContentTier


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_subscriber(**kwargs) -> Subscriber:
    """Build a minimal Subscriber for testing."""
    defaults = dict(
        sub_id="test-uuid-1234",
        username="testuser",
        display_name="Test User",
        state=SubState.WARMING,
        sub_type=SubType.HORNY,
        persona_id="avatar_1",
        source_ig_account="@testmodel",
        source_detected=True,
        subscribe_date=datetime(2026, 1, 1, 12, 0, 0),
        message_count=5,
        qualifying_questions_asked=2,
        current_script_id="script_001",
        current_script_phase=ScriptPhase.TEASE,
        current_loop_number=1,
        scripts_completed=["script_000"],
        gfe_active=False,
        callback_references=["loves football", "works in finance"],
        last_message_date=datetime(2026, 3, 1, 10, 0, 0),
        ghost_count=0,
        tier_no_count=1,
    )
    defaults.update(kwargs)
    sub = Subscriber(**defaults)
    sub.spending.total_spent = 27.38
    sub.spending.ppv_count = 1
    sub.qualifying.age = 32
    sub.qualifying.occupation = "engineer"
    return sub


def make_db_row(**overrides) -> dict:
    """Build a minimal Supabase row dict as returned by the DB."""
    row = {
        "id": "db-uuid-abcd",
        "platform": "fanvue",
        "platform_user_id": "fv_user_001",
        "model_id": "model-uuid-xyz",
        "username": "testuser",
        "display_name": "Test User",
        "state": "warming",
        "whale_score": 25,
        "total_spent": 27.38,
        "persona_id": "avatar_1",
        "current_script_id": "script_001",
        "loop_count": 1,
        "current_tier": 1,
        "callback_references": ["loves football", "works in finance"],
        "recent_messages": [],
        "last_message_at": "2026-03-01T10:00:00",
        "created_at": "2026-01-01T12:00:00",
        "spending_history": {
            "total_spent": 27.38,
            "ppv_count": 1,
            "custom_count": 0,
            "tip_count": 0,
            "last_purchase_date": None,
            "avg_ppv_price": 27.38,
            "highest_single_purchase": 27.38,
            "rejected_ppv_count": 0,
            "price_objection_count": 0,
        },
        "qualifying_data": {
            "sub_type": "horny",
            "source_ig_account": "@testmodel",
            "source_detected": True,
            "subscribe_date": "2026-01-01T12:00:00",
            "message_count": 5,
            "qualifying_questions_asked": 2,
            "current_script_phase": "tease",
            "scripts_completed": ["script_000"],
            "gfe_active": False,
            "personal_details_shared": {},
            "emotional_hooks": [],
            "last_active_date": None,
            "ghost_count": 0,
            "re_engagement_attempts": 0,
            "asked_for_meetup": False,
            "asked_for_free_content": 0,
            "one_word_reply_streak": 0,
            "abusive": False,
            "tier_no_count": 1,
            "last_session_completed_at": None,
            "session_locked_until": None,
            "custom_declined": False,
            "brokey_flagged": False,
            "age": 32,
            "location": None,
            "occupation": "engineer",
            "relationship_status": None,
            "subscribe_reason": None,
            "interests": [],
            "mentions_spending": False,
            "emotional_openness": 0,
            "response_speed": "normal",
            "message_length": "normal",
            "initiated_sexual": False,
        },
    }
    row.update(overrides)
    return row


# ─────────────────────────────────────────────
# subscriber_store tests
# ─────────────────────────────────────────────

class TestRowToSubscriber:
    """Test deserialization from DB row → Subscriber."""

    def test_basic_fields(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())

        assert sub.sub_id == "db-uuid-abcd"
        assert sub.username == "testuser"
        assert sub.display_name == "Test User"
        assert sub.state == SubState.WARMING
        assert sub.sub_type == SubType.HORNY
        assert sub.persona_id == "avatar_1"
        assert sub.current_script_id == "script_001"
        assert sub.current_loop_number == 1

    def test_spending_history(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())

        assert sub.spending.total_spent == pytest.approx(27.38)
        assert sub.spending.ppv_count == 1
        assert sub.spending.avg_ppv_price == pytest.approx(27.38)

    def test_qualifying_data(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())

        assert sub.qualifying.age == 32
        assert sub.qualifying.occupation == "engineer"
        assert sub.source_ig_account == "@testmodel"
        assert sub.source_detected is True

    def test_script_phase_parsed(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())
        assert sub.current_script_phase == ScriptPhase.TEASE

    def test_callback_references(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())
        assert "loves football" in sub.callback_references
        assert "works in finance" in sub.callback_references

    def test_last_message_date_parsed(self):
        from persistence.subscriber_store import _row_to_subscriber
        sub = _row_to_subscriber(make_db_row())
        assert sub.last_message_date == datetime(2026, 3, 1, 10, 0, 0)

    def test_unknown_state_falls_back(self):
        from persistence.subscriber_store import _row_to_subscriber
        row = make_db_row(state="invalid_state_xyz")
        sub = _row_to_subscriber(row)
        assert sub.state == SubState.RETENTION  # Safe fallback, not NEW (prevents state reset)

    def test_unknown_sub_type_falls_back(self):
        from persistence.subscriber_store import _row_to_subscriber
        row = make_db_row()
        row["qualifying_data"]["sub_type"] = "bogus"
        sub = _row_to_subscriber(row)
        assert sub.sub_type == SubType.UNKNOWN

    def test_missing_qualifying_data_safe(self):
        from persistence.subscriber_store import _row_to_subscriber
        row = make_db_row()
        row["qualifying_data"] = None
        row["spending_history"] = None
        sub = _row_to_subscriber(row)
        assert sub.spending.total_spent == 0.0
        assert sub.qualifying.age is None

    def test_session_control_fields(self):
        from persistence.subscriber_store import _row_to_subscriber
        row = make_db_row()
        row["qualifying_data"]["tier_no_count"] = 2
        row["qualifying_data"]["brokey_flagged"] = True
        row["qualifying_data"]["custom_declined"] = True
        sub = _row_to_subscriber(row)
        assert sub.tier_no_count == 2
        assert sub.brokey_flagged is True
        assert sub.custom_declined is True


class TestSubscriberToRow:
    """Test serialization from Subscriber → DB row."""

    def test_core_columns(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")

        assert row["platform"] == "fanvue"
        assert row["platform_user_id"] == "fv_001"
        assert row["model_id"] == "model-xyz"
        assert row["username"] == "testuser"
        assert row["state"] == "warming"
        assert row["persona_id"] == "avatar_1"
        assert row["current_script_id"] == "script_001"
        assert row["loop_count"] == 1

    def test_spending_history_serialized(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        sh = row["spending_history"]

        assert sh["total_spent"] == pytest.approx(27.38)
        assert sh["ppv_count"] == 1

    def test_qualifying_data_serialized(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        qd = row["qualifying_data"]

        assert qd["sub_type"] == "horny"
        assert qd["source_ig_account"] == "@testmodel"
        assert qd["occupation"] == "engineer"
        assert qd["tier_no_count"] == 1

    def test_script_phase_serialized(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        assert row["qualifying_data"]["current_script_phase"] == "tease"

    def test_script_phase_none_serialized(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber(current_script_phase=None)
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        assert row["qualifying_data"]["current_script_phase"] is None

    def test_callback_references_in_row(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        assert "loves football" in row["callback_references"]

    def test_whale_score_computed(self):
        from persistence.subscriber_store import _subscriber_to_row
        sub = make_subscriber()
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        # whale_score is a computed property — just check it's a non-negative int
        assert isinstance(row["whale_score"], int)
        assert row["whale_score"] >= 0


class TestRoundTrip:
    """Verify serialize → deserialize preserves key fields."""

    def test_roundtrip_preserves_state(self):
        from persistence.subscriber_store import _subscriber_to_row, _row_to_subscriber
        sub = make_subscriber(state=SubState.GFE_ACTIVE)
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        # Simulate DB adding id / timestamps
        row["id"] = "db-uuid-rt"
        row["created_at"] = "2026-01-01T00:00:00"
        sub2 = _row_to_subscriber(row)
        assert sub2.state == SubState.GFE_ACTIVE

    def test_roundtrip_preserves_spending(self):
        from persistence.subscriber_store import _subscriber_to_row, _row_to_subscriber
        sub = make_subscriber()
        sub.spending.total_spent = 127.45
        sub.spending.ppv_count = 3
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        row["id"] = "db-uuid-rt"
        row["created_at"] = "2026-01-01T00:00:00"
        sub2 = _row_to_subscriber(row)
        assert sub2.spending.total_spent == pytest.approx(127.45)
        assert sub2.spending.ppv_count == 3

    def test_roundtrip_preserves_qualifying(self):
        from persistence.subscriber_store import _subscriber_to_row, _row_to_subscriber
        sub = make_subscriber()
        sub.qualifying.age = 38
        sub.qualifying.occupation = "lawyer"
        sub.qualifying.emotional_openness = 8
        row = _subscriber_to_row(sub, "fanvue", "fv_001", "model-xyz")
        row["id"] = "db-uuid-rt"
        row["created_at"] = "2026-01-01T00:00:00"
        sub2 = _row_to_subscriber(row)
        assert sub2.qualifying.age == 38
        assert sub2.qualifying.occupation == "lawyer"
        assert sub2.qualifying.emotional_openness == 8


class TestLoadSubscriber:
    """Test load_subscriber with mocked Supabase."""

    @patch("persistence.subscriber_store.get_client")
    def test_returns_subscriber_when_found(self, mock_get_client):
        from persistence.subscriber_store import load_subscriber
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = [make_db_row()]

        sub = load_subscriber("fanvue", "fv_user_001", "model-uuid-xyz")
        assert sub is not None
        assert sub.username == "testuser"

    @patch("persistence.subscriber_store.get_client")
    def test_returns_none_when_not_found(self, mock_get_client):
        from persistence.subscriber_store import load_subscriber
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value.data = []

        sub = load_subscriber("fanvue", "unknown_user", "model-uuid-xyz")
        assert sub is None


class TestCreateSubscriber:
    """Test create_subscriber with mocked Supabase."""

    @patch("persistence.subscriber_store.get_client")
    def test_creates_and_returns_subscriber(self, mock_get_client):
        from persistence.subscriber_store import create_subscriber
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        inserted_row = make_db_row(
            state="new",
            username="newuser",
            qualifying_data={
                "sub_type": "unknown", "source_ig_account": "", "source_detected": False,
                "subscribe_date": "2026-03-09T00:00:00", "message_count": 0,
                "qualifying_questions_asked": 0, "interests": [], "mentions_spending": False,
                "emotional_openness": 0, "response_speed": "normal", "message_length": "normal",
                "initiated_sexual": False, "scripts_completed": [], "gfe_active": False,
                "personal_details_shared": {}, "emotional_hooks": [],
                "last_active_date": None, "ghost_count": 0, "re_engagement_attempts": 0,
                "asked_for_meetup": False, "asked_for_free_content": 0,
                "one_word_reply_streak": 0, "abusive": False, "tier_no_count": 0,
                "brokey_flagged": False, "custom_declined": False,
            },
        )
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [inserted_row]

        sub = create_subscriber("fanvue", "new_fv_001", "model-xyz", username="newuser")
        assert sub is not None
        assert sub.state == SubState.NEW

    @patch("persistence.subscriber_store.get_client")
    def test_raises_on_insert_failure(self, mock_get_client):
        from persistence.subscriber_store import create_subscriber
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value.data = None

        with pytest.raises(RuntimeError, match="Failed to create subscriber"):
            create_subscriber("fanvue", "fv_dup", "model-xyz")


class TestSaveSubscriber:
    """Test save_subscriber with mocked Supabase."""

    @patch("persistence.subscriber_store.get_client")
    def test_calls_upsert(self, mock_get_client):
        from persistence.subscriber_store import save_subscriber
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db

        sub = make_subscriber()
        save_subscriber(sub, "fanvue", "fv_001", "model-xyz")

        mock_db.table.assert_called_with("subscribers")
        mock_db.table.return_value.upsert.assert_called_once()


# ─────────────────────────────────────────────
# content_store tests
# ─────────────────────────────────────────────

def make_catalog_row(**overrides) -> dict:
    row = {
        "id": "cat-uuid-001",
        "model_id": "model-xyz",
        "session_number": 1,
        "tier": 1,
        "bundle_id": "bundle_s1_t1",
        "fanvue_media_uuid": "fv-media-uuid-abc",
        "b2_key": "models/model-xyz/session1/tier1/bundle.zip",
        "media_type": "mixed",
        "price_cents": 2738,
        "created_at": "2026-01-01T00:00:00",
    }
    row.update(overrides)
    return row


class TestRowToBundleInfo:
    """Test conversion from catalog DB row → bundle info dict."""

    def test_price_converted_to_dollars(self):
        from persistence.content_store import _row_to_bundle_info
        info = _row_to_bundle_info(make_catalog_row(price_cents=2738))
        assert info["price"] == pytest.approx(27.38)
        assert info["price_cents"] == 2738

    def test_tier_enum_populated(self):
        from persistence.content_store import _row_to_bundle_info
        info = _row_to_bundle_info(make_catalog_row(tier=1))
        assert info["tier_enum"] == ContentTier.TIER_1_BODY_TEASE

    def test_bundle_id_preserved(self):
        from persistence.content_store import _row_to_bundle_info
        info = _row_to_bundle_info(make_catalog_row(bundle_id="bundle_s3_t2"))
        assert info["bundle_id"] == "bundle_s3_t2"

    def test_fanvue_uuid_preserved(self):
        from persistence.content_store import _row_to_bundle_info
        info = _row_to_bundle_info(make_catalog_row(fanvue_media_uuid="fv-abc-123"))
        assert info["fanvue_media_uuid"] == "fv-abc-123"

    def test_none_price_cents_safe(self):
        from persistence.content_store import _row_to_bundle_info
        info = _row_to_bundle_info(make_catalog_row(price_cents=None))
        assert info["price"] == pytest.approx(0.0)


class TestGetAvailableBundle:
    """Test get_available_bundle with mocked Supabase."""

    @patch("persistence.content_store.get_client")
    def test_returns_first_unused(self, mock_get_client):
        from persistence.content_store import get_available_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        rows = [
            make_catalog_row(bundle_id="b1", session_number=1),
            make_catalog_row(bundle_id="b2", session_number=2),
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = rows

        result = get_available_bundle("model-xyz", ContentTier.TIER_1_BODY_TEASE)
        assert result["bundle_id"] == "b1"

    @patch("persistence.content_store.get_client")
    def test_skips_excluded(self, mock_get_client):
        from persistence.content_store import get_available_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        rows = [
            make_catalog_row(bundle_id="b1", session_number=1),
            make_catalog_row(bundle_id="b2", session_number=2),
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = rows

        result = get_available_bundle("model-xyz", ContentTier.TIER_1_BODY_TEASE, exclude_bundle_ids=["b1"])
        assert result["bundle_id"] == "b2"

    @patch("persistence.content_store.get_client")
    def test_recycles_when_all_used(self, mock_get_client):
        from persistence.content_store import get_available_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        rows = [make_catalog_row(bundle_id="b1", session_number=1)]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = rows

        result = get_available_bundle("model-xyz", ContentTier.TIER_1_BODY_TEASE, exclude_bundle_ids=["b1"])
        # All excluded → recycles first
        assert result["bundle_id"] == "b1"

    @patch("persistence.content_store.get_client")
    def test_returns_none_when_no_content(self, mock_get_client):
        from persistence.content_store import get_available_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value.data = []

        result = get_available_bundle("model-xyz", ContentTier.TIER_6_CLIMAX)
        assert result is None


class TestGetCatalogReadiness:
    """Test catalog readiness check."""

    @patch("persistence.content_store.get_client")
    def test_ready_when_all_tiers_present(self, mock_get_client):
        from persistence.content_store import get_catalog_readiness
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        rows = [make_catalog_row(tier=t) for t in range(1, 7)]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = rows

        result = get_catalog_readiness("model-xyz")
        assert result["ready"] is True
        assert result["total_bundles"] == 6

    @patch("persistence.content_store.get_client")
    def test_not_ready_when_tiers_missing(self, mock_get_client):
        from persistence.content_store import get_catalog_readiness
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        # Only tiers 1-3 present
        rows = [make_catalog_row(tier=t) for t in range(1, 4)]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.order.return_value.execute.return_value.data = rows

        result = get_catalog_readiness("model-xyz")
        assert result["ready"] is False


class TestRegisterBundle:
    """Test register_bundle with mocked Supabase."""

    @patch("persistence.content_store.get_client")
    def test_inserts_with_default_price(self, mock_get_client):
        from persistence.content_store import register_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        inserted = make_catalog_row(bundle_id="new_bundle", price_cents=2738)
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [inserted]

        result = register_bundle(
            model_id="model-xyz",
            session_number=1,
            tier=ContentTier.TIER_1_BODY_TEASE,
            bundle_id="new_bundle",
        )
        assert result["bundle_id"] == "new_bundle"
        assert result["price"] == pytest.approx(27.38)

    @patch("persistence.content_store.get_client")
    def test_raises_on_failure(self, mock_get_client):
        from persistence.content_store import register_bundle
        mock_db = MagicMock()
        mock_get_client.return_value = mock_db
        mock_db.table.return_value.insert.return_value.execute.return_value.data = None

        with pytest.raises(RuntimeError, match="Failed to register bundle"):
            register_bundle(
                model_id="model-xyz",
                session_number=1,
                tier=ContentTier.TIER_1_BODY_TEASE,
                bundle_id="fail_bundle",
            )
