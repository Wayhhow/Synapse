import json
import os
import logging
import threading
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SkillRegistry:
    """
    Persistent registry of skill execution stats.

    Bug-5 fix: ``register()`` previously was a no-op for skills that had
    already been registered, which meant the description captured on first
    registration (often empty, or a placeholder like
    ``"Auto-generated skill for: ..."``) could never be refined. Now if a
    later ``register()`` call supplies a non-empty description, the stored
    description is updated in place.

    Bug-19 fix: the ``health_score`` field used to be persisted at
    registration time as ``100.0`` and never updated again. Readers
    (``generate_improvement_report``, ``/stats``) compute the live score via
    ``SkillEvaluator.evaluate()`` and never read this field, so keeping it
    around was misleading — operators would inspect the JSON file and
    believe every skill was perfectly healthy. The field is no longer
    written. Existing on-disk JSON files are migrated on load: any stale
    ``health_score`` key is dropped silently.

    Bug-9 fix: every ``register`` / ``record_execution`` / ``clear`` call
    previously did a full ``load → modify → write`` cycle with no
    synchronization. Two concurrent router requests writing to the same
    registry (the registry is shared by the router, the SkillCreator, and
    the SkillEvaluator) could lose updates. We now guard all public
    mutators/readers with an ``RLock`` so the load-modify-write cycle is
    atomic with respect to other threads. ``RLock`` (not ``Lock``) is used
    because mutators call ``_save_locked()`` while already holding the lock.

    Bug-17 fix: ``persist_path`` may be a bare filename with no directory
    component (e.g. tests pass ``"registry.json"``). ``os.path.dirname``
    returns "" in that case and ``os.makedirs("")`` raises
    FileNotFoundError. We only attempt ``makedirs`` when there is actually
    a directory component.
    """

    def __init__(self, persist_path: str = "data/skill_registry.json"):
        self.persist_path = persist_path
        self._stats: Dict[str, Dict[str, Any]] = {}
        # Re-entrant because mutators call _save_locked() while already
        # holding the lock, and _save_locked() must not deadlock on re-entry.
        self._lock = threading.RLock()
        self._load()

    def register(self, skill_name: str, description: str = "") -> None:
        with self._lock:
            existing = self._stats.get(skill_name)
            if existing is None:
                self._stats[skill_name] = {
                    "description": description,
                    "created_at": datetime.now().isoformat(),
                    "total_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_error": None,
                    "avg_execution_time": 0.0,
                }
                self._save_locked()
                return
            # Bug-5 fix: update description if a more informative one is supplied.
            # This matters because SkillRouter re-registers all discovered skills
            # on startup with their real description, but auto-generated skills
            # had previously been registered by SkillCreator with a placeholder
            # description ("Auto-generated skill for: <intent>"). Without this
            # update path, dim4_specificity would keep scoring against the
            # placeholder forever.
            if description and existing.get("description", "") != description:
                existing["description"] = description
                self._save_locked()

    def record_execution(self, skill_name: str, success: bool, execution_time: float = 0.0, error: Optional[str] = None) -> None:
        with self._lock:
            if skill_name not in self._stats:
                # Inline the registration to avoid recursive lock acquisition
                # via self.register(); RLock would handle it, but the inline
                # path is faster and avoids an extra _save_locked() call.
                self._stats[skill_name] = {
                    "description": "",
                    "created_at": datetime.now().isoformat(),
                    "total_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "last_error": None,
                    "avg_execution_time": 0.0,
                }
            stats = self._stats[skill_name]
            stats["total_count"] += 1
            if success:
                stats["success_count"] += 1
                # Bug-7 (related): clear stale last_error on a fresh success so
                # the registry no longer carries forward an old failure forever.
                # The evaluator no longer reads last_error, but the field is
                # still surfaced via /stats for operators; keeping it accurate
                # matters.
                stats["last_error"] = None
            else:
                stats["failure_count"] += 1
                stats["last_error"] = error
            if stats["total_count"] > 0:
                old_avg = stats["avg_execution_time"]
                n = stats["total_count"]
                stats["avg_execution_time"] = old_avg + (execution_time - old_avg) / n
            self._save_locked()

    def get_stats(self, skill_name: str) -> Optional[Dict[str, Any]]:
        # Defensive copy so callers cannot mutate internal state outside the
        # lock and corrupt concurrent writers.
        with self._lock:
            stats = self._stats.get(skill_name)
            return dict(stats) if stats is not None else None

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        # Defensive deep copy: returns a fresh dict-of-dicts so callers can
        # iterate / mutate without holding the lock.
        with self._lock:
            return {name: dict(stats) for name, stats in self._stats.items()}

    def _save_locked(self) -> None:
        """Caller MUST already hold ``self._lock``."""
        try:
            dir_path = os.path.dirname(self.persist_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            # Atomic write via temp + rename: guards against partial writes
            # if the process is killed mid-write.
            tmp_path = self.persist_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.persist_path)
        except Exception as e:
            logger.error(f"Failed to persist skill registry: {e}")

    def _load(self) -> None:
        with self._lock:
            if not os.path.exists(self.persist_path):
                return
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load skill registry: {e}")
                return
            # Bug-19 migration: silently drop the stale `health_score` key from
            # any pre-existing entry. We never read it; keeping it just confused
            # operators inspecting the JSON file. Future writes will not re-add it.
            for stats in loaded.values():
                if isinstance(stats, dict):
                    stats.pop("health_score", None)
            self._stats = loaded
