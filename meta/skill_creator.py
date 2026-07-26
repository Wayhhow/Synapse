import os
import ast
import json
import logging
import importlib.util
import inspect
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI
from core.skill_registry import SkillRegistry
from core.base import BaseSkill
from meta.skill_evaluator import SkillEvaluator

logger = logging.getLogger(__name__)

class GeneratedSkill(BaseModel):
    filename: str = Field(..., description="The name of the python file, e.g., 'crypto_price_skill.py'")
    class_name: str = Field(..., description="The name of the class inheriting from BaseSkill, e.g., 'CryptoPriceSkill'")
    code: str = Field(..., description="The complete python code for the skill")

class SkillCreator:
    """
    SkillCreator is the Meta-Evolution Module responsible for writing and saving new skills using an LLM.
    """

    def __init__(
        self,
        skills_dir: str = "skills",
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        registry: Optional[SkillRegistry] = None,
    ):
        load_dotenv()
        self.skills_dir = skills_dir
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        # Lazy: only construct the OpenAI client when generate_skill() is
        # actually called. This lets SkillRouter boot for introspection
        # (e.g. `python cli.py --skills`, /health endpoint) without an
        # OPENAI_API_KEY set in the environment.
        self._client: Optional[AsyncOpenAI] = None
        self.registry = registry if registry is not None else SkillRegistry()
        self.evaluator = SkillEvaluator(registry=self.registry, skills_dir=self.skills_dir)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def generate_skill(self, intent: str, requirements: str = "") -> bool:
        """
        Uses an LLM to generate a new Python skill and saves it to the skills directory.
        Returns True if successful, False otherwise.

        Security ordering (Bug-1 fix): top-level safety check + antipattern AST
        evaluation happen BEFORE the module is loaded via `exec_module`, so that
        a malicious `import os; os.system(...)` at module top level is rejected
        instead of executed in the main process.
        """
        system_prompt = (
            "You are a master Python software engineer working on the Synapse AI agent architecture. "
            "Your task is to create a new skill to satisfy the user's intent. "
            "The new skill MUST STRICTLY follow these rules:\n"
            "1. It must be a complete Python file.\n"
            "2. It must define Pydantic models for both arguments and response (e.g., `MyArgs`, `MyResponse`).\n"
            "3. It must define a class that inherits from `core.base.BaseSkill`.\n"
            "4. The class must implement `name`, `description`, `expected_args`, and `expected_response_type` as @property.\n"
            "5. The class must implement `async def execute(self, **kwargs) -> BaseModel`.\n"
            "6. You must provide a JSON response containing 'filename', 'class_name', and 'code' conforming to the GeneratedSkill schema.\n"
            "Do not return markdown, only the raw JSON string matching the GeneratedSkill schema."
        )

        user_prompt = f"Intent: {intent}\nRequirements: {requirements}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"}
            )

            content = response.choices[0].message.content

            # Parse the JSON and validate it against the GeneratedSkill Pydantic model
            skill_data = json.loads(content)
            generated_skill = GeneratedSkill(**skill_data)

            # 1. Basic syntax check
            try:
                ast.parse(generated_skill.code)
            except SyntaxError as e:
                logger.error(f"SkillCreator: Generated code contains syntax errors: {e}")
                return False

            # 2. Bug-1 fix: top-level safety check BEFORE any module load / file write.
            #    Rejects top-level function calls (e.g. `os.system(...)`, `eval(...)`)
            #    that would execute during `exec_module` in the main process.
            rejection = self._check_top_level_safety(generated_skill.code)
            if rejection is not None:
                logger.error(f"SkillCreator: rejected unsafe generated code: {rejection}")
                return False

            # 3. Bug-28 fix: AST-based antipattern check on the whole code body
            #    (catches `getattr(builtins, "eval")("1")` style obfuscation that
            #    substring matching misses). The penalty returned by
            #    `check_antipattern_ast` is `15 - 5*hits` clamped to 0:
            #      0 hits → 15 (clean)   1 hit → 10   2 hits → 5   3+ hits → 0
            #    We reject only when 3+ dangerous calls are detected (penalty
            #    reaches 0). 1-2 hits are left to the ratchet mechanism, which
            #    will roll back the new file when its total score is lower than
            #    the existing one. This layered design keeps the
            #    `test_generate_skill_ratchet_rollback_on_lower_quality` test
            #    meaningful (it relies on a single `eval` going through the
            #    antipattern gate so the ratchet can reject it).
            antipattern_penalty = self.evaluator.check_antipattern_ast(generated_skill.code)
            if antipattern_penalty <= 0.0:
                logger.error(
                    "SkillCreator: rejected generated code - 3 or more "
                    "dangerous calls detected by AST scan."
                )
                return False

            # 4. Bug-10 fix: avoid generating a duplicate skill. If an existing
            #    skill already covers this intent (high keyword overlap), skip.
            similar = self._find_similar_skill(intent)
            if similar is not None:
                logger.warning(
                    f"SkillCreator: similar skill '{similar}' already exists for intent "
                    f"'{intent}'; skipping generation to avoid duplicates."
                )
                return False

            # 5. Filename safety
            if not generated_skill.filename.endswith(".py"):
                generated_skill.filename += ".py"
            safe_filename = os.path.basename(generated_skill.filename)
            if "/" in safe_filename or "\\" in safe_filename:
                logger.error(f"SkillCreator: Rejected unsafe filename: {generated_skill.filename}")
                return False

            filepath = os.path.join(self.skills_dir, safe_filename)

            # 6. Ratchet: capture old content + compute scores BEFORE writing.
            #    Bug-1 fix: scores computed on code strings (not loaded modules),
            #    so we can decide before any execution happens.
            file_existed = os.path.exists(filepath)
            old_code = ""
            if file_existed:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        old_code = f.read()
                except OSError as e:
                    logger.warning(f"SkillCreator: failed to read previous skill file {filepath}: {e}")
                    old_code = ""

            new_score = self.evaluator.evaluate_code_quality(generated_skill.code)
            old_score = self.evaluator.evaluate_code_quality(old_code) if old_code else 0.0
            if new_score < old_score:
                logger.warning(
                    f"SkillCreator: Ratchet check failed - new score ({new_score}) < old score ({old_score}). "
                    f"Not writing {safe_filename}."
                )
                return False

            # 7. Write the new code to the file
            try:
                # Make sure the skills directory exists
                os.makedirs(self.skills_dir, exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(generated_skill.code)
            except OSError as e:
                logger.error(f"SkillCreator: failed to write skill file {filepath}: {e}")
                return False

            # 8. Load the new module to obtain the real skill name. Safe now because
            #    top-level statements were verified to contain no function calls.
            real_skill_name = self._load_skill_name(filepath, safe_filename)
            if real_skill_name is None:
                # Load failed: roll back to the previous content
                logger.warning(f"SkillCreator: failed to load generated skill from {filepath}; rolling back.")
                self._restore_file(filepath, file_existed, old_code)
                return False

            # 9. Register the new skill under its real name
            self.registry.register(real_skill_name, f"Auto-generated skill for: {intent}")

            logger.info(f"SkillCreator: Successfully created {safe_filename} (skill name: {real_skill_name})")
            return True

        except Exception as e:
            logger.error(f"SkillCreator: Failed to generate skill: {e}")
            return False

    @staticmethod
    def _load_skill_name(filepath: str, safe_filename: str) -> Optional[str]:
        """Load the module at filepath, instantiate the first BaseSkill subclass, return its `name`."""
        module_name = f"_generated_{safe_filename[:-3]}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, filepath)
            if spec is None or spec.loader is None:
                logger.error(f"SkillCreator: could not create import spec for {filepath}")
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"SkillCreator: failed to load generated module {filepath}: {e}")
            return None

        try:
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is BaseSkill or not issubclass(obj, BaseSkill):
                    continue
                # Skip classes that were merely imported into the module
                if obj.__module__ != module.__name__:
                    continue
                skill_instance = obj()
                return skill_instance.name
        except Exception as e:
            logger.error(f"SkillCreator: failed to instantiate BaseSkill subclass from {filepath}: {e}")
            return None

        logger.error(f"SkillCreator: no BaseSkill subclass defined in {filepath}")
        return None

    @staticmethod
    def _restore_file(filepath: str, file_existed: bool, old_code: str) -> None:
        """Restore the previous file content, or remove the file if it did not exist before."""
        try:
            if file_existed:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(old_code)
            elif os.path.exists(filepath):
                os.remove(filepath)
        except OSError as e:
            logger.error(f"SkillCreator: failed to restore file {filepath}: {e}")

    # Top-level statement types that are allowed in a generated skill file.
    # Anything outside this set (e.g. `If`, `For`, `While`, `Try` at module
    # top level) is rejected — a skill file should be declarations only.
    _ALLOWED_TOPLEVEL = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.Assign,
        ast.AnnAssign,
        ast.Expr,  # only docstrings (string constants) — see check below
    )

    @classmethod
    def _check_top_level_safety(cls, code: str) -> Optional[str]:
        """
        Bug-1 fix: examine the module's top-level statements BEFORE the module
        is loaded via `exec_module`. Returns a rejection reason string if any
        top-level statement is unsafe (e.g. a function call that would execute
        during import), or None if the top level is safe.

        Allowed at top level: imports, class/function defs, simple assignments,
        and string-only expressions (module docstrings). Any `Call` node inside
        a top-level `Expr` or `Assign` value is rejected.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return f"syntax error: {e}"

        for stmt in tree.body:
            if not isinstance(stmt, cls._ALLOWED_TOPLEVEL):
                return f"disallowed top-level statement: {type(stmt).__name__}"

            # Expr: only string-constant docstrings are allowed.
            if isinstance(stmt, ast.Expr):
                if isinstance(stmt.value, ast.Constant) and isinstance(
                    stmt.value.value, str
                ):
                    continue
                # Any non-constant expression at top level is suspicious.
                for node in ast.walk(stmt.value):
                    if isinstance(node, ast.Call):
                        return "top-level expression contains a function call"
                return "top-level expression is not a string docstring"

            # Assign / AnnAssign: reject if the value contains any function call
            # (e.g. `x = os.system("rm -rf /")`).
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                value = stmt.value
                if value is None:
                    continue
                for node in ast.walk(value):
                    if isinstance(node, ast.Call):
                        return "top-level assignment contains a function call"

        return None

    # Stopwords excluded from similarity comparison so that common English
    # filler words don't inflate the Jaccard score.
    _SIMILARITY_STOPWORDS = frozenset({
        "the", "a", "an", "is", "are", "to", "for", "of", "and", "or", "in",
        "on", "with", "get", "query", "skill", "tool", "data", "please",
        "me", "my", "i", "you", "this", "that", "it",
    })

    def _find_similar_skill(self, intent: str) -> Optional[str]:
        """
        Bug-10 fix: scan already-registered skills and return the name of the
        first one whose description has high keyword overlap (Jaccard ≥ 0.5)
        with the requested intent. Returns None if no similar skill exists.

        Uses simple token overlap rather than embeddings so we don't pull in
        any new dependency.
        """
        intent_tokens = {
            w.lower()
            for w in intent.replace(",", " ").replace(".", " ").split()
            if len(w) > 2 and w.lower() not in self._SIMILARITY_STOPWORDS
        }
        if not intent_tokens:
            return None

        best_match: Optional[str] = None
        best_score = 0.0
        threshold = 0.5

        for skill_name, stats in self.registry.get_all_stats().items():
            description = stats.get("description", "") or ""
            desc_tokens = {
                w.lower()
                for w in description.replace(",", " ").replace(".", " ").split()
                if len(w) > 2 and w.lower() not in self._SIMILARITY_STOPWORDS
            }
            if not desc_tokens:
                continue
            intersection = intent_tokens & desc_tokens
            union = intent_tokens | desc_tokens
            score = len(intersection) / len(union) if union else 0.0
            if score > best_score:
                best_score = score
                best_match = skill_name

        if best_match is not None and best_score >= threshold:
            logger.info(
                f"SkillCreator: intent '{intent}' matches existing skill "
                f"'{best_match}' with Jaccard {best_score:.2f}"
            )
            return best_match
        return None
