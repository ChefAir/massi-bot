"""
Tests for the full-LLM routing mode (route_full).

Validates:
  - Decision context extraction from template BotActions
  - State-specific mission prompt generation
  - State-specific guardrail modes
  - PPV price/content_id preservation
  - Template fallback when LLM fails
  - Burst mode and delay application

Run with: pytest tests/test_llm_full_route.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber, SubState, SubType, BotAction, ScriptPhase


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_sub(state: SubState = SubState.QUALIFYING) -> Subscriber:
    sub = Subscriber(
        sub_id="full-llm-test",
        username="testfan",
        display_name="Test Fan",
        state=state,
        persona_id="luxury_baddie",
    )
    sub.qualifying_questions_asked = 1
    return sub


def make_avatar():
    avatar = MagicMock()
    avatar.persona = MagicMock()
    avatar.persona.name = "Jessica"
    avatar.persona.nickname = "Jess"
    avatar.persona.location_story = "Miami"
    avatar.persona.age = 24
    avatar.persona.niche_keywords = ["luxury", "lifestyle"]
    avatar.persona.niche_topics = ["fashion", "miami"]
    avatar.persona.voice = MagicMock()
    avatar.persona.voice.primary_tone = "confident & seductive"
    avatar.persona.voice.emoji_use = "moderate"
    avatar.persona.voice.flirt_style = "power_play"
    avatar.persona.voice.capitalization = "lowercase_casual"
    avatar.persona.voice.punctuation_style = "minimal"
    avatar.persona.voice.sexual_escalation_pace = "fast"
    avatar.persona.voice.greeting_style = "bold"
    avatar.persona.voice.message_length = "short"
    avatar.persona.voice.favorite_phrases = ["daddy 😈", "I am expensive", "you're trouble"]
    avatar.persona.voice.reaction_phrases = ["omg", "stop it"]
    avatar.persona.ig_account_tag = "@luxury_baddie"
    avatar.qualifying_questions = [
        {"question": "do you run your own business too? I can always tell 😏", "purpose": "income"},
        {"question": "what do you do when you're not here? 😏", "purpose": "lifestyle"},
        {"question": "what's your type?", "purpose": "attraction"},
    ]
    return avatar


def make_template_actions(
    msg="template response text",
    ppv=False,
    ppv_price=27.38,
    new_state=None,
):
    actions = [
        BotAction(
            action_type="send_message",
            message=msg,
            delay_seconds=45,
            new_state=new_state,
            metadata={"source": "template"},
        )
    ]
    if ppv:
        actions.append(BotAction(
            action_type="send_ppv",
            message="",
            ppv_price=ppv_price,
            ppv_caption="exclusive just for you 😈",
            content_id="bundle-001",
            delay_seconds=5,
            metadata={"tier": "tier_1_body_tease", "source": "template"},
        ))
    return actions


# ─────────────────────────────────────────────
# Decision context extraction tests
# ─────────────────────────────────────────────

class TestDecisionContextExtraction:

    def test_basic_context(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.WARMING)
        actions = make_template_actions()
        ctx = _extract_decision_context(sub, SubState.QUALIFYING, actions)
        assert ctx["pre_state"] == "qualifying"
        assert ctx["post_state"] == "warming"
        assert ctx["has_ppv"] is False
        assert ctx["mission_key"] == "qualifying"

    def test_ppv_context(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.FIRST_PPV_SENT)
        actions = make_template_actions(ppv=True, ppv_price=27.38)
        ctx = _extract_decision_context(sub, SubState.FIRST_PPV_READY, actions)
        assert ctx["has_ppv"] is True
        assert ctx["ppv_price"] == 27.38
        assert ctx["ppv_tier"] == "tier_1_body_tease"

    def test_objection_context_level1(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.FIRST_PPV_SENT)
        sub.tier_no_count = 1
        actions = make_template_actions()
        ctx = _extract_decision_context(sub, SubState.FIRST_PPV_SENT, actions)
        assert ctx["mission_key"] == "objection_1"

    def test_objection_context_level3(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.LOOPING)
        sub.tier_no_count = 3
        actions = make_template_actions()
        ctx = _extract_decision_context(sub, SubState.LOOPING, actions)
        assert ctx["mission_key"] == "objection_3"

    def test_brokey_context(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.FIRST_PPV_SENT)
        sub.tier_no_count = 3
        sub.brokey_flagged = True
        actions = make_template_actions()
        ctx = _extract_decision_context(sub, SubState.FIRST_PPV_SENT, actions)
        assert ctx["mission_key"] == "brokey_treatment"
        assert ctx["is_brokey"] is True

    def test_retention_locked_context(self):
        from llm.llm_router import _extract_decision_context
        sub = make_sub(SubState.RETENTION)
        sub.session_locked_until = datetime.now() + timedelta(hours=2)
        actions = make_template_actions()
        ctx = _extract_decision_context(sub, SubState.RETENTION, actions)
        assert ctx["mission_key"] == "retention_locked"
        assert ctx["session_locked"] is True


# ─────────────────────────────────────────────
# State mission prompt tests
# ─────────────────────────────────────────────

class TestStateMissionPrompts:

    def test_qualifying_prompt_includes_question(self):
        from llm.prompts import build_full_prompt
        sub = make_sub(SubState.QUALIFYING)
        sub.qualifying_questions_asked = 1
        avatar = make_avatar()
        ctx = {"mission_key": "qualifying", "has_ppv": False, "loop_number": 0}
        prompt = build_full_prompt(avatar, sub, ctx, "hey there")
        assert "do you run your own business" in prompt.lower() or "qualifying" in prompt.lower()

    def test_warming_prompt_has_selling_rules(self):
        from llm.prompts import build_full_prompt
        sub = make_sub(SubState.WARMING)
        avatar = make_avatar()
        ctx = {"mission_key": "warming", "has_ppv": False, "loop_number": 0}
        prompt = build_full_prompt(avatar, sub, ctx, "you're so hot")
        assert "NEVER mention dollar" in prompt

    def test_gfe_prompt_has_no_selling_rules(self):
        from llm.prompts import build_full_prompt
        sub = make_sub(SubState.GFE_ACTIVE)
        avatar = make_avatar()
        ctx = {"mission_key": "gfe_active", "has_ppv": False, "loop_number": 0}
        prompt = build_full_prompt(avatar, sub, ctx, "how was your day")
        assert "SELLING RULES" not in prompt
        assert "NO selling" in prompt

    def test_objection_prompt_has_ego_language(self):
        from llm.prompts import build_full_prompt
        sub = make_sub(SubState.FIRST_PPV_SENT)
        sub.tier_no_count = 2
        avatar = make_avatar()
        ctx = {"mission_key": "objection_2", "has_ppv": False, "loop_number": 0}
        prompt = build_full_prompt(avatar, sub, ctx, "too expensive")
        assert "ego" in prompt.lower() or "different" in prompt.lower()

    def test_prompt_includes_subscriber_name(self):
        from llm.prompts import build_full_prompt
        sub = make_sub()
        sub.display_name = "BigDaddy42"
        avatar = make_avatar()
        ctx = {"mission_key": "qualifying", "has_ppv": False, "loop_number": 0}
        prompt = build_full_prompt(avatar, sub, ctx, "hey")
        assert "BigDaddy42" in prompt


# ─────────────────────────────────────────────
# State-specific guardrail tests
# ─────────────────────────────────────────────

class TestStatefulGuardrails:

    def test_qualifying_blocks_explicit(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "I want to ride your cock so bad 😈",
            mode=GuardrailMode.QUALIFYING,
        )
        assert result is None

    def test_qualifying_allows_clean(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "omg hey you! tell me more about yourself 😏",
            mode=GuardrailMode.QUALIFYING,
        )
        assert result is not None

    def test_selling_blocks_prices(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "this is only $27 babe you can afford it 😏",
            mode=GuardrailMode.SELLING,
        )
        assert result is None

    def test_selling_allows_explicit(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "you have no idea what I want to do to you right now 😈",
            mode=GuardrailMode.SELLING,
        )
        assert result is not None

    def test_objection_blocks_soft_language(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "it's okay babe don't worry about it 😊",
            mode=GuardrailMode.OBJECTION,
        )
        assert result is None

    def test_objection_blocks_other_fans_reference(self):
        """Other fans reference should be blocked — kills intimacy illusion."""
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "I thought you were different... my other fans never hesitate 😏",
            mode=GuardrailMode.OBJECTION,
        )
        assert result is None  # Blocked: never mention other fans

    def test_objection_allows_wallet_ego_bruise(self):
        """Ego bruise through wallet concern should pass in objection mode."""
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "I get it baby... I don't wanna hurt your pockets 💕",
            mode=GuardrailMode.OBJECTION,
        )
        assert result is not None

    def test_standard_allows_anything_clean(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        result = post_process_stateful(
            "hey babe I miss you so much 💕 how was your day?",
            mode=GuardrailMode.STANDARD,
        )
        assert result is not None

    def test_ai_reference_blocked_all_modes(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        for mode in GuardrailMode:
            result = post_process_stateful(
                "as an AI I can help you with that",
                mode=mode,
            )
            assert result is None, f"AI reference should be blocked in {mode.value}"

    def test_selling_allows_4_sentences(self):
        from llm.guardrails import post_process_stateful, GuardrailMode
        text = (
            "omg you're making this so hard 😏. "
            "I've been thinking about you all day. "
            "you have no idea what I have for you. "
            "just say the word and I'll show you everything."
        )
        result = post_process_stateful(text, mode=GuardrailMode.SELLING)
        assert result is not None

    def test_get_mode_for_state(self):
        from llm.guardrails import get_mode_for_state, GuardrailMode
        assert get_mode_for_state("qualifying") == GuardrailMode.QUALIFYING
        assert get_mode_for_state("warming") == GuardrailMode.SELLING
        assert get_mode_for_state("gfe_active") == GuardrailMode.STANDARD
        assert get_mode_for_state("looping") == GuardrailMode.SELLING


# ─────────────────────────────────────────────
# route_full() integration tests
# ─────────────────────────────────────────────

class TestRouteFullIntegration:

    @pytest.mark.anyio
    async def test_replaces_message_text_with_llm(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(
                return_value="omg hey daddy 😈 so what do you do for fun?"
            )):
                router = LLMRouter()
                sub = make_sub(SubState.QUALIFYING)
                avatar = make_avatar()
                template = make_template_actions("boring template question")

                result = await router.route_full(
                    sub, "hey beautiful", avatar, template, SubState.QUALIFYING
                )

                assert len(result) >= 1
                msg_actions = [a for a in result if a.action_type == "send_message"]
                assert len(msg_actions) >= 1
                # Template text should be replaced
                assert msg_actions[0].message != "boring template question"
                assert msg_actions[0].metadata.get("source") == "llm_full"

    @pytest.mark.anyio
    async def test_preserves_ppv_price_and_content_id(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(
                return_value="you have no idea what I'm about to show you 😈"
            )):
                router = LLMRouter()
                sub = make_sub(SubState.FIRST_PPV_SENT)
                avatar = make_avatar()
                template = make_template_actions(ppv=True, ppv_price=27.38)

                result = await router.route_full(
                    sub, "show me", avatar, template, SubState.FIRST_PPV_READY
                )

                ppv_actions = [a for a in result if a.action_type == "send_ppv"]
                assert len(ppv_actions) == 1
                assert ppv_actions[0].ppv_price == 27.38
                assert ppv_actions[0].content_id == "bundle-001"
                assert ppv_actions[0].ppv_caption == "exclusive just for you 😈"

    @pytest.mark.anyio
    async def test_fallback_to_templates_when_llm_fails(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(return_value=None)):
                router = LLMRouter()
                sub = make_sub(SubState.WARMING)
                avatar = make_avatar()
                template = make_template_actions("template fallback text")

                result = await router.route_full(
                    sub, "hey", avatar, template, SubState.QUALIFYING
                )

                # Should return template actions unchanged
                assert len(result) == 1
                assert result[0].message == "template fallback text"

    @pytest.mark.anyio
    async def test_fallback_when_no_avatar(self):
        from llm.llm_router import LLMRouter
        router = LLMRouter()
        sub = make_sub()
        template = make_template_actions("template text")

        result = await router.route_full(
            sub, "hey", None, template, SubState.QUALIFYING
        )
        assert result[0].message == "template text"

    @pytest.mark.anyio
    async def test_fallback_when_guardrails_reject(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(
                return_value="As an AI I cannot discuss that."
            )):
                router = LLMRouter()
                sub = make_sub(SubState.WARMING)
                avatar = make_avatar()
                template = make_template_actions("safe template text")

                result = await router.route_full(
                    sub, "hey", avatar, template, SubState.QUALIFYING
                )

                # Guardrails should reject → fallback to template
                assert result[0].message == "safe template text"

    @pytest.mark.anyio
    async def test_preserves_state_transition(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(
                return_value="omg tell me more 😈"
            )):
                router = LLMRouter()
                sub = make_sub(SubState.CLASSIFIED)
                avatar = make_avatar()
                template = make_template_actions(
                    "template text",
                    new_state=SubState.WARMING,
                )

                result = await router.route_full(
                    sub, "I'm 30 from NYC", avatar, template, SubState.QUALIFYING
                )

                # The state transition should be preserved
                has_transition = any(
                    a.new_state == SubState.WARMING
                    for a in result
                )
                assert has_transition

    @pytest.mark.anyio
    async def test_dynamic_delays_applied(self):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(
                return_value="hey 😏"
            )):
                router = LLMRouter()
                sub = make_sub(SubState.WARMING)
                avatar = make_avatar()
                template = make_template_actions()

                result = await router.route_full(
                    sub, "hello", avatar, template, SubState.QUALIFYING
                )

                # LLM actions should have dynamic delays (not the template's 45s)
                msg_actions = [a for a in result if a.action_type == "send_message"]
                assert len(msg_actions) >= 1
                # Delay should be reasonable (3-150s range from calculate_reply_delay)
                assert 3 <= msg_actions[0].delay_seconds <= 150
