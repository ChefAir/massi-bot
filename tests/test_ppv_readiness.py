"""
Tests for the PPV readiness checker (llm/ppv_readiness.py).

Validates:
  - Returns True when LLM says YES
  - Returns False when LLM says NO
  - Returns False when API key is missing
  - Returns False when fewer than 2 messages provided
  - Returns False on LLM error (graceful fallback)
  - Correct prompt formatting
  - Integration with route_full PPV override

Run with: pytest tests/test_ppv_readiness.py -v
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import Subscriber, SubState, BotAction


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_recent_messages(engaged: bool = True) -> list[dict]:
    """Build a realistic recent_messages list."""
    if engaged:
        return [
            {"role": "bot", "content": "hey babe, what do you do for fun? 😏"},
            {"role": "sub", "content": "I'm a lawyer, but right now all I can think about is you"},
            {"role": "bot", "content": "mmm a lawyer... I bet you're used to getting what you want 😈"},
            {"role": "sub", "content": "I want you so bad right now, you're driving me crazy"},
        ]
    else:
        return [
            {"role": "bot", "content": "hey babe, what do you do for fun? 😏"},
            {"role": "sub", "content": "just chilling, watching tv"},
        ]


def _mock_completion(answer: str):
    """Create a mock OpenAI completion response."""
    choice = MagicMock()
    choice.message.content = answer
    completion = MagicMock()
    completion.choices = [choice]
    return completion


# ─────────────────────────────────────────────
# Unit tests for check_ppv_readiness
# ─────────────────────────────────────────────

@pytest.mark.anyio
async def test_ppv_readiness_yes():
    """LLM returns YES -> check_ppv_readiness returns True."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("YES")
    )

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        result = await check_ppv_readiness(
            make_recent_messages(engaged=True),
            "warming",
            4,
        )
    assert result is True


@pytest.mark.anyio
async def test_ppv_readiness_no():
    """LLM returns NO -> check_ppv_readiness returns False."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("NO")
    )

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        result = await check_ppv_readiness(
            make_recent_messages(engaged=False),
            "warming",
            2,
        )
    assert result is False


@pytest.mark.anyio
async def test_ppv_readiness_no_client():
    """No API key -> returns False (safe fallback)."""
    from llm.ppv_readiness import check_ppv_readiness

    with patch("llm.ppv_readiness._get_client", return_value=None):
        result = await check_ppv_readiness(
            make_recent_messages(engaged=True),
            "warming",
            4,
        )
    assert result is False


@pytest.mark.anyio
async def test_ppv_readiness_too_few_messages():
    """Fewer than 2 messages -> returns False (not enough context)."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("YES")
    )

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        result = await check_ppv_readiness(
            [{"role": "sub", "content": "hey"}],
            "warming",
            1,
        )
    assert result is False
    # LLM should NOT have been called
    mock_client.chat.completions.create.assert_not_called()


@pytest.mark.anyio
async def test_ppv_readiness_llm_error():
    """LLM call raises exception -> returns False (graceful fallback)."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=Exception("timeout")
    )

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        result = await check_ppv_readiness(
            make_recent_messages(engaged=True),
            "warming",
            4,
        )
    assert result is False


@pytest.mark.anyio
async def test_ppv_readiness_case_insensitive():
    """LLM returns 'yes' (lowercase) -> still returns True."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("yes")
    )

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        result = await check_ppv_readiness(
            make_recent_messages(engaged=True),
            "tension_build",
            5,
        )
    assert result is True


