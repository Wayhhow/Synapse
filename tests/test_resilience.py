"""Tests for the retry-with-backoff helper in core.resilience."""
import pytest

from core.resilience import with_retries, _TransientError


class FakeRateLimit(Exception):
    """Mimics openai.RateLimitError (matched by class name)."""


def _patch_transient_names(monkeypatch):
    monkeypatch.setattr(
        "core.resilience._TRANSIENT_NAMES",
        frozenset({"RateLimitError"}),
    )
    FakeRateLimit.__name__ = "RateLimitError"


@pytest.mark.asyncio
async def test_retries_transient_then_succeeds(monkeypatch):
    _patch_transient_names(monkeypatch)
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeRateLimit("slow down")
        return "ok"

    result = await with_retries(flaky, attempts=3, base_delay=0.01)
    assert result == "ok"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_gives_up_after_attempts(monkeypatch):
    _patch_transient_names(monkeypatch)

    async def always_fails():
        raise FakeRateLimit("nope")

    with pytest.raises(FakeRateLimit):
        await with_retries(always_fails, attempts=3, base_delay=0.01)


@pytest.mark.asyncio
async def test_non_transient_error_raises_immediately():
    calls = {"n": 0}

    async def broken():
        calls["n"] += 1
        raise ValueError("logic bug")

    with pytest.raises(ValueError):
        await with_retries(broken, attempts=5, base_delay=0.01)
    assert calls["n"] == 1  # no retry for non-transient errors


@pytest.mark.asyncio
async def test_explicit_retry_on_types():
    class Custom(Exception):
        pass

    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise Custom("custom transient")
        return 42

    result = await with_retries(flaky, attempts=3, base_delay=0.01, retry_on=[Custom])
    assert result == 42


@pytest.mark.asyncio
async def test_marker_transient_error():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise _TransientError("marker")
        return "done"

    assert await with_retries(flaky, attempts=3, base_delay=0.01) == "done"
