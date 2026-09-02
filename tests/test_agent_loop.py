"""
Tests for the ReAct-style agent loop in ``SkillRouter.process_query_events``:
multi-tool turns, error feedback, step budgets, legacy single-shot mode and
LLM failure handling. All LLM calls are mocked; no network access happens.
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from router.router import SkillRouter
from core.memory import Memory
from core.skill_registry import SkillRegistry
from core.config import SynapseConfig


def _tool_call(name, arguments):
    tc = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _text_message(content):
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = content
    return msg


def _tool_message(tool_calls):
    msg = MagicMock()
    msg.tool_calls = tool_calls
    msg.content = None
    return msg


@pytest.fixture
def router(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    config = SynapseConfig(max_steps=5, trace_enabled=False)
    r = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    r.sandbox = None
    r.memory = Memory(max_history=10)
    return r


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_multiple_tool_calls_all_executed(mock_create, router):
    """Bug-27, fixed properly: every tool call of a turn runs, each result is
    fed back as its own tool message."""
    mock_weather = MagicMock()
    mock_weather.execute = AsyncMock(return_value="sunny 20C")
    mock_calc = MagicMock()
    mock_calc.execute = AsyncMock(return_value="42")

    call1 = _tool_message([_tool_call("weather_skill", {"location": "X"}), _tool_call("calculator_skill", {"expression": "1+1"})])
    final = _text_message("done")

    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=call1)]),
        MagicMock(choices=[MagicMock(message=final)]),
    ]

    with patch.object(router, "skills", {"weather_skill": mock_weather, "calculator_skill": mock_calc}):
        events = [e async for e in router.process_query_events("q")]

    tool_starts = [e for e in events if e["type"] == "tool_start"]
    assert [t["name"] for t in tool_starts] == ["weather_skill", "calculator_skill"]
    mock_weather.execute.assert_awaited_once()
    mock_calc.execute.assert_awaited_once()

    # Both tool results fed back in the second LLM round
    second_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_msgs = [m for m in second_messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert events[-1]["type"] == "final"
    assert events[-1]["text"] == "done"


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_skill_failure_is_fed_back_not_raised(mock_create, router):
    """A crashing skill must not crash the loop: the error goes back to the
    LLM as a tool message, and the loop continues."""
    bad_skill = MagicMock()
    bad_skill.execute = AsyncMock(side_effect=RuntimeError("boom"))
    call1 = _tool_message([_tool_call("bad_skill", {"x": 1})])
    final = _text_message("the skill failed, sorry")

    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=call1)]),
        MagicMock(choices=[MagicMock(message=final)]),
    ]

    with patch.object(router, "skills", {"bad_skill": bad_skill}):
        result = await router.process_query("q")

    assert result == "the skill failed, sorry"
    second_messages = mock_create.call_args_list[1].kwargs["messages"]
    tool_msg = [m for m in second_messages if m.get("role") == "tool"][0]
    assert "boom" in tool_msg["content"]
    # failure recorded exactly once
    stats = router.registry.get_stats("bad_skill")
    assert stats["failure_count"] == 1


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_unknown_tool_error_fed_back(mock_create, router):
    call1 = _tool_message([_tool_call("nonexistent_skill", {"x": 1})])
    final = _text_message("no such tool")
    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=call1)]),
        MagicMock(choices=[MagicMock(message=final)]),
    ]
    result = await router.process_query("q")
    assert result == "no such tool"
    tool_msg = [m for m in mock_create.call_args_list[1].kwargs["messages"] if m.get("role") == "tool"][0]
    assert "does not exist" in tool_msg["content"]


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_invalid_json_arguments_fed_back(mock_create, router):
    tc = MagicMock()
    tc.function.name = "weather_skill"
    tc.function.arguments = "{not json"
    call1 = _tool_message([tc])
    final = _text_message("hmm")
    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=call1)]),
        MagicMock(choices=[MagicMock(message=final)]),
    ]
    result = await router.process_query("q")
    assert result == "hmm"
    tool_msg = [m for m in mock_create.call_args_list[1].kwargs["messages"] if m.get("role") == "tool"][0]
    assert "not valid JSON" in tool_msg["content"]


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_max_steps_budget_returns_last_tool_result(mock_create, tmpdir):
    """With max_steps=2 and an LLM that always calls tools, the loop must stop
    and surface the last tool result instead of looping forever."""
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(max_steps=2, trace_enabled=False)
    r = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    r.sandbox = None
    r.memory = Memory(max_history=10)

    skill = MagicMock()
    skill.execute = AsyncMock(return_value="partial result")
    endless_call = _tool_message([_tool_call("loop_skill", {"x": 1})])
    mock_create.return_value = MagicMock(choices=[MagicMock(message=endless_call)])

    with patch.object(r, "skills", {"loop_skill": skill}):
        result = await r.process_query("q")

    assert "partial result" in result
    assert mock_create.call_count == 2  # step budget respected


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_legacy_single_shot_mode_returns_pydantic_result(mock_create, tmpdir):
    """max_steps=1 restores the original single-shot contract: the skill's
    structured result is returned directly."""
    from skills.weather_skill import WeatherResponse

    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(max_steps=1, trace_enabled=False)
    r = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    r.sandbox = None
    r.memory = Memory(max_history=10)

    skill = MagicMock()
    skill.execute = AsyncMock(return_value=WeatherResponse(
        location="X", weather="Clear sky", temperature=25.0))
    call1 = _tool_message([_tool_call("weather_skill", {"location": "X"})])
    mock_create.return_value = MagicMock(choices=[MagicMock(message=call1)])

    with patch.object(r, "skills", {"weather_skill": skill}):
        result = await r.process_query("q")

    assert isinstance(result, WeatherResponse)
    assert result.temperature == 25.0


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_llm_transport_failure_returns_error_text(mock_create, router):
    mock_create.side_effect = ConnectionError("network down")
    result = await router.process_query("q")
    assert isinstance(result, str)
    assert "LLM call failed" in result


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_duplicate_skill_request_not_generated_twice(mock_create, router):
    """request_new_skill called twice for the same intent only triggers one
    generation round."""
    from meta.skill_creator import SkillCreator

    call1 = _tool_message([_tool_call("request_new_skill", {"intent": "do X"})])
    call2 = _tool_message([_tool_call("request_new_skill", {"intent": "do X"})])
    final = _text_message("ok")
    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=call1)]),
        MagicMock(choices=[MagicMock(message=call2)]),
        MagicMock(choices=[MagicMock(message=final)]),
    ]

    with patch.object(SkillCreator, "generate_skill", new_callable=AsyncMock, return_value=True) as gen, \
         patch.object(router, "_discover_skills", lambda: None):
        events = [e async for e in router.process_query_events("q")]

    gen.assert_awaited_once()
    metas = [e for e in events if e["type"] == "meta"]
    assert len([m for m in metas if m["status"] == "ok"]) == 1


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_text_only_query_records_memory_once(mock_create, router):
    mock_create.return_value = MagicMock(choices=[MagicMock(message=_text_message("hello there"))])
    result = await router.process_query("hi", session_id="s1")
    assert result == "hello there"
    history = router.memory.get_history("s1")
    assert [m["role"] for m in history] == ["user", "assistant"]
