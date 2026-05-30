import os
import importlib
import inspect
import json
from typing import Dict, Optional, Type, Union, List, Any
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel
from core.base import BaseSkill

class SkillRouter:
    """
    SkillRouter dynamically discovers and loads skills, and routes input to the appropriate skill using an LLM.
    """
    def __init__(self, skills_dir: str = "skills", api_key: Optional[str] = None, model_name: str = "gpt-4o-mini"):
        load_dotenv()
        self.skills_dir = skills_dir
        self.skills: Dict[str, BaseSkill] = {}
        self._discover_skills()

        # Initialize OpenAI Client
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=self.api_key)

    def _discover_skills(self) -> None:
        """
        Dynamically scans the skills directory and loads all subclasses of BaseSkill.
        """
        if not os.path.isdir(self.skills_dir):
            return

        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = f"{self.skills_dir}.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                            # Instantiate the skill
                            skill_instance = obj()
                            self.skills[skill_instance.name] = skill_instance
                except Exception as e:
                    print(f"Error loading module {module_name}: {e}")

    def _get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        Dynamically generate OpenAI tool specifications from registered skills.
        """
        tools = []
        for skill_name, skill in self.skills.items():
            schema = skill.expected_args.model_json_schema()
            # Remove pydantic specific fields that might confuse the LLM if any
            if "title" in schema:
                del schema["title"]

            tool = {
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": schema
                }
            }
            tools.append(tool)
        return tools

    async def process_query(self, user_query: str) -> Union[str, BaseModel]:
        """
        Uses an LLM to understand the user's intent and intelligently route to a skill.
        If a skill is triggered, executes it and returns its Pydantic response model.
        If no skill is triggered, returns the plain text LLM response.
        """
        messages = [
            {"role": "system", "content": "You are Synapse, an intelligent routing agent. Use the provided tools to answer the user's query if applicable. If no tool is suitable, answer the query directly."},
            {"role": "user", "content": user_query}
        ]

        tools = self._get_tools_schema()

        # Make the LLM call
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None
        )

        message = response.choices[0].message

        # If the LLM decided to use a tool (route to a skill)
        if message.tool_calls:
            # For simplicity, we process the first tool call in this iteration
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name

            if function_name in self.skills:
                skill = self.skills[function_name]
                arguments = json.loads(tool_call.function.arguments)

                # Execute the skill with the provided arguments
                result = await skill.execute(**arguments)
                return result
            else:
                return f"Error: Skill '{function_name}' was requested by LLM but not found in registered skills."

        # If no tool was called, return the plain text response
        return message.content or ""

    def route(self, text: str) -> Optional[BaseSkill]:
        """
        [Deprecated] A mock routing logic that matches input text against skill names or descriptions.
        Kept for backward compatibility during tests.
        """
        text_lower = text.lower()
        for skill in self.skills.values():
            skill_keywords = set(skill.name.lower().split('_') + skill.description.lower().split())
            text_words = set(text_lower.split())
            if skill_keywords.intersection(text_words):
                return skill
        return None
