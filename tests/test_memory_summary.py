"""
Rolling-summary memory tests: without a summarizer, Memory behaves exactly
like the original FIFO; with one, dropped turns are compressed into a summary
that is prepended to subsequent history.
"""
import json
import os
import pytest

from core.memory import Memory


@pytest.mark.asyncio
async def test_without_summarizer_behavior_unchanged():
    mem = Memory(max_history=2)
    for i in range(10):
        mem.add_message("s", "user", f"u{i}")
    history = mem.get_history("s")
    assert len(history) == 4  # plain FIFO, no summary message
    assert all(m["role"] != "system" for m in history)


@pytest.mark.asyncio
async def test_summary_prepended_to_history():
    async def summarizer(dropped):
        return "User greeted and discussed the weather."

    mem = Memory(max_history=1, summarizer=summarizer)
    # Fill 4 messages: max keeps 2, so the first 2 drop into the pending pool.
    mem.add_message("s", "user", "hello")
    mem.add_message("s", "assistant", "hi")
    mem.add_message("s", "user", "what's the weather")
    mem.add_message("s", "assistant", "sunny")

    assert await mem.apply_summary("s") == "User greeted and discussed the weather."

    history = mem.get_history("s")
    assert history[0]["role"] == "system"
    assert "earlier part" in history[0]["content"]
    assert "weather" in history[0]["content"]
    assert history[-2:][0]["content"] == "what's the weather"
    assert history[-1]["content"] == "sunny"


@pytest.mark.asyncio
async def test_apply_summary_noop_without_dropped():
    async def summarizer(dropped):  # pragma: no cover - must not be called
        raise AssertionError("summarizer should not run")

    mem = Memory(max_history=5, summarizer=summarizer)
    mem.add_message("s", "user", "only message")
    assert await mem.apply_summary("s") is None


@pytest.mark.asyncio
async def test_summarizer_failure_degrades_gracefully():
    async def bad_summarizer(dropped):
        raise RuntimeError("LLM unavailable")

    mem = Memory(max_history=1, summarizer=bad_summarizer)
    mem.add_message("s", "user", "a")
    mem.add_message("s", "assistant", "b")
    mem.add_message("s", "user", "c")

    assert await mem.apply_summary("s") is None
    # History still works, just without a summary message
    history = mem.get_history("s")
    assert all(m["role"] != "system" for m in history)


@pytest.mark.asyncio
async def test_summaries_persist_to_sidecar(tmpdir):
    async def summarizer(dropped):
        return "compressed facts"

    path = os.path.join(str(tmpdir), "mem.json")
    mem1 = Memory(max_history=1, persist_path=path, summarizer=summarizer)
    mem1.add_message("s", "user", "a")
    mem1.add_message("s", "assistant", "b")
    mem1.add_message("s", "user", "c")
    await mem1.apply_summary("s")

    # Sidecar file exists next to the main file
    assert os.path.isfile(path + ".summaries.json")
    with open(path + ".summaries.json", encoding="utf-8") as f:
        assert json.load(f)["s"] == "compressed facts"

    # A fresh instance picks the summary back up
    mem2 = Memory(max_history=1, persist_path=path, summarizer=summarizer)
    history = mem2.get_history("s")
    assert history[0]["role"] == "system"
    assert "compressed facts" in history[0]["content"]


@pytest.mark.asyncio
async def test_clear_removes_summary(tmpdir):
    async def summarizer(dropped):
        return "old stuff"

    mem = Memory(max_history=1, summarizer=summarizer)
    mem.add_message("s", "user", "a")
    mem.add_message("s", "assistant", "b")
    mem.add_message("s", "user", "c")
    await mem.apply_summary("s")
    mem.clear("s")
    assert mem.get_summary("s") is None
    assert mem.get_history("s") == []
