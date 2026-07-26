import asyncio
import logging
import multiprocessing
from typing import Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SandboxResult(BaseModel):
    success: bool
    result: Any = None
    error: Optional[str] = None


def _worker(skill_instance, kwargs, queue):
    try:
        import asyncio
        result = asyncio.run(skill_instance.execute(**kwargs))
        queue.put(("success", result))
    except Exception as e:
        queue.put(("error", str(e)))


class Sandbox:
    """
    Process-level sandbox for executing skills.

    Bug-2 fix: ``execute`` is synchronous and would block the FastAPI event
    loop when called from ``async def process_query``. The new
    ``execute_async`` wrapper runs the synchronous logic in a thread executor
    so other coroutines can keep making progress. The original ``execute``
    method is kept for backwards compatibility and for tests that disable
    the sandbox (``router.sandbox = None``).

    Bug-12 fix: when a skill times out, ``terminate`` followed by a 1-second
    ``join`` is not always enough — the child can still be alive. We now
    escalate to ``kill`` (SIGKILL) and join again. The inter-process queue
    is also explicitly closed/joined to release the background feeder thread
    and avoid leaking file descriptors across many runs.
    """

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    async def execute_async(self, skill_instance, **kwargs) -> SandboxResult:
        """
        Bug-2 fix: async entry point. Wraps the synchronous ``_execute_sync``
        in ``run_in_executor`` so the event loop is not blocked while the
        child process runs (and potentially times out).
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._execute_sync, skill_instance, kwargs)

    def execute(self, skill_instance, **kwargs) -> SandboxResult:
        """Synchronous entry point. Kept for backwards compatibility."""
        return self._execute_sync(skill_instance, kwargs)

    def _execute_sync(self, skill_instance, kwargs) -> SandboxResult:
        queue: multiprocessing.Queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_worker, args=(skill_instance, kwargs, queue))
        process.start()
        process.join(timeout=self.timeout)

        timed_out = False
        if process.is_alive():
            timed_out = True
            # Bug-12 fix: terminate gracefully, then escalate to kill if it
            # refuses to die. Otherwise the child becomes a zombie and the
            # Queue's background feeder thread keeps the file descriptors open.
            process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                logger.warning(
                    "Sandbox: process did not terminate after 1s, escalating to SIGKILL"
                )
                process.kill()
                process.join(timeout=1)

        # Always drain the result queue and close it so the feeder thread
        # is shut down. Bug-12 fix: previously the queue was left open on the
        # timeout path, leaking OS-level file descriptors over long runs.
        result: Optional[SandboxResult] = None
        try:
            if not queue.empty():
                status, value = queue.get()
                if status == "success":
                    result = SandboxResult(success=True, result=value)
                else:
                    logger.error(f"Sandbox: Skill execution failed: {value}")
                    result = SandboxResult(success=False, error=value)
        finally:
            try:
                queue.close()
                queue.join_thread()
            except Exception as e:  # pragma: no cover - defensive cleanup
                logger.debug(f"Sandbox: queue cleanup raised {e}")

        if timed_out:
            logger.warning(f"Sandbox: Skill execution timed out after {self.timeout}s")
            return SandboxResult(success=False, error=f"Skill execution timed out after {self.timeout}s")

        if result is not None:
            return result

        logger.error("Sandbox: Skill execution produced no result")
        return SandboxResult(success=False, error="Skill execution produced no result")
