import os
import sys
import importlib
import inspect
import json
import logging
import time
from typing import Dict, Optional, Union, List, Any, AsyncIterator
from openai import AsyncOpenAI
from pydantic import BaseModel
from core.base import BaseSkill
from core.config import SynapseConfig, load_env_file
from core.memory import Memory
from core.resilience import with_retries
from core.sandbox import Sandbox, SandboxResult
from core.skill_registry import SkillRegistry
from core.tracer import TraceRecorder, Trace
from meta.skill_creator import SkillCreator
from meta.skill_evaluator import SkillEvaluator

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Synapse, an intelligent agent backed by a growing library of skills.\n"
    "Resolve the user's request step by step:\n"
    "1. Call the most relevant tool(s) with valid JSON arguments.\n"
    "2. After each tool result, either call another tool (if you need more data or an "
    "action failed and another tool could help) or produce the final answer.\n"
    "3. Prefer existing skills. Call `request_new_skill` ONLY if no existing tool can "
    "possibly handle the request.\n"
    "4. Answer in the user's language, concisely. Plain text without tools is only for "
    "greetings or casual chat."
)


class SkillRouter:
    """
    SkillRouter dynamically discovers and loads skills, and resolves user
    queries with an OpenAI-compatible LLM.

    Evolution from the original single-shot router: ``process_query`` now runs
    a bounded ReAct-style agent loop (OpenManus/LangGraph style). Each round
    the LLM may call one or more tools; every tool result is fed back as a
    ``tool`` message, and the loop continues until the model produces a final
    answer or ``config.max_steps`` rounds are consumed. ``max_steps=1``
    reproduces the legacy single-shot behavior (skill result returned directly).

    Self-healing: when a skill records ``config.auto_repair_threshold``
    consecutive failures, the router triggers a Voyager-style LLM repair of
    that skill's source (ratchet-gated, previous version archived).
    """

    def __init__(self, skills_dir: str = "skills", api_key: Optional[str] = None,
                 model_name: Optional[str] = None,
                 registry: Optional["SkillRegistry"] = None, memory: Optional["Memory"] = None,
                 config: Optional[SynapseConfig] = None):
        load_env_file()
        self.skills_dir = skills_dir
        self.config = config or SynapseConfig.from_env()
        # Explicit kwargs win over env config (backwards compatible with the
        # original constructor and used heavily by tests).
        self.api_key = api_key or self.config.api_key
        self.model_name = model_name or self.config.model
        self.skills: Dict[str, BaseSkill] = {}
        self._loaded_modules: Dict[str, Any] = {}
        self._discover_skills()

        # OpenAI client is constructed lazily on first use so that operations
        # that don't need an LLM (e.g. `python cli.py --skills`, registry
        # inspection, /health endpoint) work without OPENAI_API_KEY set.
        self._client: Optional[AsyncOpenAI] = None

        # Initialize Skill Registry & Evaluator (allow injection for test isolation)
        self.registry = registry if registry is not None else SkillRegistry(persist_path=self.config.registry_persist_path)

        # Initialize Meta-Evolution Creator (share the same registry so generated
        # skills and execution stats land in the same place)
        self.skill_creator = SkillCreator(
            skills_dir=self.skills_dir, api_key=self.api_key, model_name=self.model_name,
            registry=self.registry, config=self.config,
        )

        # Initialize Memory System (allow injection for test isolation). The
        # rolling-summary hook needs an LLM, so it is only attached when an API
        # key is available; otherwise Memory degrades to plain FIFO truncation.
        if memory is not None:
            self.memory = memory
        else:
            self.memory = Memory(
                max_history=self.config.memory_max_history,
                persist_path=self.config.memory_persist_path,
                summarizer=self._summarize_history if self.api_key else None,
            )

        # Initialize Sandbox
        self.sandbox = Sandbox(timeout=self.config.sandbox_timeout)

        # Initialize Evaluator (after registry is set)
        self.evaluator = SkillEvaluator(self.registry, skills_dir=self.skills_dir)

        # Observability
        self.tracer = TraceRecorder(self.config.trace_path if self.config.trace_enabled else None)

        # Skills reported as used by the most recent process_query call
        # (surfaced via the web API for attribution).
        self.last_skills_used: List[str] = []

        for skill_name, skill in self.skills.items():
            self.registry.register(skill_name, skill.description)

    @property
    def client(self) -> AsyncOpenAI:
        """
        Lazily construct the OpenAI client on first use. Lets `python cli.py
        --skills` (and other introspection paths) work without an API key.
        """
        if self._client is None:
            kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.config.llm_timeout}
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client = AsyncOpenAI(max_retries=self.config.llm_max_retries, **kwargs)
        return self._client

    async def _summarize_history(self, dropped: List[dict]) -> str:
        """Compress dropped conversation turns into a compact rolling summary
        (the LLM-backed half of Memory's summarization support)."""
        excerpt = "\n".join(f"{m['role']}: {m['content']}" for m in dropped)
        response = await with_retries(
            lambda: self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": (
                        "Summarize this conversation excerpt into concise bullet points, "
                        "preserving key facts: names, numbers, decisions and open questions. "
                        "Maximum 120 words."
                    )},
                    {"role": "user", "content": excerpt},
                ],
                temperature=0.0,
            ),
            attempts=self.config.app_retries,
        )
        return response.choices[0].message.content or ""

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

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    async def process_query_events(self, user_query: str, session_id: Optional[str] = None) -> AsyncIterator[Dict[str, Any]]:
        """
        Run the agent loop, yielding progress events:

        - ``{"type": "llm", "step": n, "duration_ms": ms}``        — an LLM round finished
        - ``{"type": "tool_start", "name": ..., "step": n}``       — a tool call began
        - ``{"type": "tool_result", "name": ..., "success": bool,
             "duration_ms": ms, "error": ...}``                     — a tool finished
        - ``{"type": "meta", "status": "generating"|"ok"|"failed", "intent": ...}``
        - ``{"type": "final", "text": str, "result": BaseModel|None, "skills_used": [...]}``

        The final event is always the last one yielded.
        """
        trace: Optional[Trace] = self.tracer.start(user_query, session_id) if self.tracer.enabled else None
        skills_used: List[str] = []
        final_type = "error"

        try:
            # Compress overflowed history into a rolling summary when possible.
            if session_id and self.memory.summarizer is not None:
                await self.memory.apply_summary(session_id)

            messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
            if session_id:
                messages.extend(self.memory.get_history(session_id))
            messages.append({"role": "user", "content": user_query})

            if session_id:
                self.memory.add_message(session_id, "user", user_query)

            tools = self._get_tools_schema()
            max_steps = max(1, self.config.max_steps)
            final_text = ""
            result_obj: Optional[BaseModel] = None
            last_tool_content = ""
            generated_intents: set = set()

            for step in range(1, max_steps + 1):
                t0 = time.monotonic()
                try:
                    response = await with_retries(
                        lambda: self.client.chat.completions.create(
                            model=self.model_name,
                            messages=messages,
                            tools=tools if tools else None,
                            tool_choice="auto" if tools else None,
                            temperature=self.config.temperature,
                        ),
                        attempts=self.config.app_retries,
                    )
                except Exception as e:
                    logger.error(f"Router: LLM call failed: {e}")
                    final_text = f"Error: LLM call failed: {e}"
                    if trace:
                        trace.add_step("llm", self.model_name, (time.monotonic() - t0) * 1000, success=False, error=str(e))
                    yield {"type": "final", "text": final_text, "result": None, "skills_used": skills_used}
                    if session_id:
                        self.memory.add_message(session_id, "assistant", final_text)
                    final_type = "error"
                    return
                llm_ms = (time.monotonic() - t0) * 1000
                if trace:
                    trace.add_step("llm", self.model_name, llm_ms)
                yield {"type": "llm", "step": step, "duration_ms": round(llm_ms, 1)}

                message = response.choices[0].message

                # No tool call => final natural-language answer.
                if not message.tool_calls:
                    final_text = message.content or ""
                    final_type = "text"
                    break

                # Append the assistant tool-call turn so the following tool
                # results are accepted by the API.
                messages.append({
                    "role": "assistant",
                    "content": message.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                })

                # Bug-27 (fixed properly): execute EVERY tool call of the turn,
                # in order, feeding each result back to the model.
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as e:
                        logger.error(f"Router: failed to parse tool arguments JSON: {e}")
                        messages.append({
                            "role": "tool", "tool_call_id": tool_call.id,
                            "content": f"Error: invalid tool arguments (not valid JSON): {e}",
                        })
                        if trace:
                            trace.add_step("tool", function_name, 0.0, success=False, error=f"bad JSON args: {e}")
                        continue

                    # Bug-16 fix: tool arguments must be a JSON object so that
                    # `**arguments` unpacking works.
                    if not isinstance(arguments, dict):
                        logger.error(
                            f"Router: tool arguments for '{function_name}' is "
                            f"{type(arguments).__name__}, expected object"
                        )
                        messages.append({
                            "role": "tool", "tool_call_id": tool_call.id,
                            "content": (
                                f"Error: invalid tool arguments for '{function_name}': "
                                f"expected JSON object, got {type(arguments).__name__}"
                            ),
                        })
                        continue

                    yield {"type": "tool_start", "name": function_name, "step": step}

                    # ---- Meta-Evolution intercept ----
                    if function_name == "request_new_skill":
                        intent = arguments.get("intent", user_query)
                        if intent in generated_intents:
                            tool_content = (
                                "A skill for this intent was already requested in this conversation. "
                                "It is now available in the tool list — call it directly; if it truly "
                                "does not fit, answer with what you can."
                            )
                        else:
                            generated_intents.add(intent)
                            logger.info(f"Meta-Evolution triggered for intent: {intent}")
                            yield {"type": "meta", "status": "generating", "intent": intent}
                            if trace:
                                trace.add_step("meta", "request_new_skill", 0.0, detail={"intent": intent})
                            success = await self.skill_creator.generate_skill(
                                intent=intent, requirements=arguments.get("requirements", "")
                            )
                            if success:
                                # Pick up the new skill file; the next LLM round
                                # receives a refreshed tool schema automatically.
                                self._discover_skills()
                                for name, skill in self.skills.items():
                                    self.registry.register(name, skill.description)
                                tool_content = (
                                    f"Skill generated successfully for intent '{intent}'. "
                                    "A new tool is now available in your tool list — call it now."
                                )
                                yield {"type": "meta", "status": "ok", "intent": intent}
                            else:
                                tool_content = (
                                    f"Meta-Evolution failed to generate a valid skill for intent '{intent}'. "
                                    "Explain to the user what you tried and answer as best you can."
                                )
                                yield {"type": "meta", "status": "failed", "intent": intent}
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_content})
                        continue

                    # ---- Standard skill routing ----
                    if function_name in self.skills:
                        skill = self.skills[function_name]
                        start_time = time.monotonic()
                        success = False
                        error_msg: Optional[str] = None
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
                            duration_ms = (time.monotonic() - start_time) * 1000

                            # Bug-4 fix: skills may catch exceptions internally and
                            # return a response with a non-empty `error` field — treat
                            # that as a failure for the registry.
                            soft_error = None
                            if isinstance(result, BaseModel) and getattr(result, "error", None):
                                soft_error = str(result.error)

                            if soft_error:
                                self.registry.record_execution(
                                    function_name, success=False,
                                    execution_time=duration_ms / 1000, error=soft_error,
                                )
                                logger.warning(
                                    f"Skill '{function_name}' returned a response with error field set: {soft_error}"
                                )
                                error_msg = soft_error
                            else:
                                self.registry.record_execution(
                                    function_name, success=True, execution_time=duration_ms / 1000
                                )
                                success = True
                                result_obj = result if isinstance(result, BaseModel) else result_obj
                                if function_name not in skills_used:
                                    skills_used.append(function_name)
                        except Exception as e:
                            duration_ms = (time.monotonic() - start_time) * 1000
                            error_msg = str(e)
                            self.registry.record_execution(
                                function_name, success=False,
                                execution_time=duration_ms / 1000, error=str(e),
                            )
                            logger.error(f"Skill '{function_name}' execution failed: {e}")

                        if trace:
                            trace.add_step(
                                "tool", function_name, duration_ms,
                                success=success, error=error_msg,
                            )
                        yield {
                            "type": "tool_result", "name": function_name,
                            "success": success, "duration_ms": round(duration_ms, 1),
                            "error": error_msg,
                        }

                        # ---- Self-healing ----
                        if not success and self.config.auto_repair:
                            await self._maybe_repair_skill(function_name, error_msg or "unknown error")

                        # Feed the tool result back so the LLM can continue.
                        if success:
                            tool_content = (
                                result.model_dump_json(indent=2)
                                if isinstance(result, BaseModel) else str(result)
                            )
                            last_tool_content = tool_content
                        else:
                            tool_content = f"The skill '{function_name}' failed with error: {error_msg}"
                        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_content})
                    else:
                        logger.error(f"Skill '{function_name}' was requested by LLM but not found in registered skills.")
                        messages.append({
                            "role": "tool", "tool_call_id": tool_call.id,
                            "content": f"Error: tool '{function_name}' does not exist. Available tools: {', '.join(list(self.skills) + ['request_new_skill'])}",
                        })

                if step == max_steps:
                    # Step budget exhausted: surface the best answer we have.
                    if result_obj is not None:
                        final_text = (
                            result_obj.model_dump_json(indent=2)
                            if isinstance(result_obj, BaseModel) else str(result_obj)
                        )
                    elif last_tool_content:
                        final_text = last_tool_content
                    else:
                        final_text = message.content or "Reached the maximum number of reasoning steps without a final answer."
                    final_type = "max_steps"

            self.last_skills_used = skills_used
            yield {"type": "final", "text": final_text, "result": result_obj, "skills_used": skills_used}
            if session_id:
                self.memory.add_message(session_id, "assistant", final_text)

        finally:
            if trace is not None:
                self.tracer.write(trace, final_type=final_type)

    async def _maybe_repair_skill(self, skill_name: str, error: str) -> None:
        """Trigger a ratchet-gated LLM repair once a skill accumulates
        ``auto_repair_threshold`` consecutive failures."""
        if not self.config.auto_repair:
            return
        stats = self.registry.get_stats(skill_name)
        if not stats:
            return
        consecutive = stats.get("consecutive_failures", 0)
        if consecutive < self.config.auto_repair_threshold:
            return
        logger.warning(
            f"Router: skill '{skill_name}' failed {consecutive} times in a row; triggering auto-repair."
        )
        # Reset the counter first so a failing repair does not re-trigger on
        # every subsequent call (the next repair needs a fresh failure run).
        self.registry.reset_failures(skill_name)
        try:
            repaired = await self.skill_creator.repair_skill(skill_name, error=error)
        except Exception as e:
            logger.error(f"Router: auto-repair of '{skill_name}' crashed: {e}")
            return
        if repaired:
            self._discover_skills()
            logger.info(f"Router: skill '{skill_name}' was repaired and reloaded.")

    async def process_query(self, user_query: str, is_retry: bool = False,
                            session_id: Optional[str] = None) -> Union[str, BaseModel]:
        """
        Resolve a user query through the agent loop and return the outcome:
        the final natural-language answer (str), or the skill's Pydantic
        result when running in legacy single-shot mode (``max_steps=1``).

        Args:
            user_query: The user's natural language query.
            is_retry: Deprecated; retained for API compatibility. The agent
                      loop has no separate retry path — meta-evolution is a
                      regular step inside the loop.
            session_id: Optional conversation id for memory.
        """
        final_text = ""
        result_obj: Optional[BaseModel] = None
        async for event in self.process_query_events(user_query, session_id=session_id):
            if event["type"] == "final":
                final_text = event["text"]
                result_obj = event.get("result")
        # Legacy contract: with max_steps == 1 the skill's structured result is
        # returned directly (matching the original single-shot router).
        if self.config.max_steps <= 1 and result_obj is not None:
            return result_obj
        return final_text

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
