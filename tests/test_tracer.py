"""
Tracing (core.tracer) unit tests, plus an integration check that the router
writes one trace record per query.
"""
import json
import os

import pytest

from core.tracer import TraceRecorder
from core.config import SynapseConfig
from core.memory import Memory
from core.skill_registry import SkillRegistry
from router.router import SkillRouter


# ---------------------------------------------------------------------------
# TraceRecorder
# ---------------------------------------------------------------------------

def test_trace_round_trip(tmpdir):
    path = os.path.join(str(tmpdir), "traces.jsonl")
    rec = TraceRecorder(path)
    t1 = rec.start("query one", "s1")
    t1.add_step("llm", "gpt-4o-mini", 100.0)
    t1.add_step("tool", "weather_skill", 20.0)
    rec.write(t1, final_type="text")

    t2 = rec.start("query two", "s2")
    rec.write(t2, final_type="max_steps")

    recent = rec.read_recent(limit=2)
    assert recent[0]["query"] == "query two"
    assert recent[1]["query"] == "query one"
    assert recent[1]["steps"][0]["type"] == "llm"
    assert recent[1]["skills_used"] == ["weather_skill"]


def test_trace_disabled_recorder_is_noop():
    rec = TraceRecorder(None)
    assert rec.enabled is False
    assert rec.read_recent() == []
    t = rec.start("q")
    rec.write(t)  # must not raise


def test_trace_read_recent_skips_corrupt_lines(tmpdir):
    path = os.path.join(str(tmpdir), "traces.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"query": "good"}) + "\n")
        f.write("not-json\n")
        f.write(json.dumps({"query": "good2"}) + "\n")
    rec = TraceRecorder(path)
    records = rec.read_recent(limit=10)
    assert [r["query"] for r in records] == ["good2", "good"]


# ---------------------------------------------------------------------------
# Router integration: one JSONL record per query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_router_writes_trace_for_query(tmpdir):
    from unittest.mock import patch, MagicMock, AsyncMock

    message = MagicMock()
    message.tool_calls = None
    message.content = "just text"
    mock_create = AsyncMock(return_value=MagicMock(choices=[MagicMock(message=message)]))

    path = os.path.join(str(tmpdir), "traces.jsonl")
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(trace_enabled=True, trace_path=path)
    router = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    router.sandbox = None
    router.memory = Memory(max_history=10)

    with patch("openai.resources.chat.completions.AsyncCompletions.create", mock_create):
        result = await router.process_query("hello", session_id="s")

    assert result == "just text"
    records = router.tracer.read_recent(limit=5)
    assert len(records) == 1
    rec = records[0]
    assert rec["query"] == "hello"
    assert rec["final_type"] == "text"
    assert any(step["type"] == "llm" for step in rec["steps"])
