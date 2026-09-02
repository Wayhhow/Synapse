"""
Tiny retry-with-backoff helper (a focused subset of what ``tenacity`` does,
without adding a dependency).

Every agent framework in production (LangChain, OpenManus, AutoGPT) wraps LLM
calls in exponential-backoff retries because rate limits and transient 5xx
errors are the norm, not the exception. The OpenAI SDK already retries at the
transport level; this module adds a second, coarser layer for
``RateLimitError`` / ``APIStatusError`` / transient network failures.
"""

import asyncio
import logging
import random
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Error types we consider transient. Matched by class name so the module does
# not need to import openai (keeps core importable without the SDK installed).
_TRANSIENT_NAMES = frozenset({
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
})


class _TransientError(Exception):
    """Marker used by tests to simulate a transient provider error."""


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, _TransientError):
        return True
    return type(exc).__name__ in _TRANSIENT_NAMES


async def with_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 2,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: Optional[Iterable[type]] = None,
) -> T:
    """Await ``fn()`` up to ``attempts`` times with exponential backoff.

    Retries only when the raised exception is transient (rate limit /
    connection / timeout / 5xx — matched by class name so openai types are
    recognized without importing them) or is an instance of one of the
    explicit ``retry_on`` types. The last exception is re-raised when all
    attempts fail. Jitter avoids thundering-herd retries across concurrent
    requests.
    """
    extra = tuple(retry_on) if retry_on else ()
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001 - deliberate broad catch
            if attempt >= attempts or not (_is_transient(exc) or isinstance(exc, extra)):
                raise
            last_exc = exc
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay *= 0.5 + random.random()  # full jitter in [0.5x, 1.5x]
            logger.warning(
                "Transient error (%s: %s); retrying in %.2fs (attempt %d/%d)",
                type(exc).__name__, exc, delay, attempt, attempts,
            )
            await asyncio.sleep(delay)
    # Unreachable: the loop either returns or raises.
    raise last_exc  # pragma: no cover
