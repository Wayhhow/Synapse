import logging
from typing import Dict, List
from core.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

class SkillEvaluator:
    def __init__(self, registry: SkillRegistry):
        self.registry = registry

    def evaluate(self, skill_name: str) -> float:
        stats = self.registry.get_stats(skill_name)
        if not stats:
            return 0.0

        dim1_structure = 20.0
        dim2_success_rate = 30.0 * (stats["success_count"] / stats["total_count"]) if stats["total_count"] > 0 else 15.0
        dim3_error_handling = 20.0 if stats.get("last_error") is None else 10.0
        dim4_specificity = 15.0 if stats.get("description") and len(stats["description"]) > 10 else 5.0
        dim5_antipattern = 15.0

        total = dim1_structure + dim2_success_rate + dim3_error_handling + dim4_specificity + dim5_antipattern
        return round(total, 1)

    def find_low_quality_skills(self, threshold: float = 50.0) -> List[str]:
        low_quality = []
        for skill_name in self.registry.get_all_stats():
            score = self.evaluate(skill_name)
            if score < threshold:
                low_quality.append(skill_name)
        return low_quality

    def generate_improvement_report(self) -> Dict[str, Dict]:
        report = {}
        for skill_name in self.registry.get_all_stats():
            score = self.evaluate(skill_name)
            stats = self.registry.get_stats(skill_name)
            report[skill_name] = {
                "health_score": score,
                "status": "needs_improvement" if score < 50 else "healthy",
                "success_rate": stats["success_count"] / stats["total_count"] if stats["total_count"] > 0 else 0,
                "total_executions": stats["total_count"],
            }
        return report
