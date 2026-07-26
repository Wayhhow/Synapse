import os
import sys
import importlib
import inspect
import json
import logging
import time
from typing import Dict, Optional, Type, Union, List, Any
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import BaseModel
from core.base import BaseSkill
from core.memory import Memory
from core.sandbox import Sandbox, SandboxResult
from core.skill_registry import SkillRegistry
from meta.skill_creator import SkillCreator
from meta.skill_evaluator import SkillEvaluator

logger = logging.getLogger(__name__)

class SkillRouter:
    """
    SkillRouter dynamically discovers and loads skills, and routes input to the appropriate skill using an LLM.
    Includes Meta-Evolution capabilities to write new skills if a required tool is missing.
    """

    def __init__(self, skills_dir: str = "skills", api_key: Optional[str] = None, model_name: str = "gpt-4o-mini",
                 registry: Optional["SkillRegistry"] = None, memory: Optional["Memory"] = None):
        load_dotenv()
        self.skills_dir = skills_dir
        self.skills: Dict[str, BaseSkill] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self._discover_skills()

        # OpenAI client is constructed lazily on first use so that operations
        # that don't need an LLM (e.g. `python cli.py --skills`, registry
        # inspection, /health endpoint) work without OPENAI_API_KEY set.
        # Constructor validates key eagerly and would crash otherwise.
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model_name
        self._client: Optional[AsyncOpenAI] = None

        # Initialize Skill Registry & Evaluator (allow injection for test isolation)
        self.registry = registry if registry is not None else SkillRegistry()

        # Initialize Meta-Evolution Creator (share the same registry so generated
        # skills and execution stats land in the same place)
        self.skill_creator = SkillCreator(
            skills_dir=self.skills_dir, api_key=self.api_key, model_name=self.model_name,
            registry=self.registry,
        )

        # Initialize Memory System (allow injection for test isolation)
        self.memory = memory if memory is not None else Memory(max_history=10, persist_path="data/memory.json")

        # Initialize Sandbox
        self.sandbox = Sandbox(timeout=10)

        # Initialize Evaluator (after registry is set)
        self.evaluator = SkillEvaluator(self.registry, skills_dir=self.skills_dir)
        for skill_name, skill in self.skills.items():
            self.registry.register(skill_name, skill.description)

    @property
    def client(self) -> AsyncOpenAI:
        """
        Lazily construct the OpenAI client on first use. Lets `python cli.py
        --skills` (and other introspection paths) work without an API key.
        """
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    def _discover_skills(self) -> None:
        """
        Dynamically scans the skills directory and loads all subclasses of BaseSkill.
        Handles importlib cache correctly: reloads existing modules and imports new ones.
        """
        # Bug-6 fix: clear the previously discovered skills so that any file
        # that has been removed from disk no longer lingers in the registry.
        # ``self._loaded_modules`` is intentionally NOT cleared: we still need
        # it to decide between `importlib.reload` (file modified) and
        # `importlib.import_module` (new file) on the next pass.
        self.skills = {}

        if not os.path.isdir(self.skills_dir):
            return

        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = f"{self.skills_dir}.{filename[:-3]}"
                try:
                    if module_name in self._loaded_modules:
                        # Previously loaded by SkillRouter; reload to refresh
                        module = importlib.reload(sys.modules[module_name])
                        logger.info(f"Reloaded module {module_name}")
                    elif module_name in sys.modules:
                        # Already in sys.modules but not tracked by SkillRouter yet; use as-is
                        module = sys.modules[module_name]
                        logger.info(f"Using existing module {module_name}")
                    else:
                        module = importlib.import_module(module_name)
                        logger.info(f"Imported module {module_name}")
                    self._loaded_modules[module_name] = module
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BaseSkill) and obj is not BaseSkill:
                            # Instantiate the skill
                            skill_instance = obj()
                            self.skills[skill_instance.name] = skill_instance
                except Exception as e:
                    logger.error(f"Error loading module {module_name}: {e}")

    def _get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        Dynamically generate OpenAI tool specifications from registered skills.
        Includes a default meta-tool to request a new skill if needed.
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

        # Add the meta-tool for automatic evolution
        tools.append({
            "type": "function",
            "function": {
                "name": "request_new_skill",
                "description": "Call this tool if NONE of the other tools can handle the user's request. This will trigger the agent to write a new Python skill dynamically.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intent": {
                            "type": "string",
                            "description": "A clear, concise description of the new task or skill that is missing."
                        },
                        "requirements": {
                            "type": "string",
                            "description": "Any specific technical requirements, inputs, or expected outputs."
                        }
                    },
                    "required": ["intent", "requirements"]
                }
            }
        })

        return tools

    async def process_query(self, user_query: str, is_retry: bool = False, session_id: Optional[str] = None) -> Union[str, BaseModel]:
        """
        Uses an LLM to understand the user's intent and intelligently route to a skill.
        If a skill is triggered, executes it and returns its Pydantic response model.
        If the meta-tool is triggered, dynamically generates the skill, reloads, and retries.
        If no skill is triggered, returns the plain text LLM response.

        Args:
            user_query: The user's natural language query.
            is_retry: Whether this call is a retry after meta-evolution generated a new skill.
                      Prevents infinite loops if skill generation succeeds but routing still fails.
        """
        messages = [
            {"role": "system", "content": "You are Synapse, an intelligent routing agent. Use the provided tools to answer the user's query if applicable. If NO tool is suitable, you MUST call the `request_new_skill` tool. Only answer directly via plain text if it's a simple greeting or casual chat."},
        ]

        if session_id:
            history = self.memory.get_history(session_id)
            messages.extend(history)

        messages.append({"role": "user", "content": user_query})

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
            # Bug-27 fix: OpenAI may return multiple tool calls per turn.
            # Full parallel/sequential execution of multiple tools is out of
            # scope for this iteration (planned as a separate spec); for now
            # we explicitly process only the first one and log a warning so
            # silent drops do not go unnoticed during debugging.
            if len(message.tool_calls) > 1:
                logger.warning(
                    f"Router: LLM returned {len(message.tool_calls)} tool_calls; "
                    f"only the first one ('{message.tool_calls[0].function.name}') "
                    f"will be executed in this iteration."
                )
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                logger.error(f"Router: failed to parse tool arguments JSON: {e}")
                return f"Error: invalid tool arguments (not valid JSON): {e}"

            # Bug-16 fix: tool arguments must be a JSON object so that
            # `**arguments` unpacking works. Anything else (list, string,
            # number) would have raised a confusing TypeError deeper in the
            # skill's execute().
            if not isinstance(arguments, dict):
                logger.error(
                    f"Router: tool arguments for '{function_name}' is "
                    f"{type(arguments).__name__}, expected object"
                )
                return (
                    f"Error: invalid tool arguments for '{function_name}': "
                    f"expected JSON object, got {type(arguments).__name__}"
                )

            # Meta-Evolution Intercept
            if function_name == "request_new_skill":
                if is_retry:
                    logger.warning("Meta-Evolution retry failed: already attempted to generate a skill for this intent.")
                    return "Error: Already attempted to generate a skill for this intent, but failed to execute it."

                logger.info(f"Meta-Evolution triggered for intent: {arguments.get('intent')}")

                success = await self.skill_creator.generate_skill(
                    intent=arguments.get("intent", user_query),
                    requirements=arguments.get("requirements", "")
                )

                if success:
                    # Dynamically reload skills
                    self._discover_skills()
                    # Bug-3 fix: do NOT record the user message here. The
                    # recursive `process_query` call below will record it
                    # exactly once if the retried skill succeeds, or record
                    # a user + assistant-error pair if it fails. Recording
                    # here as well led to duplicated user messages in history.
                    # Retry the original query
                    logger.info("Skill generated successfully. Retrying original query...")
                    return await self.process_query(user_query, is_retry=True, session_id=session_id)
                else:
                    logger.error("Meta-Evolution failed to generate a valid skill.")
                    if session_id:
                        self.memory.add_message(session_id, "user", user_query)
                        self.memory.add_message(
                            session_id, "assistant",
                            "Error: Meta-Evolution failed to generate a valid skill."
                        )
                    return "Error: Meta-Evolution failed to generate a valid skill."

            # Standard Skill Routing
            if function_name in self.skills:
                skill = self.skills[function_name]

                start_time = time.time()
                try:
                    if skill.use_sandbox and self.sandbox is not None:
                        # Bug-2 fix: use the async sandbox entry point so the
                        # FastAPI event loop is not blocked while the child
                        # process runs.
                        sandbox_result: SandboxResult = await self.sandbox.execute_async(skill, **arguments)
                        if not sandbox_result.success:
                            raise RuntimeError(sandbox_result.error or "Sandbox execution failed")
                        result = sandbox_result.result
                    else:
                        result = await skill.execute(**arguments)
                    execution_time = time.time() - start_time

                    # Bug-4 fix: skills may catch exceptions internally and
                    # return a response with a non-empty `error` field. The
                    # previous code recorded `success=True` for those, which
                    # inflated the skill's health score and hid failures from
                    # the operator. Treat a truthy `error` field as a failure.
                    is_soft_failure = False
                    if isinstance(result, BaseModel) and getattr(result, "error", None):
                        is_soft_failure = True
                        soft_error_msg = str(result.error)
                        self.registry.record_execution(
                            function_name, success=False,
                            execution_time=execution_time, error=soft_error_msg,
                        )
                        logger.warning(
                            f"Skill '{function_name}' returned a response with "
                            f"error field set: {soft_error_msg}"
                        )
                    if not is_soft_failure:
                        self.registry.record_execution(function_name, success=True, execution_time=execution_time)
                except Exception as e:
                    execution_time = time.time() - start_time
                    self.registry.record_execution(function_name, success=False, execution_time=execution_time, error=str(e))
                    logger.error(f"Skill '{function_name}' execution failed: {e}")

                    if session_id:
                        self.memory.add_message(session_id, "user", user_query)
                        self.memory.add_message(session_id, "assistant", str(f"Error: Skill '{function_name}' execution failed: {e}"))

                    return f"Error: Skill '{function_name}' execution failed: {e}"

                if session_id:
                    self.memory.add_message(session_id, "user", user_query)
                    self.memory.add_message(session_id, "assistant", str(result))

                return result
            else:
                logger.error(f"Skill '{function_name}' was requested by LLM but not found in registered skills.")
                return f"Error: Skill '{function_name}' was requested by LLM but not found in registered skills."

        # If no tool was called, return the plain text response
        text_result = message.content or ""
        if session_id:
            self.memory.add_message(session_id, "user", user_query)
            self.memory.add_message(session_id, "assistant", text_result)
        return text_result

    def route(self, text: str) -> Optional[BaseSkill]:
        """
        [Deprecated] A mock routing logic that matches input text against skill names or descriptions.
        Kept for backward compatibility during tests.
        """
        text_lower = text.lower()
        # Ignore short tokens (<=3 chars) like "the", "is", "in", "up" — they are
        # stopwords that cause false matches across skills. Kept logic simple but
        # robust enough for the deprecated mock router.
        text_words = {w for w in text_lower.split() if len(w) > 3}
        for skill in self.skills.values():
            # Check if any word in the skill name or description is in the input text
            # A very simple mock logic.
            skill_keywords = set(skill.name.lower().split('_') + skill.description.lower().split())
            skill_keywords = {w for w in skill_keywords if len(w) > 3}
            if skill_keywords.intersection(text_words):
                return skill
        return None
