"""Tests for the zero-cost demo mode (core.mock_llm.MockLLM).

The demo mode exists so anyone can try the full agent loop with no API key
and zero token spend. These tests pin down its contract: keyword routing over
the live skill catalog, honest Meta-Evolution stubbing, memory recording, and
the critical guarantee that a *production* router (demo flag off) never
patches the OpenAI SDK.

All tests are hermetic: no network, no real LLM, no filesystem writes outside
``tmpdir``.
"""

import json
import os

import pytest
from unittest.mock import AsyncMock

from core.config import SynapseConfig
from core.memory import Memory
from core.mock_llm import MockLLM
from core.skill_registry import SkillRegistry
from router.router import SkillRouter


@pytest.fixture
def demo_router(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    config = SynapseConfig(max_steps=5, trace_enabled=False, demo_mock_llm=True)
    r = SkillRouter(api_key=None, registry=registry, config=config)
    r.sandbox = None  # demo exercises routing, not the process sandbox
    r.memory = Memory(max_history=10)
    return r


def test_mock_llm_routes_by_keyword_over_real_catalog(tmp_path):
    """Routing runs over the *real* discovered skill catalog."""
    router = SkillRouter(
        api_key="test-key",
        registry=SkillRegistry(persist_path=str(tmp_path / "registry.json")),
        config=SynapseConfig(trace_enabled=False),
    )
    mock = MockLLM(skills=router.skills)
    assert mock._match_skill("北京天气怎么样？") == "weather_skill"
    assert mock._match_skill("calculate 2+2") == "calculator_skill"
    assert mock._match_skill("翻译 hello world") == "translation_skill"
    assert mock._match_skill("quantum entanglement stock options") is None
    assert mock._match_skill("帮我预测明年的量子计算股价") is None  # no skill → Meta-Evolution


def test_build_args_uses_skill_schema(demo_router):
    mock = demo_router._mock_llm
    assert mock is not None
    args = json.loads(mock._build_args("calculator_skill", "算一下"))
    assert args == {"expression": "(2 + 3) * 4 ** 2"}
    args = json.loads(mock._build_args("weather_skill", "北京天气"))
    assert args == {"location": "Beijing"}


@pytest.mark.asyncio
async def test_mock_llm_after_tool_feeds_result_back(tmp_path):
    router = SkillRouter(
        api_key="test-key",
        registry=SkillRegistry(persist_path=str(tmp_path / "registry.json")),
        config=SynapseConfig(trace_enabled=False),
    )
    mock = MockLLM(skills=router.skills)
    first = await mock.create(model="m", messages=[{"role": "user", "content": "北京天气怎么样？"}])
    assert first.choices[0].message.tool_calls[0].function.name == "weather_skill"


@pytest.mark.asyncio
async def test_demo_mode_runs_full_agent_loop_without_api_key(demo_router):
    """The headline promise: a complete query works with no OPENAI_API_KEY."""
    assert demo_router.api_key == "demo"  # placeholder so the SDK accepts it
    # Patch the *instance* execute (not the class) so the mock can't leak
    # into other tests' routers, and so no real network call happens.
    from skills.calculator_skill import CalculatorResponse
    calc = demo_router.skills["calculator_skill"]
    calc.execute = AsyncMock(
        return_value=CalculatorResponse(expression="(2 + 3) * 4 ** 2", result=80.0))
    result = await demo_router.process_query("帮我计算一下", session_id="demo-s1")
    assert isinstance(result, str)
    assert "Mock LLM" in result
    # The real tool result is echoed back in the mock's final answer.
    assert "80" in result
    calc.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_demo_mode_records_memory(demo_router):
    await demo_router.process_query("hi", session_id="demo-s2")
    history = demo_router.memory.get_history("demo-s2")
    assert [m["role"] for m in history] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_demo_mode_meta_evolution_is_honestly_stubbed(demo_router):
    """Unmatched queries trigger request_new_skill; generation is stubbed and
    the failure event + honest tool message feed back into the loop."""
    events = [e async for e in demo_router.process_query_events("帮我预测明年的量子计算股价")]
    metas = [e for e in events if e["type"] == "meta"]
    assert any(m["status"] == "generating" for m in metas)
    assert any(m["status"] == "failed" for m in metas)
    final = events[-1]
    assert final["type"] == "final"
    assert "Meta-Evolution" in final["text"]


def test_production_router_does_not_patch_sdk(tmpdir):
    """Safety invariant: without the demo flag the OpenAI SDK is untouched."""
    from openai.resources.chat.completions import AsyncCompletions
    original = AsyncCompletions.create
    try:
        registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
        config = SynapseConfig(max_steps=5, trace_enabled=False, demo_mock_llm=False)
        r = SkillRouter(api_key="test-key", registry=registry, config=config)
        assert r._mock_llm is None
        assert AsyncCompletions.create is original
    finally:
        AsyncCompletions.create = original


def test_mock_llm_patch_replaces_create():
    from openai.resources.chat.completions import AsyncCompletions
    original = AsyncCompletions.create
    mock = MockLLM()
    try:
        mock.patch()
        assert AsyncCompletions.create == mock.create
    finally:
        AsyncCompletions.create = original

