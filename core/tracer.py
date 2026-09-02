"""
Lightweight execution tracing (a local, zero-dependency stand-in for what
LangSmith / Langfuse provide hosted): every user query produces one JSONL
record describing the agent loop — which skills ran, how long each LLM round
took, and how the query resolved. Records land in ``data/traces.jsonl``
(configurable / disable-able via ``SYNAPSE_TRACE`` / ``SYNAPSE_TRACE_PATH``).

The file format is deliberately dumb: one JSON object per line, append-only,
safe to ``tail -f`` or import into any analysis tool.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Trace:
    """In-progress trace for a single query. Cheap to hold; only touches
    disk when :meth:`finish` is called (via the recorder)."""

    def __init__(self, query: str, session_id: Optional[str] = None):
        self.record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "query": query,
            "steps": [],
            "skills_used": [],
            "final_type": None,
            "total_ms": None,
        }
        self._t0 = time.monotonic()

    def add_step(self, step_type: str, name: Optional[str] = None, duration_ms: float = 0.0,
                 success: bool = True, error: Optional[str] = None, detail: Optional[Dict[str, Any]] = None) -> None:
        entry: Dict[str, Any] = {
            "type": step_type,
            "name": name,
            "duration_ms": round(duration_ms, 1),
            "success": success,
        }
        if error:
            entry["error"] = error
        if detail:
            entry["detail"] = detail
        self.record["steps"].append(entry)
        if step_type == "tool" and name and success and name not in self.record["skills_used"]:
            self.record["skills_used"].append(name)

    def finish(self, final_type: str) -> Dict[str, Any]:
        self.record["final_type"] = final_type
        self.record["total_ms"] = round((time.monotonic() - self._t0) * 1000, 1)
        return self.record


class TraceRecorder:
    """Appends finished traces to a JSONL file. Thread-safe; failures to
    write are logged but never raise (tracing must not break the agent)."""

    def __init__(self, path: Optional[str] = "data/traces.jsonl"):
        self.path = path or None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self.path)

    def start(self, query: str, session_id: Optional[str] = None) -> Trace:
        return Trace(query, session_id)

    def write(self, trace: Trace, final_type: str = "done") -> None:
        if not self.enabled:
            return
        try:
            record = trace.finish(final_type)
            dir_path = os.path.dirname(self.path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"TraceRecorder: failed to write trace: {e}")

    def read_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return up to ``limit`` most recent records (newest first)."""
        if not self.enabled or not os.path.isfile(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:  # pragma: no cover - defensive
            logger.error(f"TraceRecorder: failed to read traces: {e}")
            return []
        records: List[Dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
        return records
