import os
import ast
import json
import logging
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from openai import AsyncOpenAI
from core.skill_registry import SkillRegistry
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
    def __init__(self, skills_dir: str = "skills", api_key: Optional[str] = None, model_name: str = "gpt-4o-mini"):
        load_dotenv()
        self.skills_dir = skills_dir
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=self.api_key)

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

            # Ratchet mechanism: if file already exists, compare scores
            old_score = None
            file_existed = os.path.exists(filepath)
            if file_existed:
                registry = SkillRegistry()
                evaluator = SkillEvaluator(registry)
                old_skill_name = safe_filename.replace('.py', '')
                old_score = evaluator.evaluate(old_skill_name)

            # Save the code to the file
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(generated_skill.code)

            # Ratchet: if old file existed, check if new version is better
            if file_existed and old_score is not None:
                registry = SkillRegistry()
                evaluator = SkillEvaluator(registry)
                new_skill_name = safe_filename.replace('.py', '')
                registry.register(new_skill_name, f"Auto-generated skill for: {intent}")
                new_score = evaluator.evaluate(new_skill_name)
                if new_score < old_score:
                    logger.warning(f"SkillCreator: Ratchet check failed - new score ({new_score}) < old score ({old_score}). Reverting.")
                    os.remove(filepath)
                    return False

            # Register the new skill in the registry
            registry = SkillRegistry()
            registry.register(safe_filename.replace('.py', ''), f"Auto-generated skill for: {intent}")

            logger.info(f"SkillCreator: Successfully created {safe_filename}")
            return True

        except Exception as e:
            logger.error(f"SkillCreator: Failed to generate skill: {e}")
            return False
