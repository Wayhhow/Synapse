import json
import os
import logging
import threading
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class Memory:
    """
    Per-session conversational memory.

    Bug-9 fix: previously every ``add_message`` / ``clear`` call did a full
    ``load → modify → write`` cycle WITHOUT any synchronization. Two concurrent
    HTTP requests (e.g. two browser tabs sharing a session_id, or a retry
    racing with the original call) could both load the same on-disk state,
    both append their own message, and then both write — the second write
    would silently clobber the first, dropping messages on the floor. We now
    guard every public mutator/reader with an ``RLock`` so the load-modify-
    write cycle is atomic with respect to other threads. ``RLock`` is used
    instead of ``Lock`` because internal helpers (``_save_locked``) may be
    entered while the lock is already held by the calling mutator.

    Bug-17 fix: ``persist_path`` may be a bare filename with no directory
    component (e.g. tests pass ``"memory.json"``). ``os.path.dirname`` returns
    "" in that case and ``os.makedirs("")`` raises FileNotFoundError. We
    only attempt ``makedirs`` when there is actually a directory component.
    """

    def __init__(self, max_history: int = 10, persist_path: Optional[str] = None):
        self.max_history = max_history
        self.persist_path = persist_path
        self._history: Dict[str, List[dict]] = defaultdict(list)
        # Re-entrant: mutators call _save_locked() while already holding the
        # lock, and _save_locked() must not deadlock on re-entry.
        self._lock = threading.RLock()
        if persist_path and os.path.exists(persist_path):
            self._load()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._history[session_id].append({"role": role, "content": content})
            if len(self._history[session_id]) > self.max_history * 2:
                self._history[session_id] = self._history[session_id][-self.max_history * 2:]
            self._save_locked()

    def get_history(self, session_id: str) -> List[dict]:
        # Return a defensive copy so callers cannot mutate internal state
        # outside the lock and corrupt concurrent writers.
        with self._lock:
            return list(self._history.get(session_id, []))

    def clear(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._history:
                del self._history[session_id]
            self._save_locked()

    def _save_locked(self) -> None:
        """Caller MUST already hold ``self._lock``."""
        if not self.persist_path:
            return
        try:
            dir_path = os.path.dirname(self.persist_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            # Write to a temp file in the same directory and then atomically
            # rename. This guards against partial writes / corruption if the
            # process is killed mid-write (a real concern under concurrent
            # load + signals).
            tmp_path = self.persist_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(dict(self._history), f, ensure_ascii=False)
            os.replace(tmp_path, self.persist_path)
        except Exception as e:
            logger.error(f"Failed to persist memory: {e}")

    def _load(self) -> None:
        with self._lock:
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._history = defaultdict(list, data)
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")
