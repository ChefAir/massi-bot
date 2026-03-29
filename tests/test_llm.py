"""
Tests for the LLM integration layer.

Mocks: OpenAI client, LLM responses.
Run with: pytest tests/test_llm.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber, SubState, SubType, QualifyingData, SpendingHistory


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_sub(state: SubState = SubState.GFE_ACTIVE) -> Subscriber:
    sub = Subscriber(
        sub_id="llm-test-sub",
        username="testuser",
        display_name="Test User",
        state=state,
        persona_id="girl_boss",
    )
    sub.qualifying.age = 32
    sub.qualifying.occupation = "engineer"
    sub.qualifying.location = "NYC"
    sub.callback_references = ["loves football", "works 80 hour weeks"]
    sub.spending.total_spent = 77.35
    sub.spending.ppv_count = 2
    sub.recent_messages = [
        {"role": "sub", "content": "hey beautiful"},
        {"role": "bot", "content": "hey you 😏 what's up?"},
    ]
    return sub


def make_avatar():
    avatar = MagicMock()
    avatar.persona = MagicMock()
    avatar.persona.name = "Jasmine"
    avatar.persona.nickname = "Jazz"
    avatar.persona.location_story = "Miami"
    avatar.persona.age = 24
    avatar.persona.niche_keywords = ["fitness", "lifestyle"]
    avatar.persona.niche_topics = ["gym", "miami"]
    avatar.persona.voice = MagicMock()
    avatar.persona.voice.primary_tone = "flirty & sweet"
    avatar.persona.voice.emoji_use = "moderate"
    avatar.persona.voice.flirt_style = "playful"
    avatar.persona.voice.capitalization = "lowercase_casual"
    avatar.persona.voice.punctuation_style = "minimal"
    avatar.persona.voice.sexual_escalation_pace = "slow_burn"
    avatar.persona.voice.greeting_style = "casual"
    avatar.persona.voice.message_length = "short"
    avatar.persona.voice.favorite_phrases = ["stop it 😩", "I can't with you", "you're trouble"]
    avatar.persona.voice.reaction_phrases = ["omg stahp", "I can't"]
    return avatar


# ─────────────────────────────────────────────
# guardrails.py tests
# ─────────────────────────────────────────────

class TestGuardrails:

    def test_valid_response_passes(self):
        from llm.guardrails import post_process
        result = post_process("hey what's up 😏 I was just thinking about you.")
        assert result is not None
        assert "😏" in result

    def test_empty_response_returns_none(self):
        from llm.guardrails import post_process
        assert post_process("") is None
        assert post_process("   ") is None

    def test_ai_self_reference_rejected(self):
        from llm.guardrails import post_process
        assert post_process("as an AI I cannot do that.") is None
        assert post_process("I'm an AI language model.") is None
        assert post_process("I cannot send you that.") is None
        assert post_process("I'm not able to do that.") is None

    def test_openai_reference_rejected(self):
        from llm.guardrails import post_process
        assert post_process("I was made by OpenAI you know.") is None

    def test_anthropic_reference_rejected(self):
        from llm.guardrails import post_process
        assert post_process("Anthropic built me for this.") is None

    def test_phone_number_rejected(self):
        from llm.guardrails import post_process
        assert post_process("Call me at 555-867-5309 😘") is None

    def test_email_rejected(self):
        from llm.guardrails import post_process
        assert post_process("Email me at jasmine@gmail.com babe") is None

    def test_contact_info_phrase_rejected(self):
        from llm.guardrails import post_process
        assert post_process("add me on Instagram for more 😘") is None

    def test_truncates_to_3_sentences(self):
        from llm.guardrails import post_process
        long_response = (
            "I was thinking about you. You make me smile. "
            "I wish you were here. Come visit me. "
            "We'd have so much fun. You know what I mean 😏"
        )
        result = post_process(long_response)
        assert result is not None
        # Count sentences by splitting on common sentence enders
        import re
        sentences = [s for s in re.split(r"[.!?]", result) if s.strip()]
        assert len(sentences) <= 3

    def test_appends_emoji_when_missing(self):
        from llm.guardrails import post_process
        result = post_process("hey what are you up to today")
        assert result is not None
        # Should have at least one emoji appended
        import re
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F900-\U0001FAFF"
            "\U00002702-\U000027B0❤️💕]+"
        )
        assert emoji_pattern.search(result), f"No emoji found in: {result}"

    def test_preserves_existing_emoji(self):
        from llm.guardrails import post_process
        result = post_process("omg stop it 😩 you're literally the worst.")
        assert result is not None
        assert "😩" in result

    def test_uses_avatar_emojis_when_provided(self):
        from llm.guardrails import post_process
        result = post_process("hey you", avatar_emojis=["🔥", "🥵"])
        assert result is not None

    def test_response_ends_with_punctuation(self):
        from llm.guardrails import post_process
        result = post_process("I miss you so much")
        assert result is not None
        assert result[-1] in ".!?"

    # U12: AI vocabulary guardrails
    def test_ai_vocabulary_word_rejected(self):
        from llm.guardrails import post_process
        assert post_process("I'd love to delve into that with you 😏") is None

    def test_ai_vocabulary_nuanced_rejected(self):
        from llm.guardrails import post_process
        assert post_process("It's a nuanced situation honestly 😅") is None

    def test_ai_vocabulary_certainly_rejected(self):
        from llm.guardrails import post_process
        assert post_process("Certainly! I'll tell you all about it 💕") is None

    def test_sycophantic_opener_rejected(self):
        from llm.guardrails import post_process
        assert post_process("Great question! I love when you ask me things like that 😘") is None
        assert post_process("Absolutely! You're so right about that 🔥") is None

    def test_clean_casual_response_passes(self):
        from llm.guardrails import post_process
        result = post_process("omg stop you're making me blush rn 😍 tell me more")
        assert result is not None


# ─────────────────────────────────────────────
# prompts.py tests
# ─────────────────────────────────────────────

class TestPrompts:

    def test_build_system_prompt_contains_persona_name(self):
        from llm.prompts import build_system_prompt
        sub = make_sub()
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "Jasmine" in prompt

    def test_build_system_prompt_contains_subscriber_details(self):
        from llm.prompts import build_system_prompt
        sub = make_sub()
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "engineer" in prompt
        assert "NYC" in prompt
        assert "loves football" in prompt

    def test_build_system_prompt_contains_rules(self):
        from llm.prompts import build_system_prompt
        sub = make_sub()
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "NEVER break character" in prompt
        assert "NEVER" in prompt

    def test_gfe_context_instructions_for_gfe_state(self):
        from llm.prompts import build_system_prompt
        sub = make_sub(state=SubState.GFE_ACTIVE)
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub, context_type="gfe_conversation")
        assert "girlfriend" in prompt.lower() or "GFE" in prompt

    def test_retention_locked_context_for_locked_state(self):
        from llm.prompts import build_system_prompt
        sub = make_sub(state=SubState.RETENTION)
        sub.session_locked_until = datetime.now() + timedelta(hours=2)
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "locked" in prompt.lower() or "tomorrow" in prompt.lower()

    def test_re_engagement_context_for_re_engagement_state(self):
        from llm.prompts import build_system_prompt
        sub = make_sub(state=SubState.RE_ENGAGEMENT)
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "quiet" in prompt.lower() or "miss" in prompt.lower() or "disappear" in prompt.lower()

    def test_build_messages_includes_system_prompt(self):
        from llm.prompts import build_messages
        messages = build_messages("system content here", make_sub(), "hello")
        assert messages[0]["role"] == "system"
        assert "system content here" in messages[0]["content"]

    def test_build_messages_last_entry_is_user(self):
        from llm.prompts import build_messages
        messages = build_messages("sys", make_sub(), "what are you doing?")
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "what are you doing?"

    def test_build_messages_maps_sub_role_to_user(self):
        from llm.prompts import build_messages
        sub = make_sub()
        sub.recent_messages = [{"role": "sub", "content": "hi"}]
        messages = build_messages("sys", sub, "hello")
        # The sub message should be mapped to "user"
        history_msgs = [m for m in messages if m["role"] != "system"]
        user_msgs = [m for m in history_msgs if m["role"] == "user"]
        assert any(m["content"] == "hi" for m in user_msgs)

    def test_build_messages_maps_bot_role_to_assistant(self):
        from llm.prompts import build_messages
        sub = make_sub()
        sub.recent_messages = [{"role": "bot", "content": "hey 😏"}]
        messages = build_messages("sys", sub, "hello")
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        assert any(m["content"] == "hey 😏" for m in assistant_msgs)

    def test_build_messages_limits_history_to_10(self):
        from llm.prompts import build_messages
        sub = make_sub()
        sub.recent_messages = [
            {"role": "sub", "content": f"msg {i}"} for i in range(20)
        ]
        messages = build_messages("sys", sub, "new message")
        # 1 system + up to 10 history + 1 current = max 12
        assert len(messages) <= 12

    def test_spending_shown_in_prompt(self):
        from llm.prompts import build_system_prompt
        sub = make_sub()
        sub.spending.total_spent = 127.45
        avatar = make_avatar()
        prompt = build_system_prompt(avatar, sub)
        assert "127.45" in prompt

    def test_whale_score_personality_note(self):
        from llm.prompts import _sub_personality_note
        sub = make_sub()
        sub.spending.total_spent = 600.0
        # whale_score property is computed from the dataclass — just test the function
        assert "whale" in _sub_personality_note(sub).lower() or "buyer" in _sub_personality_note(sub).lower()


# ─────────────────────────────────────────────
# llm_client.py tests
# ─────────────────────────────────────────────

class TestLLMClient:

    def test_is_available_false_when_no_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "venice")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        from llm.llm_client import LLMClient
        client = LLMClient()
        assert client.is_available is False

    def test_is_available_true_when_key_present(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "venice")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test123")
        from llm.llm_client import LLMClient
        client = LLMClient()
        assert client.is_available is True

    @pytest.mark.anyio
    async def test_generate_returns_none_when_unavailable(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "venice")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        from llm.llm_client import LLMClient
        client = LLMClient()
        result = await client.generate([{"role": "user", "content": "hello"}])
        assert result is None

    @pytest.mark.anyio
    async def test_generate_returns_text_on_success(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "venice")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test123")

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = "hey what's up 😏"
        mock_completion.usage = MagicMock()
        mock_completion.usage.total_tokens = 15

        from llm.llm_client import LLMClient
        client = LLMClient()

        with patch.object(client, "_get_client") as mock_get:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_get.return_value = (mock_openai, "venice/uncensored:free")
            client._client = mock_openai  # pre-set to skip init
            client._model = "venice/uncensored:free"

            result = await client.generate([{"role": "user", "content": "hello"}])
            assert result == "hey what's up 😏"

    @pytest.mark.anyio
    async def test_generate_returns_none_on_exception(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "venice")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test123")

        from llm.llm_client import LLMClient
        client = LLMClient()

        with patch.object(client, "_get_client") as mock_get:
            mock_openai = AsyncMock()
            mock_openai.chat.completions.create = AsyncMock(
                side_effect=Exception("Connection timeout")
            )
            mock_get.return_value = (mock_openai, "venice/uncensored:free")
            client._client = mock_openai
            client._model = "venice/uncensored:free"

            result = await client.generate([{"role": "user", "content": "hello"}])
            assert result is None


# ─────────────────────────────────────────────
# llm_router.py tests
# ─────────────────────────────────────────────

class TestLLMRouter:

    def test_should_use_llm_true_for_gfe_active(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient
        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            router = LLMRouter()
            sub = make_sub(state=SubState.GFE_ACTIVE)
            assert router.should_use_llm(sub) is True

    def test_should_use_llm_true_for_retention(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient
        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            router = LLMRouter()
            sub = make_sub(state=SubState.RETENTION)
            assert router.should_use_llm(sub) is True

    def test_should_use_llm_true_for_re_engagement(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient
        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            router = LLMRouter()
            sub = make_sub(state=SubState.RE_ENGAGEMENT)
            assert router.should_use_llm(sub) is True

    def test_should_use_llm_false_for_warming(self, monkeypatch):
        from llm.llm_router import LLMRouter
        router = LLMRouter()
        sub = make_sub(state=SubState.WARMING)
        assert router.should_use_llm(sub) is False

    def test_should_use_llm_false_for_looping(self, monkeypatch):
        from llm.llm_router import LLMRouter
        router = LLMRouter()
        sub = make_sub(state=SubState.LOOPING)
        assert router.should_use_llm(sub) is False

    def test_should_use_llm_false_for_first_ppv_sent(self, monkeypatch):
        from llm.llm_router import LLMRouter
        router = LLMRouter()
        sub = make_sub(state=SubState.FIRST_PPV_SENT)
        assert router.should_use_llm(sub) is False

    def test_should_use_llm_false_when_client_unavailable(self, monkeypatch):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient
        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=False):
            router = LLMRouter()
            sub = make_sub(state=SubState.GFE_ACTIVE)
            assert router.should_use_llm(sub) is False

    @pytest.mark.anyio
    async def test_route_returns_none_for_template_state(self):
        from llm.llm_router import LLMRouter
        router = LLMRouter()
        sub = make_sub(state=SubState.WARMING)
        avatar = make_avatar()
        result = await router.route(sub, "hello", avatar)
        assert result is None

    @pytest.mark.anyio
    async def test_route_returns_llm_response_for_gfe_state(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm import llm_client as client_module
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(
                client_module.llm_client,
                "generate",
                new_callable=AsyncMock,
                return_value="omg stop it 😩 you're literally the worst",
            ):
                router = LLMRouter()
                sub = make_sub(state=SubState.GFE_ACTIVE)
                avatar = make_avatar()
                result = await router.route(sub, "hey beautiful", avatar)
                # route() now returns list[BotAction] — check the first message text
                assert result is not None
                assert isinstance(result, list)
                assert len(result) >= 1
                full_text = " ".join(a.message for a in result)
                assert "😩" in full_text

    @pytest.mark.anyio
    async def test_route_returns_none_when_llm_fails(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm import llm_client as client_module
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(
                client_module.llm_client,
                "generate",
                new_callable=AsyncMock,
                return_value=None,  # LLM timeout/error
            ):
                router = LLMRouter()
                sub = make_sub(state=SubState.GFE_ACTIVE)
                result = await router.route(sub, "hey", make_avatar())
                assert result is None

    @pytest.mark.anyio
    async def test_route_returns_none_when_guardrails_fail(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
        from llm.llm_router import LLMRouter
        from llm import llm_client as client_module
        from llm.llm_client import LLMClient

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(
                client_module.llm_client,
                "generate",
                new_callable=AsyncMock,
                return_value="As an AI I cannot discuss that.",  # guardrail trigger
            ):
                router = LLMRouter()
                sub = make_sub(state=SubState.GFE_ACTIVE)
                result = await router.route(sub, "hey", make_avatar())
                assert result is None  # guardrails rejected → None

    @pytest.mark.anyio
    async def test_route_returns_none_when_no_avatar(self, monkeypatch):
        from llm.llm_router import LLMRouter
        from llm.llm_client import LLMClient
        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            router = LLMRouter()
            sub = make_sub(state=SubState.GFE_ACTIVE)
            result = await router.route(sub, "hey", None)  # no avatar
            assert result is None

    def test_wrap_as_action_returns_bot_action(self):
        from llm.llm_router import LLMRouter
        from models import BotAction
        router = LLMRouter()
        action = router.wrap_as_action("hey you 😏")
        assert isinstance(action, BotAction)
        assert action.action_type == "send_message"
        assert action.message == "hey you 😏"
        assert action.delay_seconds > 0
        assert action.metadata.get("source") == "llm"

    def test_template_only_states_covers_selling_pipeline(self):
        from llm.llm_router import TEMPLATE_ONLY_STATES
        selling_states = [
            SubState.WARMING, SubState.TENSION_BUILD,
            SubState.FIRST_PPV_READY, SubState.FIRST_PPV_SENT,
            SubState.LOOPING, SubState.CUSTOM_PITCH,
            SubState.POST_SESSION,
        ]
        for state in selling_states:
            assert state in TEMPLATE_ONLY_STATES, f"{state} should be template-only"

    def test_llm_eligible_states_are_non_selling(self):
        from llm.llm_router import LLM_ELIGIBLE_STATES
        assert SubState.GFE_ACTIVE in LLM_ELIGIBLE_STATES
        assert SubState.RETENTION in LLM_ELIGIBLE_STATES
        assert SubState.RE_ENGAGEMENT in LLM_ELIGIBLE_STATES
        # Verify no selling states leaked in
        assert SubState.LOOPING not in LLM_ELIGIBLE_STATES
        assert SubState.FIRST_PPV_SENT not in LLM_ELIGIBLE_STATES


# ─────────────────────────────────────────────
# Bridge signal detection tests
# ─────────────────────────────────────────────

class TestBridgeSignalDetection:

    def test_explicit_message_triggers_bridge(self):
        from llm.llm_router import _should_bridge
        assert _should_bridge("I'm so hard right now") is True
        assert _should_bridge("I'm stroking to your pics") is True
        assert _should_bridge("you're making me horny") is True
        assert _should_bridge("I can't stop thinking about you") is True

    def test_price_objection_does_not_trigger_bridge(self):
        from llm.llm_router import _should_bridge
        assert _should_bridge("that's too expensive") is False
        assert _should_bridge("I can't afford that") is False
        assert _should_bridge("too much money") is False

    def test_short_message_does_not_trigger_bridge(self):
        from llm.llm_router import _should_bridge
        assert _should_bridge("ok") is False
        assert _should_bridge("lol nice") is False

    def test_system_message_does_not_trigger_bridge(self):
        from llm.llm_router import _should_bridge
        assert _should_bridge("[PURCHASE_CONFIRMED]") is False

    def test_neutral_message_does_not_trigger_bridge(self):
        from llm.llm_router import _should_bridge
        assert _should_bridge("what are you up to today") is False
        assert _should_bridge("how is your day going") is False

    @pytest.mark.asyncio
    async def test_route_bridge_returns_none_for_non_bridge_state(self):
        from llm.llm_router import llm_router
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from models import Subscriber, SubState
        sub = Subscriber(sub_id="test_bridge", username="testuser")
        sub.state = SubState.GFE_ACTIVE  # Not a bridge state
        result = await llm_router.route_bridge(sub, "I'm so hard right now", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_route_bridge_returns_none_for_non_engagement_message(self):
        from llm.llm_router import llm_router
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from models import Subscriber, SubState
        sub = Subscriber(sub_id="test_bridge2", username="testuser")
        sub.state = SubState.LOOPING
        result = await llm_router.route_bridge(sub, "ok cool", None)
        assert result is None

    @pytest.mark.asyncio
    async def test_route_bridge_returns_action_on_success(self):
        from llm.llm_router import llm_router
        from llm.llm_client import LLMClient
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from models import Subscriber, SubState
        from avatars import LUXURY_BADDIE

        sub = Subscriber(sub_id="test_bridge3", username="testuser")
        sub.state = SubState.LOOPING

        with patch.object(LLMClient, "is_available", new_callable=PropertyMock, return_value=True):
            with patch.object(LLMClient, "generate", new=AsyncMock(return_value="good... that's exactly where I want you 😈")):
                actions = await llm_router.route_bridge(sub, "I'm so hard right now", LUXURY_BADDIE)

        assert actions is not None
        assert len(actions) == 1
        assert actions[0].action_type == "send_message"
        assert actions[0].metadata.get("source") == "llm_bridge"

    def test_bridge_eligible_states_are_selling_pipeline(self):
        from llm.llm_router import BRIDGE_ELIGIBLE_STATES
        assert SubState.WARMING in BRIDGE_ELIGIBLE_STATES
        assert SubState.TENSION_BUILD in BRIDGE_ELIGIBLE_STATES
        assert SubState.FIRST_PPV_READY in BRIDGE_ELIGIBLE_STATES
        assert SubState.FIRST_PPV_SENT in BRIDGE_ELIGIBLE_STATES
        assert SubState.LOOPING in BRIDGE_ELIGIBLE_STATES
        # GFE states should NOT be in bridge (they use full LLM)
        assert SubState.GFE_ACTIVE not in BRIDGE_ELIGIBLE_STATES

    def test_build_bridge_prompt_includes_fan_message(self):
        from llm.prompts import build_bridge_prompt
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from avatars import LUXURY_BADDIE
        from models import Subscriber
        sub = Subscriber(sub_id="x", username="y")
        prompt = build_bridge_prompt(LUXURY_BADDIE, sub, "I'm stroking to your pics")
        assert "I'm stroking to your pics" in prompt
        assert "price" in prompt.lower() or "sale" in prompt.lower() or "NOT mention" in prompt


# ─────────────────────────────────────────────
# U13: Same-day pitch dedup tests
# ─────────────────────────────────────────────

class TestSameDayPitchDedup:

    def _make_sub(self, last_pitch_at=None):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from models import Subscriber
        sub = Subscriber(sub_id="test_dedup", username="testuser")
        sub.last_pitch_at = last_pitch_at
        return sub

    def test_pitched_today_false_when_never_pitched(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from engine_v2 import IntegratedEngine
        sub = self._make_sub()
        assert IntegratedEngine._pitched_today(sub) is False

    def test_pitched_today_true_when_pitched_today(self):
        import sys, os
        from datetime import datetime
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from engine_v2 import IntegratedEngine
        sub = self._make_sub(last_pitch_at=datetime.now())
        assert IntegratedEngine._pitched_today(sub) is True

    def test_pitched_today_false_when_pitched_yesterday(self):
        import sys, os
        from datetime import datetime, timedelta
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from engine_v2 import IntegratedEngine
        sub = self._make_sub(last_pitch_at=datetime.now() - timedelta(days=1))
        assert IntegratedEngine._pitched_today(sub) is False

    def test_last_pitch_at_set_on_first_ppv(self):
        """_handle_first_ppv sets sub.last_pitch_at to now."""
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
        from datetime import datetime
        from models import Subscriber, SubState
        from engine_v2 import IntegratedEngine
        from avatars import ALL_AVATARS
        engine = IntegratedEngine(avatars=ALL_AVATARS)
        sub = Subscriber(sub_id="testppv", username="ppvtest")
        sub.state = SubState.FIRST_PPV_READY
        sub.persona_id = "example_model"
        assert sub.last_pitch_at is None
        engine._handle_first_ppv(sub, "send it", {})
        assert sub.last_pitch_at is not None
        assert sub.last_pitch_at.date() == datetime.now().date()
