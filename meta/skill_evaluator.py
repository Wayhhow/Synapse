import os
import ast
import logging
from typing import Dict, List, Optional
from core.skill_registry import SkillRegistry

logger = logging.getLogger(__name__)

_REQUIRED_MEMBERS = (
    "name",
    "description",
    "expected_args",
    "expected_response_type",
    "execute",
)

_ANTIPATTERN_PATTERNS = (
    "eval(",
    "exec(",
    "os.system",
    "subprocess",
    "__import__",
    "compile(",
    "globals()",
    "locals()",
)


def _is_baseskill_subclass(class_node: ast.ClassDef) -> bool:
    """Return True if the class node has BaseSkill in its direct bases."""
    for base in class_node.bases:
        if isinstance(base, ast.Name) and base.id == "BaseSkill":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "BaseSkill":
            return True
    return False


def _extract_name_property_value(class_node: ast.ClassDef) -> Optional[str]:
    """Best-effort extraction of the string returned by the `name` @property."""
    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if item.name != "name":
            continue
        is_property = any(
            (isinstance(d, ast.Name) and d.id == "property")
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in item.decorator_list
        )
        if not is_property:
            continue
        for stmt in item.body:
            if (
                isinstance(stmt, ast.Return)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                return stmt.value.value
    return None


class SkillEvaluator:
    def __init__(self, registry: Optional[SkillRegistry] = None, skills_dir: str = "skills"):
        self.registry = registry if registry is not None else SkillRegistry()
        self.skills_dir = skills_dir

    def _find_skill_file(self, skill_name: str) -> Optional[str]:
        direct = os.path.join(self.skills_dir, f"{skill_name}.py")
        if os.path.isfile(direct):
            return direct

        if not os.path.isdir(self.skills_dir):
            return None

        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            filepath = os.path.join(self.skills_dir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    code = f.read()
                tree = ast.parse(code)
            except (OSError, SyntaxError) as e:
                logger.warning(f"SkillEvaluator: failed to parse {filepath} while locating skill: {e}")
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if not _is_baseskill_subclass(node):
                    continue
                if _extract_name_property_value(node) == skill_name:
                    return filepath
        return None

    def _check_structure_from_code(self, code: str) -> float:
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning(f"SkillEvaluator: failed to parse code for structure check: {e}")
            return 0.0

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not _is_baseskill_subclass(node):
                continue
            found = set()
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in _REQUIRED_MEMBERS:
                    found.add(item.name)
            return 4.0 * len(found)
        return 0.0

    def _check_antipattern_from_code(self, code: str) -> float:
        hits = sum(1 for pattern in _ANTIPATTERN_PATTERNS if pattern in code)
        return max(0.0, 15.0 - 5.0 * hits)

    def evaluate_code_quality(self, code: str) -> float:
        return self._check_structure_from_code(code) + self._check_antipattern_from_code(code)

    def evaluate(self, skill_name: str) -> float:
        stats = self.registry.get_stats(skill_name)
        if not stats:
            return 0.0

        skill_file = self._find_skill_file(skill_name)
        code: Optional[str] = None
        if skill_file is None:
            logger.warning(f"SkillEvaluator: skill file not found for '{skill_name}'")
        else:
            try:
                with open(skill_file, "r", encoding="utf-8") as f:
                    code = f.read()
            except OSError as e:
                logger.warning(f"SkillEvaluator: failed to read skill file for '{skill_name}': {e}")
                code = None

        if code is None:
            dim1_structure = 0.0
            dim5_antipattern = 0.0
        else:
            dim1_structure = self._check_structure_from_code(code)
            dim5_antipattern = self._check_antipattern_from_code(code)

        dim2_success_rate = 30.0 * (stats["success_count"] / stats["total_count"]) if stats["total_count"] > 0 else 15.0
        dim3_error_handling = 20.0 if stats.get("last_error") is None else 10.0
        dim4_specificity = 15.0 if stats.get("description") and len(stats["description"]) > 10 else 5.0

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
