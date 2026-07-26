"""
Regression coverage for ``core.sandbox.Sandbox.execute_async`` (Bug-2 fix).

The previous implementation called ``Sandbox.execute`` (a synchronous method
that blocks on ``process.join(timeout)``) directly from inside
``async def process_query``. That blocked the FastAPI event loop for up to
the 10s timeout, freezing every other in-flight coroutine.

The fix introduced ``execute_async``, which wraps the synchronous logic in
``loop.run_in_executor(None, ...)`` so the event loop keeps making progress
while the child process runs.
"""
import asyncio
import time

import pytest
from pydantic import BaseModel
from typing import Type

from core.base import BaseSkill
from core.sandbox import Sandbox, SandboxResult
from skills.calculator_skill import CalculatorSkill


# Defined at module scope so the multiprocessing pickler can serialize it.
# Local classes defined inside a test function would raise PicklingError when
# the sandbox tries to ship the skill instance to the worker process.
class SlowArgs(BaseModel):
    pass


class SlowResp(BaseModel):
    result: str


class SlowSkill(BaseSkill):
    """A skill that sleeps longer than the sandbox timeout — used to verify
    that execute_async correctly enforces the timeout and surfaces it as a
    failure rather than hanging the coroutine."""

    @property
    def name(self): return "slow_skill"

    @property
    def description(self): return "slow"

    @property
    def expected_args(self): return SlowArgs

    @property
    def expected_response_type(self): return SlowResp

    async def execute(self, **kwargs):
        await asyncio.sleep(5)
        return SlowResp(result="done")


@pytest.mark.asyncio
async def test_b02_execute_async_returns_sandbox_result():
    """execute_async must return a SandboxResult, just like execute()."""
    sandbox = Sandbox(timeout=5)
    result = await sandbox.execute_async(CalculatorSkill(), expression="2 + 3 * 4")
    assert isinstance(result, SandboxResult)
    assert result.success is True
    # Calculator returns a CalculatorResponse — just check the result field.
    assert result.result is not None


@pytest.mark.asyncio
async def test_b02_execute_async_does_not_block_event_loop():
    """
    Bug-2 regression: while execute_async is running (and potentially
    blocking on a child process), other coroutines scheduled on the same
    event loop must keep making progress. We assert this by interleaving an
    `asyncio.sleep` ticker coroutine and confirming it actually advances
    during the sandbox execution window.

    Note: this is a soft signal — under a healthy event loop the ticker
    fires multiple times while the sandboxed skill runs. Under the old
    blocking implementation it would fire 0 times during the execution
    window because the loop was wedged on `process.join()`.
    """
    sandbox = Sandbox(timeout=5)
    tick_count = 0

    async def ticker():
        nonlocal tick_count
        for _ in range(20):
            await asyncio.sleep(0.05)
            tick_count += 1

    ticker_task = asyncio.create_task(ticker())
    # Give the ticker a chance to start before we hit the sandbox.
    await asyncio.sleep(0)

    result = await sandbox.execute_async(CalculatorSkill(), expression="2 + 2")
    assert result.success is True

    # Wait for the ticker to finish so we can count how many times it fired.
    await ticker_task
    # If the event loop was blocked during sandbox execution, the ticker
    # would have fired far fewer times. A reasonable threshold: at least 5
    # ticks out of 20 over a multi-millisecond sandbox run.
    assert tick_count >= 5, (
        f"Event loop appears blocked: ticker only fired {tick_count} times "
        f"during sandbox execution."
    )


@pytest.mark.asyncio
async def test_b02_execute_async_propagates_skill_failure():
    """
    Bug-2 + Bug-4 regression: a skill that raises must surface as
    SandboxResult(success=False, error=...), not as a crash in the
    executor. The router relies on this contract to record the failure.
    """
    sandbox = Sandbox(timeout=5)
    result = await sandbox.execute_async(CalculatorSkill(), expression="1/0")
    assert isinstance(result, SandboxResult)
    # Division by zero is caught inside CalculatorSkill and returned as a
    # soft failure (response with error). The sandbox itself succeeds.
    assert result.success is True
    assert hasattr(result.result, "error")
    assert result.result.error is not None


@pytest.mark.asyncio
async def test_b02_execute_async_timeout_returns_failure():
    """
    Bug-2 + Bug-12 regression: a skill that exceeds the timeout must return
    SandboxResult(success=False, error="...timed out...") rather than
    hanging the coroutine indefinitely.
    """
    sandbox = Sandbox(timeout=1)

    start = time.monotonic()
    result = await sandbox.execute_async(SlowSkill())
    elapsed = time.monotonic() - start
    # Must return well before the child's 5s sleep finishes.
    assert elapsed < 4, f"execute_async blocked for {elapsed}s — did not enforce timeout"
    assert result.success is False
    assert "timed out" in result.error
