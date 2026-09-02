import os
import re
import ast
import json
import logging
import importlib.util
import inspect
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from core.skill_registry import SkillRegistry
from core.base import BaseSkill
from core.config import SynapseConfig, load_env_file
from core.resilience import with_retries
from meta.skill_evaluator import SkillEvaluator

logger = logging.getLogger(__name__)

class GeneratedSkill(BaseModel):
    filename: str = Field(..., description="The name of the python file, e.g., 'crypto_price_skill.py'")
    class_name: str = Field(..., description="The name of the class inheriting from BaseSkill, e.g., 'CryptoPriceSkill'")
    code: str = Field(..., description="The complete python code for the skill")

class SkillCreator:
    """
    SkillCreator is the Meta-Evolution Module responsible for writing and saving
    new skills using an LLM.

    Generation follows the Voyager "iterative prompting mechanism" (Wang et al.,
    2023): instead of a single generate-then-pray call, the creator runs up to
    ``config.generate_max_attempts`` rounds of generate -> validate -> feed the
    validation/execution errors back to the LLM -> regenerate. The ratchet
    (score must not decrease) gates every write, and replaced skill files are
    archived under ``skills/.archive/`` instead of being destroyed, so evolution
    keeps a fossil record.
    """

    def __init__(
        self,
        skills_dir: str = "skills",
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        registry: Optional[SkillRegistry] = None,
        config: Optional[SynapseConfig] = None,
    ):
        load_env_file()
        self.skills_dir = skills_dir
        self.config = config or SynapseConfig.from_env()
        # Explicit kwargs win over env config (tests inject dummies).
        self.api_key = api_key or self.config.api_key
        self.model_name = model_name or self.config.model
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
            client_kwargs = {}
            if self.config.base_url:
                client_kwargs["base_url"] = self.config.base_url
            if client_kwargs:
                self._client = AsyncOpenAI(api_key=self.api_key, **client_kwargs)
            else:
                self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    @property
    def archive_dir(self) -> str:
        return os.path.join(self.skills_dir, ".archive")

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def generate_skill(self, intent: str, requirements: str = "") -> bool:
        """
        Uses an LLM to generate a new Python skill and saves it to the skills
        directory. Returns True if successful, False otherwise.

        Voyager-style loop: each failed validation round feeds the exact
        errors back into the next generation attempt, so transient model
        mistakes (a missing import, a bad filename) are repaired without
        human intervention.

        Security ordering (Bug-1 fix): top-level safety check + antipattern AST
        evaluation happen BEFORE the module is loaded via `exec_module`, so that
        a malicious `import os; os.system(...)` at module top level is rejected
        instead of executed in the main process.
        """
        feedback = ""
        for attempt in range(1, max(1, self.config.generate_max_attempts) + 1):
            skill_data = await self._request_skill_json(intent, requirements, feedback)
            if skill_data is None:
                return False

            # 1. Basic syntax check
            try:
                ast.parse(skill_data.code)
            except SyntaxError as e:
                logger.error(f"SkillCreator: Generated code contains syntax errors: {e}")
                feedback = f"SyntaxError: {e}. Fix the syntax and return the complete corrected file."
                continue

            # 2. Bug-1 fix: top-level safety check BEFORE any module load / file write.
            rejection = self._check_top_level_safety(skill_data.code)
            if rejection is not None:
                logger.error(f"SkillCreator: rejected unsafe generated code: {rejection}")
                feedback = (
                    f"SECURITY REJECTION: {rejection}. Top-level code may only contain imports, "
                    "class/function definitions, constant assignments and docstrings. "
                    "Move any executable logic inside methods."
                )
                continue

            # 3. Bug-28 fix: AST-based antipattern check on the whole code body
            #    (catches `getattr(builtins, "eval")("1")` style obfuscation that
            #    substring matching misses). The penalty returned by
            #    `check_antipattern_ast` is `15 - 5*hits` clamped to 0:
            #      0 hits -> 15 (clean)   1 hit -> 10   2 hits -> 5   3+ hits -> 0
            #    We reject only when 3+ dangerous calls are detected (penalty
            #    reaches 0). 1-2 hits are left to the ratchet mechanism, which
            #    will roll back the new file when its total score is lower than
            #    the existing one. This layered design keeps the
            #    `test_generate_skill_ratchet_rollback_on_lower_quality` test
            #    meaningful (it relies on a single `eval` going through the
            #    antipattern gate so the ratchet can reject it).
            antipattern_penalty = self.evaluator.check_antipattern_ast(skill_data.code)
            if antipattern_penalty <= 0.0:
                logger.error(
                    "SkillCreator: rejected generated code - 3 or more "
                    "dangerous calls detected by AST scan."
                )
                feedback = (
                    "SECURITY REJECTION: 3 or more dangerous calls (eval/exec/os.system/"
                    "subprocess/...) detected. Remove them and implement the logic with safe "
                    "library calls instead."
                )
                continue

            # 4. Bug-10 fix: avoid generating a duplicate skill. If an existing
            #    skill already covers this intent (high keyword overlap), skip.
            #    Retrying cannot fix a duplicate, so return immediately.
            similar = self._find_similar_skill(intent)
            if similar is not None:
                logger.warning(
                    f"SkillCreator: similar skill '{similar}' already exists for intent "
                    f"'{intent}'; skipping generation to avoid duplicates."
                )
                return False

            # 5. Filename safety: sanitize rather than reject. Prefer the
            #    LLM-provided basename; fall back to the class name so a bad
            #    filename alone never kills an otherwise valid skill.
            safe_filename = self._sanitize_filename(skill_data.filename, skill_data.class_name)
            if safe_filename is None:
                feedback = "Invalid filename. Use a simple snake_case name ending with '_skill.py'."
                continue
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

            new_score = self.evaluator.evaluate_code_quality(skill_data.code)
            old_score = self.evaluator.evaluate_code_quality(old_code) if old_code else 0.0
            if new_score < old_score:
                logger.warning(
                    f"SkillCreator: Ratchet check failed - new score ({new_score}) < old score ({old_score}). "
                    f"Not writing {safe_filename}."
                )
                feedback = (
                    f"RATCHET REJECTED: quality score {new_score} < existing {old_score}. "
                    "Provide complete name/description/expected_args/expected_response_type/execute "
                    "members, error handling and no dangerous calls."
                )
                continue

            # 7. Write the new code to the file (archiving the old version first
            #    so the ratchet's replacements keep a fossil record).
            try:
                os.makedirs(self.skills_dir, exist_ok=True)
                if file_existed and old_code and old_code != skill_data.code:
                    self._archive_file(safe_filename, old_code)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(skill_data.code)
            except OSError as e:
                logger.error(f"SkillCreator: failed to write skill file {filepath}: {e}")
                return False

            # 8. Load the new module to obtain the real skill name. Safe now because
            #    top-level statements were verified to contain no function calls.
            real_skill_name = self._load_skill_name(filepath, safe_filename)
            if real_skill_name is None:
                # Load failed: roll back to the previous content, then let the
                # next Voyager round repair the code with the load error.
                logger.warning(f"SkillCreator: failed to load generated skill from {filepath}; rolling back.")
                self._restore_file(filepath, file_existed, old_code)
                feedback = "The generated module raised an exception while being imported. Fix the code so it imports cleanly."
                continue

            # 9. Register the new skill under its real name
            self.registry.register(real_skill_name, f"Auto-generated skill for: {intent}")

            logger.info(f"SkillCreator: Successfully created {safe_filename} (skill name: {real_skill_name}, attempt {attempt})")
            return True

        logger.error(f"SkillCreator: generation failed after {self.config.generate_max_attempts} attempts.")
        return False

    async def repair_skill(self, skill_name: str, error: str) -> bool:
        """
        Self-healing (Voyager-style environment feedback): when a skill fails
        repeatedly at runtime, ask the LLM to fix the existing code, passing
        the actual execution error as context. The ratchet still gates the
        replacement (the repaired version must not score lower than the
        current one) and the previous version is archived.
        """
        skill_file = self._find_skill_file(skill_name)
        if skill_file is None:
            logger.warning(f"SkillCreator: repair requested for unknown skill '{skill_name}'")
            return False
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                current_code = f.read()
        except OSError as e:
            logger.error(f"SkillCreator: cannot read {skill_file} for repair: {e}")
            return False

        old_score = self.evaluator.evaluate_code_quality(current_code)

        system_prompt = (
            "You are a master Python software engineer repairing a broken skill in the "
            "Synapse AI agent architecture. The skill below failed at runtime. Fix the bug "
            "while KEEPING the same skill `name`, the same argument model fields, and the "
            "same response model fields so callers are not broken. Rules:\n"
            "1. Return a complete Python file.\n"
            "2. Keep Pydantic models for arguments and response, and a BaseSkill subclass.\n"
            "3. Improve error handling so transient failures return an `error` field instead of raising.\n"
            "4. Respond with JSON containing 'filename', 'class_name', and 'code' matching the GeneratedSkill schema. No markdown."
        )
        user_prompt = (
            f"Runtime error:\n{error}\n\n"
            f"Current code:\n```python\n{current_code}\n```"
        )

        try:
            response = await with_retries(
                lambda: self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                ),
                attempts=self.config.app_retries,
            )
            skill_data = GeneratedSkill(**json.loads(response.choices[0].message.content))
        except Exception as e:
            logger.error(f"SkillCreator: repair LLM call failed for '{skill_name}': {e}")
            return False

        # Validation gates (same as generation).
        try:
            ast.parse(skill_data.code)
        except SyntaxError as e:
            logger.error(f"SkillCreator: repaired code has syntax errors: {e}")
            return False
        if self._check_top_level_safety(skill_data.code) is not None:
            logger.error("SkillCreator: repaired code rejected by top-level safety check")
            return False
        if self.evaluator.check_antipattern_ast(skill_data.code) <= 0.0:
            logger.error("SkillCreator: repaired code rejected by antipattern scan")
            return False
        new_score = self.evaluator.evaluate_code_quality(skill_data.code)
        if new_score < old_score:
            logger.warning(
                f"SkillCreator: ratchet rejected repair of '{skill_name}' ({new_score} < {old_score})"
            )
            return False

        safe_filename = self._sanitize_filename(skill_data.filename, skill_data.class_name) or os.path.basename(skill_file)
        filepath = os.path.join(self.skills_dir, safe_filename)
        try:
            self._archive_file(os.path.basename(skill_file), current_code)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(skill_data.code)
        except OSError as e:
            logger.error(f"SkillCreator: failed to write repaired skill: {e}")
            return False

        loaded_name = self._load_skill_name(filepath, safe_filename)
        if loaded_name is None:
            logger.error(f"SkillCreator: repaired skill failed to load; rolling back '{skill_name}'.")
            self._restore_file(filepath, True, current_code)
            return False

        logger.info(f"SkillCreator: successfully repaired '{skill_name}' -> {safe_filename}")
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request_skill_json(self, intent: str, requirements: str, feedback: str) -> Optional[GeneratedSkill]:
        """One LLM round-trip. When ``feedback`` is non-empty (a previous
        attempt failed validation), it is injected so the model can repair
        its own output."""
        system_prompt = (
            "You are a master Python software engineer working on the Synapse AI agent architecture. "
            "Your task is to create a new skill to satisfy the user's intent. "
            "The new skill MUST STRICTLY follow these rules:\n"
            "1. It must be a complete Python file.\n"
            "2. It must define Pydantic models for both arguments and response (e.g., `MyArgs`, `MyResponse`).\n"
            "3. It must define a class that inherits from `core.base.BaseSkill`.\n"
            "4. The class must implement `name`, `description`, `expected_args`, and `expected_response_type` as @property.\n"
            "5. The class must implement `async def execute(self, **kwargs) -> BaseModel` with try/except error handling.\n"
            "6. Top-level code may only contain imports, class definitions and constants — no executable statements.\n"
            "7. Never use eval/exec/os.system/subprocess or similar dangerous calls.\n"
            "8. The description must end with 'Trigger words: word1, word2, ...' listing when to use this skill.\n"
            "9. You must provide a JSON response containing 'filename', 'class_name', and 'code' conforming to the GeneratedSkill schema.\n"
            "Do not return markdown, only the raw JSON string matching the GeneratedSkill schema."
        )
        user_prompt = f"Intent: {intent}\nRequirements: {requirements}"
        if feedback:
            user_prompt += f"\n\nYour previous attempt was rejected:\n{feedback}\nFix these problems and return the complete corrected JSON."

        try:
            response = await with_retries(
                lambda: self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                ),
                attempts=self.config.app_retries,
            )
            content = response.choices[0].message.content
            return GeneratedSkill(**json.loads(content))
        except Exception as e:
            logger.error(f"SkillCreator: Failed to generate skill: {e}")
            return None

    @staticmethod
    def _sanitize_filename(filename: str, class_name: str = "") -> Optional[str]:
        """Return a safe basename ending in .py, or None if impossible."""
        name = os.path.basename((filename or "").strip())
        if name in ("", ".", "..") or "/" in name or "\\" in name or name.startswith("."):
            # Fall back to a snake_case name derived from the class name.
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", class_name or "").lower()
            snake = re.sub(r"[^a-z0-9_]", "", snake).strip("_")
            name = f"{snake or 'generated'}_skill.py"
        if not name.endswith(".py"):
            name += ".py"
        if not re.fullmatch(r"[A-Za-z0-9_\-]+\.py", name):
            return None
        return name

    def _archive_file(self, filename: str, code: str) -> None:
        """Store a timestamped copy of ``code`` under skills/.archive/<stem>/."""
        try:
            stem = filename[:-3] if filename.endswith(".py") else filename
            dest_dir = os.path.join(self.archive_dir, stem)
            os.makedirs(dest_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            dest = os.path.join(dest_dir, f"{stamp}_{stem}.py")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(code)
            logger.info(f"SkillCreator: archived previous version of '{filename}' -> {dest}")
        except OSError as e:
            logger.warning(f"SkillCreator: failed to archive '{filename}': {e}")

    def _find_skill_file(self, skill_name: str) -> Optional[str]:
        """Locate the source file whose BaseSkill subclass has `name == skill_name`."""
        direct = os.path.join(self.skills_dir, f"{skill_name}.py")
        if os.path.isfile(direct):
            return direct
        if not os.path.isdir(self.skills_dir):
            return None
        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            filepath = os.path.join(self.skills_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                if any(
                    (isinstance(b, ast.Name) and b.id == "BaseSkill")
                    or (isinstance(b, ast.Attribute) and b.attr == "BaseSkill")
                    for b in node.bases
                ):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == "name":
                            for stmt in item.body:
                                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Constant):
                                    if stmt.value.value == skill_name:
                                        return filepath
        return None

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