@pytest.mark.anyio
async def test_ppv_readiness_prompt_format():
    """Verify the prompt is formatted correctly with conversation and state."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("NO")
    )

    messages = [
        {"role": "bot", "content": "hey there"},
        {"role": "sub", "content": "hi babe"},
    ]

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        await check_ppv_readiness(messages, "warming", 3)

    # Verify the call was made with correct structure
    call_args = mock_client.chat.completions.create.call_args
    assert call_args.kwargs["model"] == "x-ai/grok-4.1-fast"
    assert call_args.kwargs["max_tokens"] == 5
    assert call_args.kwargs["temperature"] == 0.0
    prompt_content = call_args.kwargs["messages"][0]["content"]
    assert "Her: hey there" in prompt_content
    assert "Fan: hi babe" in prompt_content
    assert "warming" in prompt_content
    assert "3 messages" in prompt_content


@pytest.mark.anyio
async def test_ppv_readiness_truncates_long_messages():
    """Messages longer than 150 chars are truncated."""
    from llm.ppv_readiness import check_ppv_readiness

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_completion("NO")
    )

    long_msg = "x" * 300
    messages = [
        {"role": "bot", "content": "hi"},
        {"role": "sub", "content": long_msg},
    ]

    with patch("llm.ppv_readiness._get_client", return_value=mock_client):
        await check_ppv_readiness(messages, "warming", 2)

    call_args = mock_client.chat.completions.create.call_args
    prompt_content = call_args.kwargs["messages"][0]["content"]
    # The long message should be truncated to 150 chars
    assert "x" * 150 in prompt_content
    assert "x" * 151 not in prompt_content


# ─────────────────────────────────────────────
# Integration test: route_full PPV override
# ─────────────────────────────────────────────

def make_sub(state: SubState = SubState.WARMING) -> Subscriber:
    sub = Subscriber(
        sub_id="ppv-readiness-test",
        username="testfan",
        display_name="Test Fan",
        state=state,
        persona_id="luxury_baddie",
    )
    sub.qualifying_questions_asked = 1
    sub.message_count = 4
    sub.recent_messages = make_recent_messages(engaged=True)
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
    avatar.persona.voice.favorite_phrases = ["daddy", "I am expensive", "you're trouble"]
    avatar.persona.voice.reaction_phrases = ["omg", "stop it"]
    avatar.persona.ig_account_tag = "@luxury_baddie"
    return avatar


def make_warming_template_actions():
    """Template actions that the engine would return in WARMING state (no PPV)."""
    return [
        BotAction(
            action_type="send_message",
            message="mmm you're making me blush 😏",
            delay_seconds=15,
        ),
    ]


@pytest.mark.anyio
async def test_route_full_ppv_override_warming():
    """When PPV readiness says YES in WARMING, route_full should include a PPV action."""
    from llm.llm_router import LLMRouter

    sub = make_sub(state=SubState.WARMING)
    avatar = make_avatar()
    template_actions = make_warming_template_actions()
    pre_state = SubState.WARMING

    router = LLMRouter()

    # Mock: ppv_readiness returns True, LLM generates text, validator passes
    with patch("llm.ppv_readiness.check_ppv_readiness", new=AsyncMock(return_value=True)), \
         patch("llm.llm_router.llm_client") as mock_llm, \
         patch("llm.llm_router.memory_manager") as mock_mm, \
         patch("llm.llm_router.validate_response", new=AsyncMock(return_value=(True, None))), \
         patch("llm.llm_router.get_weather", new=AsyncMock(return_value=None)):
        mock_llm.is_available = True
        mock_llm.generate = AsyncMock(return_value="I have something special for you babe 😈")
        mock_mm.get_context_memories = AsyncMock(return_value=[])
        mock_mm.get_persona_context = AsyncMock(return_value=None)
        mock_mm.maybe_extract_and_store = AsyncMock(return_value=None)
        mock_mm.maybe_store_persona_facts = AsyncMock(return_value=None)

        result = await router.route_full(sub, "I want you so bad", avatar, template_actions, pre_state)

    # Should contain a PPV action (the override injected one)
    ppv_actions = [a for a in result if a.action_type == "send_ppv"]
    assert len(ppv_actions) >= 1, f"Expected PPV action in result, got: {[a.action_type for a in result]}"
    assert ppv_actions[0].ppv_price == 27.38  # Tier 1 price
    # State should have advanced to FIRST_PPV_SENT
    assert sub.state == SubState.FIRST_PPV_SENT


@pytest.mark.anyio
async def test_route_full_no_override_when_not_ready():
    """When PPV readiness says NO, route_full should NOT inject PPV actions."""
    from llm.llm_router import LLMRouter

    sub = make_sub(state=SubState.WARMING)
    avatar = make_avatar()
    template_actions = make_warming_template_actions()
    pre_state = SubState.WARMING

    router = LLMRouter()

    with patch("llm.ppv_readiness.check_ppv_readiness", new=AsyncMock(return_value=False)), \
         patch("llm.llm_router.llm_client") as mock_llm, \
         patch("llm.llm_router.memory_manager") as mock_mm, \
         patch("llm.llm_router.validate_response", new=AsyncMock(return_value=(True, None))), \
         patch("llm.llm_router.get_weather", new=AsyncMock(return_value=None)):
        mock_llm.is_available = True
        mock_llm.generate = AsyncMock(return_value="mmm you're so sweet 😏")
        mock_mm.get_context_memories = AsyncMock(return_value=[])
        mock_mm.get_persona_context = AsyncMock(return_value=None)
        mock_mm.maybe_extract_and_store = AsyncMock(return_value=None)
        mock_mm.maybe_store_persona_facts = AsyncMock(return_value=None)

        result = await router.route_full(sub, "just chilling", avatar, template_actions, pre_state)

    # Should NOT contain a PPV action
    ppv_actions = [a for a in result if a.action_type == "send_ppv"]
    assert len(ppv_actions) == 0, f"Expected no PPV action, got: {[a.action_type for a in result]}"


@pytest.mark.anyio
async def test_route_full_no_override_when_already_has_ppv():
    """When template_actions already has PPV, readiness check should NOT run."""
    from llm.llm_router import LLMRouter

    sub = make_sub(state=SubState.FIRST_PPV_READY)
    avatar = make_avatar()
    # Template already includes a PPV
    template_actions = [
        BotAction(action_type="send_message", message="here it comes...", delay_seconds=5),
        BotAction(
            action_type="send_ppv", ppv_price=27.38, ppv_caption="just for you",
            delay_seconds=8, metadata={"tier": "tier_1_body_tease"},
            new_state=SubState.FIRST_PPV_SENT,
        ),
    ]
    pre_state = SubState.FIRST_PPV_READY

    router = LLMRouter()

    with patch("llm.ppv_readiness.check_ppv_readiness", new=AsyncMock(return_value=True)) as mock_check, \
         patch("llm.llm_router.llm_client") as mock_llm, \
         patch("llm.llm_router.memory_manager") as mock_mm, \
         patch("llm.llm_router.validate_response", new=AsyncMock(return_value=(True, None))), \
         patch("llm.llm_router.get_weather", new=AsyncMock(return_value=None)):
        mock_llm.is_available = True
        mock_llm.generate = AsyncMock(return_value="here it comes babe 😈")
        mock_mm.get_context_memories = AsyncMock(return_value=[])
        mock_mm.get_persona_context = AsyncMock(return_value=None)
        mock_mm.maybe_extract_and_store = AsyncMock(return_value=None)
        mock_mm.maybe_store_persona_facts = AsyncMock(return_value=None)

        await router.route_full(sub, "show me", avatar, template_actions, pre_state)

    # Readiness check should NOT have been called (pre_state is FIRST_PPV_READY, not WARMING)
    mock_check.assert_not_called()


@pytest.mark.anyio
async def test_route_full_ppv_override_tension_build():
    """PPV readiness override also works for TENSION_BUILD state."""
    from llm.llm_router import LLMRouter

    sub = make_sub(state=SubState.TENSION_BUILD)
    avatar = make_avatar()
    template_actions = [
        BotAction(
            action_type="send_message",
            message="you're getting me worked up 😈",
            delay_seconds=10,
            new_state=SubState.FIRST_PPV_READY,
        ),
    ]
    pre_state = SubState.TENSION_BUILD

    router = LLMRouter()

    with patch("llm.ppv_readiness.check_ppv_readiness", new=AsyncMock(return_value=True)), \
         patch("llm.llm_router.llm_client") as mock_llm, \
         patch("llm.llm_router.memory_manager") as mock_mm, \
         patch("llm.llm_router.validate_response", new=AsyncMock(return_value=(True, None))), \
         patch("llm.llm_router.get_weather", new=AsyncMock(return_value=None)):
        mock_llm.is_available = True
        mock_llm.generate = AsyncMock(return_value="I have something for you 😈")
        mock_mm.get_context_memories = AsyncMock(return_value=[])
        mock_mm.get_persona_context = AsyncMock(return_value=None)
        mock_mm.maybe_extract_and_store = AsyncMock(return_value=None)
        mock_mm.maybe_store_persona_facts = AsyncMock(return_value=None)

        result = await router.route_full(sub, "I need you right now", avatar, template_actions, pre_state)

    ppv_actions = [a for a in result if a.action_type == "send_ppv"]
    assert len(ppv_actions) >= 1
    assert sub.state == SubState.FIRST_PPV_SENT
