import json
import os
import logging
import threading
from typing import Awaitable, Callable, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# An async callable that receives the dropped messages and returns a summary string.
Summarizer = Callable[[List[dict]], Awaitable[str]]


class Memory:
    """
    Per-session conversational memory.

    Short-term history is a FIFO of the most recent ``max_history`` rounds
    (2 messages per round). When a conversation overflows, instead of losing
    the dropped turns entirely, Synapse can compress them into a rolling
    summary that is prepended to the context on every subsequent call
    (inspired by LangChain's ``ConversationSummaryBufferMemory`` and the
    hierarchical memory of mem0 / Letta). Summarization is opt-in: pass an
    async ``summarizer`` callable; without one, behavior is identical to the
    plain FIFO truncation.

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

    On-disk format note: the main ``persist_path`` JSON stays a plain
    ``{session_id: [messages]}`` mapping for backward compatibility; summaries
    live in a sidecar file ``<persist_path>.summaries.json``.
    """

    def __init__(self, max_history: int = 10, persist_path: Optional[str] = None,
                 summarizer: Optional[Summarizer] = None):
        self.max_history = max_history
        self.persist_path = persist_path
        self.summarizer = summarizer
        self._history: Dict[str, List[dict]] = defaultdict(list)
        # Rolling summaries per session (compressed older turns).
        self._summaries: Dict[str, str] = {}
        # Dropped messages awaiting summarization. Only populated when a
        # summarizer is configured; otherwise overflow is plain FIFO drop.
        self._dropped: Dict[str, List[dict]] = defaultdict(list)
        # Re-entrant: mutators call _save_locked() while already holding the
        # lock, and _save_locked() must not deadlock on re-entry.
        self._lock = threading.RLock()
        if persist_path and os.path.exists(persist_path):
            self._load()
        self._load_summaries()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            self._history[session_id].append({"role": role, "content": content})
            if len(self._history[session_id]) > self.max_history * 2:
                overflow = self._history[session_id][:-self.max_history * 2]
                self._history[session_id] = self._history[session_id][-self.max_history * 2:]
                if self.summarizer is not None:
                    self._dropped[session_id].extend(overflow)
            self._save_locked()

    async def apply_summary(self, session_id: str) -> Optional[str]:
        """Compress any dropped messages for this session into a rolling
        summary using the configured summarizer. Returns the new summary
        text, or None when there was nothing to summarize / no summarizer.

        Called by the router between queries (it needs an async LLM call,
        which the sync ``add_message`` cannot perform)."""
        summarizer = self.summarizer
        with self._lock:
            dropped = self._dropped.get(session_id) if summarizer is not None else None
            if not summarizer or not dropped:
                return None
            dropped = list(dropped)
        try:
            summary = await summarizer(dropped)
        except Exception as e:
            logger.warning(f"Memory: summarizer failed, keeping FIFO history: {e}")
            return None
        summary = (summary or "").strip()
        if not summary:
            return None
        with self._lock:
            self._summaries[session_id] = summary
            self._dropped[session_id] = []
            self._save_summaries_locked()
        return summary

    def get_history(self, session_id: str) -> List[dict]:
        # Return a defensive copy so callers cannot mutate internal state
        # outside the lock and corrupt concurrent writers.
        with self._lock:
            history = list(self._history.get(session_id, []))
            summary = self._summaries.get(session_id)
            if summary:
                summary_message = {
                    "role": "system",
                    "content": f"Summary of the earlier part of this conversation: {summary}",
                }
                history = [summary_message] + history
            return history

    def get_summary(self, session_id: str) -> Optional[str]:
        with self._lock:
            return self._summaries.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._history:
                del self._history[session_id]
            self._summaries.pop(session_id, None)
            self._dropped.pop(session_id, None)
            self._save_locked()
            self._save_summaries_locked()

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

    @property
    def _summaries_path(self) -> Optional[str]:
        return f"{self.persist_path}.summaries.json" if self.persist_path else None

    def _save_summaries_locked(self) -> None:
        """Caller MUST already hold ``self._lock``."""
        path = self._summaries_path
        if not path:
            return
        try:
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._summaries, f, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception as e:
            logger.error(f"Failed to persist memory summaries: {e}")

    def _load_summaries(self) -> None:
        path = self._summaries_path
        if not path or not os.path.exists(path):
            return
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._summaries = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory summaries: {e}")
