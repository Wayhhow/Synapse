import logging
import multiprocessing
from typing import Any, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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

    def execute(self, skill_instance, **kwargs) -> Any:
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_worker, args=(skill_instance, kwargs, queue))
        process.start()
        process.join(timeout=self.timeout)

        if process.is_alive():
            process.terminate()
            process.join(timeout=1)
            logger.warning(f"Sandbox: Skill execution timed out after {self.timeout}s")
            return BaseModel()

        if not queue.empty():
            status, result = queue.get()
            if status == "success":
                return result
            else:
                logger.error(f"Sandbox: Skill execution failed: {result}")
                return BaseModel()

        logger.error("Sandbox: Skill execution produced no result")
        return BaseModel()
