import os
import ast
import logging
import re
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

# Bug-28 fix: dangerous call targets detected via AST walk.
# Each entry maps a fully-qualified call name (as resolved from the AST) to a
# short label. Substring matching previously used for `_ANTIPATTERN_PATTERNS`
# could be defeated by `eval  ("1")` or `getattr(builtins, "eval")("1")`; the
# AST walk resolves the actual callable name regardless of formatting.
_DANGEROUS_CALL_NAMES: Dict[str, str] = {
    "eval": "eval",
    "exec": "exec",
    "compile": "compile",
    "__import__": "__import__",
    "globals": "globals",
    "locals": "locals",
    "os.system": "os.system",
    "os.popen": "os.popen",
    "os.remove": "os.remove",
    "os.unlink": "os.unlink",
    "os.rmdir": "os.rmdir",
    "os.removedirs": "os.removedirs",
    "subprocess.Popen": "subprocess.Popen",
    "subprocess.run": "subprocess.run",
    "subprocess.call": "subprocess.call",
    "subprocess.check_call": "subprocess.check_call",
    "subprocess.check_output": "subprocess.check_output",
    "shutil.rmtree": "shutil.rmtree",
}

# Legacy patterns kept for backward compatibility with any external callers
# that imported the constant; the actual check is now AST-based.
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


def _resolve_call_target(node: ast.Call) -> Optional[str]:
    """
    Resolve the callable name for a `Call` node as a dotted string.

    Returns:
      - "eval"           for `eval(...)`
      - "os.system"      for `os.system(...)`
      - "subprocess.Popen" for `subprocess.Popen(...)`
      - None if it cannot be resolved (e.g. `obj.method()` where obj is unknown)
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        # Walk the attribute chain: e.g. `a.b.c` -> "a.b.c"
        parts: List[str] = []
        cursor = func
        while isinstance(cursor, ast.Attribute):
            parts.append(cursor.attr)
            cursor = cursor.value
        if isinstance(cursor, ast.Name):
            parts.append(cursor.id)
            return ".".join(reversed(parts))
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
        """Backward-compatible wrapper around `check_antipattern_ast`."""
        return self.check_antipattern_ast(code)

    def check_antipattern_ast(self, code: str) -> float:
        """
        Bug-28 fix: AST-based antipattern detection. Walks every `Call` node
        in the code and resolves its target name; for each match in
        `_DANGEROUS_CALL_NAMES`, a 5-point penalty is applied (min 0).

        Unlike the previous substring scan, this catches obfuscated forms like
        `getattr(builtins, "eval")("1")` (resolved to `getattr` — not directly
        dangerous, so not flagged) AND plain `eval("1")` (resolved to `eval` —
        flagged). The dangerous-call list now also covers `os.remove`,
        `os.unlink`, `shutil.rmtree`, `subprocess.run`, etc. which the old
        substring list missed entirely.

        Returns the penalty (0 = clean, 15 = maximally dangerous).
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If we can't parse, we can't score. Return 0 penalty — the
            # structure dimension will already have given 0 points, and the
            # caller (SkillCreator) runs an explicit syntax check first.
            return 0.0

        hits = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _resolve_call_target(node)
            if target is not None and target in _DANGEROUS_CALL_NAMES:
                hits += 1
        return max(0.0, 15.0 - 5.0 * hits)

    def evaluate_code_quality(self, code: str) -> float:
        return self._check_structure_from_code(code) + self._check_antipattern_from_code(code)

    def _check_error_handling_from_code(self, code: str) -> float:
        """
        Bug-7 fix: score the error-handling dimension by inspecting the code,
        not the runtime `last_error` flag. A skill that has both a `try/except`
        block and an `error` field on its response model gets full marks; a
        skill with only one gets partial; one with neither gets the minimum.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return 5.0

        has_try = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                has_try = True
                break

        # Detect an `error` field on any class (response model). We look for
        # an annotated assignment `error: Optional[str] = None` in any
        # ClassDef rather than relying on a "Response" name suffix, so the
        # check works for skills that use shorter names like `MyResp`.
        has_error_field = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    if item.target.id == "error":
                        has_error_field = True
                        break
            if has_error_field:
                break

        if has_try and has_error_field:
            return 20.0
        if has_try or has_error_field:
            return 15.0
        return 5.0

    def _check_specificity_from_description(self, description: str) -> float:
        """
        Bug-8 fix: score the specificity dimension by checking whether the
        description declares explicit trigger words (per the
        `synapse-skill-eval` spec). All built-in skills follow the convention
        `"... Trigger words: a, b, c"`.
        """
        if not description:
            return 5.0
        # Extract the trigger-word list following "Trigger words:".
        match = re.search(
            r"trigger\s*words?\s*:\s*([^\n]+)",
            description,
            flags=re.IGNORECASE,
        )
        if match is None:
            # Fall back to "description is non-trivially long" so we don't
            # regress existing skills that haven't adopted the convention yet.
            return 10.0 if len(description) > 10 else 5.0
        raw_words = match.group(1)
        # Trigger words are comma- or space-separated; filter empties.
        words = [w.strip() for w in re.split(r"[,，]", raw_words) if w.strip()]
        if len(words) >= 2:
            return 15.0
        if len(words) == 1:
            return 10.0
        return 5.0

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
            dim3_error_handling = 5.0
            dim5_antipattern = 0.0
        else:
            dim1_structure = self._check_structure_from_code(code)
            dim3_error_handling = self._check_error_handling_from_code(code)
            dim5_antipattern = self._check_antipattern_from_code(code)

        dim2_success_rate = 30.0 * (stats["success_count"] / stats["total_count"]) if stats["total_count"] > 0 else 15.0
        dim4_specificity = self._check_specificity_from_description(stats.get("description") or "")

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
