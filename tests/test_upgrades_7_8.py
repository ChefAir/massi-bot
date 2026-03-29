"""
Tests for Upgrade 7 (Returning User Awareness) and Upgrade 8 (Persona Self-Identity Memory).

Run with: pytest tests/test_upgrades_7_8.py -v
"""

import pytest
import sys
import os
import re
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber, SubState, SubType, BotAction


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def make_sub(state: SubState = SubState.NEW, message_count: int = 0) -> Subscriber:
    sub = Subscriber(
        sub_id="test-sub-u78",
        username="testfan",
        display_name="Test Fan",
        state=state,
        persona_id="girl_boss",
    )
    sub.message_count = message_count
    return sub


def make_avatar():
    avatar = MagicMock()
    avatar.persona = MagicMock()
    avatar.persona.name = "Jasmine"
    avatar.persona.nickname = "Jazz"
    avatar.persona.location_story = "Miami"
    avatar.persona.age = 24
    avatar.persona.ig_account_tag = "girl_boss"
    avatar.persona.voice = MagicMock()
    avatar.persona.voice.primary_tone = "flirty & sweet"
    avatar.persona.voice.emoji_use = "moderate"
    avatar.persona.voice.flirt_style = "playful"
    avatar.persona.voice.capitalization = "lowercase_casual"
    avatar.persona.voice.punctuation_style = "minimal"
    avatar.persona.voice.sexual_escalation_pace = "slow_burn"
    avatar.persona.voice.greeting_style = "casual"
    avatar.persona.voice.message_length = "short"
    avatar.persona.voice.favorite_phrases = ["stop it", "you're trouble"]
    avatar.persona.voice.reaction_phrases = ["omg stahp"]
    avatar.welcome_messages = ["hey! what made you subscribe? 💕"]
    avatar.qualifying_questions = []
    return avatar


def make_engine():
    """Build a minimal IntegratedEngine for testing."""
    from engine_v2 import IntegratedEngine
    from avatars import ALL_AVATARS
    return IntegratedEngine(avatars=ALL_AVATARS)


# ═══════════════════════════════════════════════
# UPGRADE 7: Returning User Awareness
# ═══════════════════════════════════════════════

class TestReturningUserDetection:
    """Test that _handle_new detects returning users."""

    def test_first_time_sub_gets_standard_welcome(self):
        """Brand new subscriber (message_count=0, no recent_messages) gets standard welcome."""
        engine = make_engine()
        sub = make_sub(state=SubState.NEW, message_count=0)
        sub.recent_messages = []
        actions = engine.process_new_subscriber(sub)
        assert len(actions) >= 1
        msg = actions[0].message.lower()
        # Standard welcome should NOT contain returning-user phrases
        returning_phrases = ["you're back", "missed you", "welcome back", "come find me"]
        assert not any(p in msg for p in returning_phrases), f"First-time sub got returning message: {msg}"

    def test_returning_sub_message_count_gets_returning_welcome(self):
        """Sub with message_count > 0 gets a returning user welcome."""
        engine = make_engine()
        sub = make_sub(state=SubState.NEW, message_count=5)
        sub.recent_messages = []
        actions = engine.process_new_subscriber(sub)
        assert len(actions) >= 1
        msg = actions[0].message.lower()
        returning_phrases = ["back", "missed", "thinking about", "come back", "hiding"]
        assert any(p in msg for p in returning_phrases), f"Returning sub didn't get returning message: {msg}"

    def test_returning_sub_recent_messages_gets_returning_welcome(self):
        """Sub with recent_messages (even if message_count=0) gets returning welcome."""
        engine = make_engine()
        sub = make_sub(state=SubState.NEW, message_count=0)
        sub.recent_messages = [
            {"role": "sub", "content": "hey", "timestamp": datetime.now().isoformat()},
        ]
        actions = engine.process_new_subscriber(sub)
        assert len(actions) >= 1
        msg = actions[0].message.lower()
        returning_phrases = ["back", "missed", "thinking about", "come back", "hiding"]
        assert any(p in msg for p in returning_phrases), f"Sub with history didn't get returning message: {msg}"

    def test_returning_welcome_does_not_ask_subscribe_reason(self):
        """Returning user welcome should NOT ask what made them subscribe."""
        engine = make_engine()
        sub = make_sub(state=SubState.NEW, message_count=10)
        actions = engine.process_new_subscriber(sub)
        msg = actions[0].message.lower()
        assert "what made you" not in msg
        assert "why did you" not in msg
        assert "subscribe" not in msg

    def test_state_transitions_to_welcome_sent(self):
        """Both first-time and returning subs transition to WELCOME_SENT."""
        engine = make_engine()
        # First-time
        sub1 = make_sub(state=SubState.NEW)
        engine.process_new_subscriber(sub1)
        assert sub1.state == SubState.WELCOME_SENT

        # Returning
        sub2 = make_sub(state=SubState.NEW, message_count=3)
        engine.process_new_subscriber(sub2)
        assert sub2.state == SubState.WELCOME_SENT


