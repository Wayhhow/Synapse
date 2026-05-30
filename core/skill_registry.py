import json
import os
import logging
from typing import Dict, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SkillRegistry:
    def __init__(self, persist_path: str = "data/skill_registry.json"):
        self.persist_path = persist_path
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._load()

    def register(self, skill_name: str, description: str = "") -> None:
        if skill_name not in self._stats:
            self._stats[skill_name] = {
                "description": description,
                "created_at": datetime.now().isoformat(),
                "total_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "last_error": None,
                "avg_execution_time": 0.0,
                "health_score": 100.0,
            }
            self._save()

    def record_execution(self, skill_name: str, success: bool, execution_time: float = 0.0, error: Optional[str] = None) -> None:
        if skill_name not in self._stats:
            self.register(skill_name)
        stats = self._stats[skill_name]
        stats["total_count"] += 1
        if success:
            stats["success_count"] += 1
        else:
            stats["failure_count"] += 1
            stats["last_error"] = error
        if stats["total_count"] > 0:
            old_avg = stats["avg_execution_time"]
            n = stats["total_count"]
            stats["avg_execution_time"] = old_avg + (execution_time - old_avg) / n
        self._save()

    def get_stats(self, skill_name: str) -> Optional[Dict[str, Any]]:
        return self._stats.get(skill_name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._stats)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist skill registry: {e}")

    def _load(self) -> None:
        if os.path.exists(self.persist_path):
            try:
                with open(self.persist_path, "r", encoding="utf-8") as f:
                    self._stats = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load skill registry: {e}")
