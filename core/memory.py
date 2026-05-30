import json
import os
import logging
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

class Memory:
    def __init__(self, max_history: int = 10, persist_path: Optional[str] = None):
        self.max_history = max_history
        self.persist_path = persist_path
        self._history: Dict[str, List[dict]] = defaultdict(list)
        if persist_path and os.path.exists(persist_path):
            self._load()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        self._history[session_id].append({"role": role, "content": content})
        if len(self._history[session_id]) > self.max_history * 2:
            self._history[session_id] = self._history[session_id][-self.max_history * 2:]
        self._save()

    def get_history(self, session_id: str) -> List[dict]:
        return self._history.get(session_id, [])

    def clear(self, session_id: str) -> None:
        if session_id in self._history:
            del self._history[session_id]
        self._save()

    def _save(self) -> None:
        if self.persist_path:
            try:
                os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
                with open(self.persist_path, "w", encoding="utf-8") as f:
                    json.dump(dict(self._history), f, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to persist memory: {e}")

    def _load(self) -> None:
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._history = defaultdict(list, data)
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