class TestReturningUserInRouter:
    """Test that _extract_decision_context includes is_returning flag."""

    def test_is_returning_flag_true_when_messages(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(state=SubState.NEW, message_count=5)
        ctx = _extract_decision_context(sub, SubState.NEW, [])
        assert ctx["is_returning"] is True

    def test_is_returning_flag_true_when_recent_messages(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(state=SubState.NEW, message_count=0)
        sub.recent_messages = [{"role": "sub", "content": "hi"}]
        ctx = _extract_decision_context(sub, SubState.NEW, [])
        assert ctx["is_returning"] is True

    def test_is_returning_flag_false_for_new_sub(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(state=SubState.NEW, message_count=0)
        sub.recent_messages = []
        ctx = _extract_decision_context(sub, SubState.NEW, [])
        assert ctx["is_returning"] is False


class TestReturningUserInPrompts:
    """Test that _resolve_mission picks new_returning for returning subs."""

    def test_resolve_mission_returning(self):
        from llm.prompts import _resolve_mission, _STATE_MISSIONS
        sub = make_sub(state=SubState.NEW, message_count=5)
        ctx = {"mission_key": "new", "is_returning": True}
        mission = _resolve_mission(sub, ctx)
        assert "DO NOT ask what brought him here" in mission
        assert "new_returning" in _STATE_MISSIONS  # Verify the key exists

    def test_resolve_mission_first_time(self):
        from llm.prompts import _resolve_mission
        sub = make_sub(state=SubState.NEW, message_count=0)
        ctx = {"mission_key": "new", "is_returning": False}
        mission = _resolve_mission(sub, ctx)
        assert "brand new subscriber" in mission

    def test_resolve_mission_no_is_returning_key(self):
        """If is_returning is missing from context, treat as first-time."""
        from llm.prompts import _resolve_mission
        sub = make_sub(state=SubState.NEW)
        ctx = {"mission_key": "new"}
        mission = _resolve_mission(sub, ctx)
        assert "brand new subscriber" in mission


# ═══════════════════════════════════════════════
# UPGRADE 8: Persona Self-Identity Memory
# ═══════════════════════════════════════════════

class TestPersonaFactExtraction:
    """Test extract_persona_facts from memory_extractor."""

    def test_extracts_hobby(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("i love going to the gym every morning")
        assert len(facts) >= 1
        categories = [c for c, _ in facts]
        assert "hobby" in categories

    def test_extracts_daily_life(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("i just got back from the beach with my friends")
        assert len(facts) >= 1
        categories = [c for c, _ in facts]
        assert "daily_life" in categories

    def test_extracts_opinion(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("i think people who ghost are the worst")
        assert len(facts) >= 1
        categories = [c for c, _ in facts]
        assert "opinion" in categories

    def test_extracts_food(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("i just had the best sushi downtown")
        assert len(facts) >= 1
        categories = [c for c, _ in facts]
        assert "food" in categories

    def test_ignores_short_messages(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("hey babe")
        assert facts == []

    def test_ignores_empty_messages(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts("")
        assert facts == []

    def test_detail_length_filters(self):
        from llm.memory_extractor import extract_persona_facts
        # Very short match should be filtered
        facts = extract_persona_facts("i love it!")
        # "it" is only 2 chars, should be filtered
        assert all(len(f) > 3 for _, f in facts)

    def test_multiple_categories_one_message(self):
        from llm.memory_extractor import extract_persona_facts
        facts = extract_persona_facts(
            "i love cooking Italian food and i think mondays are the worst"
        )
        categories = [c for c, _ in facts]
        # Should get at least hobby
        assert len(facts) >= 1


class TestPersonaMemoryStore:
    """Test store/retrieve persona facts (mocked Supabase)."""

    @pytest.mark.asyncio
    async def test_store_persona_fact_success(self):
        from llm.memory_store import store_persona_fact

        mock_sb = MagicMock()
        mock_sb.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "x"}])

        with patch("llm.memory_store._get_supabase", return_value=mock_sb), \
             patch("llm.memory_store._embed", return_value=[0.1] * 384):
            result = await store_persona_fact("model-123", "enjoys yoga", "hobby")
            assert result is True
            mock_sb.table.assert_called_with("persona_memory")

    @pytest.mark.asyncio
    async def test_store_persona_fact_no_supabase(self):
        from llm.memory_store import store_persona_fact

        with patch("llm.memory_store._get_supabase", return_value=None):
            result = await store_persona_fact("model-123", "enjoys yoga", "hobby")
            assert result is False

    @pytest.mark.asyncio
    async def test_store_persona_fact_no_embedding(self):
        from llm.memory_store import store_persona_fact

        mock_sb = MagicMock()
        with patch("llm.memory_store._get_supabase", return_value=mock_sb), \
             patch("llm.memory_store._embed", return_value=None):
            result = await store_persona_fact("model-123", "enjoys yoga", "hobby")
            assert result is False

    @pytest.mark.asyncio
    async def test_retrieve_persona_facts_success(self):
        from llm.memory_store import retrieve_persona_facts

        mock_sb = MagicMock()
        mock_sb.table.return_value.select.return_value.eq.return_value \
            .order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {"fact": "enjoys yoga"},
                {"fact": "food: sushi"},
            ]
        )

        with patch("llm.memory_store._get_supabase", return_value=mock_sb):
            facts = await retrieve_persona_facts("model-123", limit=5)
            assert len(facts) == 2
            assert "enjoys yoga" in facts

    @pytest.mark.asyncio
    async def test_retrieve_persona_facts_no_supabase(self):
        from llm.memory_store import retrieve_persona_facts

        with patch("llm.memory_store._get_supabase", return_value=None):
            facts = await retrieve_persona_facts("model-123")
            assert facts == []


class TestPersonaMemoryManager:
    """Test MemoryManager persona orchestration methods."""

    @pytest.mark.asyncio
    async def test_maybe_store_persona_facts_extracts_and_stores(self):
        from llm.memory_manager import memory_manager

        with patch("llm.memory_manager.store_persona_fact", new_callable=AsyncMock, return_value=True) as mock_store:
            count = await memory_manager.maybe_store_persona_facts(
                "i love going to the gym every morning",
                model_id="model-abc",
            )
            assert count >= 1
            mock_store.assert_called()

    @pytest.mark.asyncio
    async def test_maybe_store_persona_facts_no_model_id(self):
        from llm.memory_manager import memory_manager

        with patch.dict(os.environ, {"FANVUE_MODEL_ID": ""}):
            count = await memory_manager.maybe_store_persona_facts(
                "i love going to the gym",
                model_id="",
            )
            assert count == 0

    @pytest.mark.asyncio
    async def test_maybe_store_persona_facts_no_facts_found(self):
        from llm.memory_manager import memory_manager

        count = await memory_manager.maybe_store_persona_facts(
            "hey babe how are you",
            model_id="model-abc",
        )
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_persona_context_success(self):
        from llm.memory_manager import memory_manager

        with patch("llm.memory_manager.retrieve_persona_facts", new_callable=AsyncMock,
                    return_value=["enjoys yoga", "food: sushi"]):
            facts = await memory_manager.get_persona_context(model_id="model-abc")
            assert len(facts) == 2

    @pytest.mark.asyncio
    async def test_get_persona_context_no_model_id(self):
        from llm.memory_manager import memory_manager

        with patch.dict(os.environ, {"FANVUE_MODEL_ID": ""}):
            facts = await memory_manager.get_persona_context(model_id="")
            assert facts == []


class TestPersonaFactsInPrompt:
    """Test that persona facts are injected into build_full_prompt."""

    def test_persona_facts_in_prompt(self):
        from llm.prompts import build_full_prompt

        avatar = make_avatar()
        sub = make_sub(state=SubState.GFE_ACTIVE)
        sub.spending.total_spent = 50.0
        sub.spending.ppv_count = 1

        decision_ctx = {
            "pre_state": "gfe_active",
            "post_state": "gfe_active",
            "mission_key": "gfe_active",
            "has_ppv": False,
            "ppv_tier": None,
            "ppv_price": None,
            "objection_level": 0,
            "is_brokey": False,
            "session_locked": False,
            "loop_number": 0,
            "qualifying_q_index": 0,
            "days_silent": 0,
            "likely_bought": False,
            "template_messages": [],
            "content_description": {},
            "is_returning": False,
            "persona_facts": ["enjoys yoga", "food: the best sushi downtown"],
        }

        prompt = build_full_prompt(avatar, sub, decision_ctx, "hey babe")
        assert "Things you've mentioned about yourself in past conversations" in prompt
        assert "enjoys yoga" in prompt
        assert "food: the best sushi downtown" in prompt

    def test_no_persona_facts_block_when_empty(self):
        from llm.prompts import build_full_prompt

        avatar = make_avatar()
        sub = make_sub(state=SubState.GFE_ACTIVE)
        sub.spending.total_spent = 50.0

        decision_ctx = {
            "pre_state": "gfe_active",
            "post_state": "gfe_active",
            "mission_key": "gfe_active",
            "has_ppv": False,
            "ppv_tier": None,
            "ppv_price": None,
            "objection_level": 0,
            "is_brokey": False,
            "session_locked": False,
            "loop_number": 0,
            "qualifying_q_index": 0,
            "days_silent": 0,
            "likely_bought": False,
            "template_messages": [],
            "content_description": {},
            "is_returning": False,
            "persona_facts": [],
        }

        prompt = build_full_prompt(avatar, sub, decision_ctx, "hey babe")
        assert "Things you've mentioned about yourself" not in prompt


class TestMigrationFile:
    """Verify the SQL migration file exists and has correct structure."""

    def test_migration_file_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'migrations', 'deploy_persona_memory.sql'
        )
        assert os.path.exists(path)

    def test_migration_creates_table(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'migrations', 'deploy_persona_memory.sql'
        )
        with open(path) as f:
            content = f.read()
        assert "CREATE TABLE IF NOT EXISTS persona_memory" in content
        assert "model_id" in content
        assert "fact" in content
        assert "category" in content
        assert "embedding" in content
        assert "vector(384)" in content

    def test_migration_creates_indexes(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'migrations', 'deploy_persona_memory.sql'
        )
        with open(path) as f:
            content = f.read()
        assert "persona_memory_model_id_idx" in content
        assert "persona_memory_embedding_idx" in content
        assert "ivfflat" in content
