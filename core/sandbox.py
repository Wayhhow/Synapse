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
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def execute(self, skill_instance, **kwargs) -> SandboxResult:
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_worker, args=(skill_instance, kwargs, queue))
        process.start()
        process.join(timeout=self.timeout)

        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            logger.warning(f"Sandbox: Skill execution timed out after {self.timeout}s")
            return SandboxResult(success=False, error=f"Skill execution timed out after {self.timeout}s")

        if not queue.empty():
            status, result = queue.get()
            if status == "success":
                return SandboxResult(success=True, result=result)
            else:
                logger.error(f"Sandbox: Skill execution failed: {result}")
                return SandboxResult(success=False, error=result)

        logger.error("Sandbox: Skill execution produced no result")
        return SandboxResult(success=False, error="Skill execution produced no result")
