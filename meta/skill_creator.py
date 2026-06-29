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
        self.client = AsyncOpenAI(api_key=self.api_key)
        self.registry = registry if registry is not None else SkillRegistry()
        self.evaluator = SkillEvaluator(registry=self.registry, skills_dir=self.skills_dir)

    async def generate_skill(self, intent: str, requirements: str = "") -> bool:
        """
        Uses an LLM to generate a new Python skill and saves it to the skills directory.
        Returns True if successful, False otherwise.
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

            # Basic security/syntax check: Attempt to parse the AST
            try:
                ast.parse(generated_skill.code)
            except SyntaxError as e:
                logger.error(f"SkillCreator: Generated code contains syntax errors: {e}")
                return False

            # Ensure the filename ends with .py
            if not generated_skill.filename.endswith(".py"):
                generated_skill.filename += ".py"

            # Filename safety validation
            safe_filename = os.path.basename(generated_skill.filename)
            if "/" in safe_filename or "\\" in safe_filename:
                logger.error(f"SkillCreator: Rejected unsafe filename: {generated_skill.filename}")
                return False

            filepath = os.path.join(self.skills_dir, safe_filename)

            # Ratchet mechanism: capture old content before overwriting
            file_existed = os.path.exists(filepath)
            old_code = ""
            if file_existed:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        old_code = f.read()
                except OSError as e:
                    logger.warning(f"SkillCreator: failed to read previous skill file {filepath}: {e}")
                    old_code = ""

            # Write the new code to the file
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(generated_skill.code)
            except OSError as e:
                logger.error(f"SkillCreator: failed to write skill file {filepath}: {e}")
                return False

            # Load the new module and instantiate the BaseSkill subclass to get the real skill name
            real_skill_name = self._load_skill_name(filepath, safe_filename)
            if real_skill_name is None:
                # Load failed: roll back to the previous content
                logger.warning(f"SkillCreator: failed to load generated skill from {filepath}; rolling back.")
                self._restore_file(filepath, file_existed, old_code)
                return False

            # Register the new skill under its real name
            self.registry.register(real_skill_name, f"Auto-generated skill for: {intent}")

            # Ratchet: only keep the new version if its code quality is not worse than the old one
            new_score = self.evaluator.evaluate_code_quality(generated_skill.code)
            old_score = self.evaluator.evaluate_code_quality(old_code) if old_code else 0.0
            if new_score < old_score:
                logger.warning(
                    f"SkillCreator: Ratchet check failed - new score ({new_score}) < old score ({old_score}). "
                    f"Rolling back {safe_filename}."
                )
                self._restore_file(filepath, file_existed, old_code)
                return False

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
