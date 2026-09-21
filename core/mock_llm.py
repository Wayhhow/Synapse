"""Zero-cost demo mode: a deterministic mock LLM for Synapse.

Activating it (``SYNAPSE_DEMO_MOCK_LLM=1`` or ``python cli.py --demo``)
monkey-patches the OpenAI SDK's chat-completion call so the **entire agent
loop runs without an API key and without burning a single token** — the same
trick the test suite uses, promoted into a first-class feature.

Routing is keyword-based over the live skill registry (name + description),
so runtime-generated skills work too. Queries that match nothing trigger the
``request_new_skill`` path, letting you watch Meta-Evolution fire in the
CLI/Web UI; generation itself is stubbed (writing new code requires a real
LLM) and the honest failure event feeds back into the loop.

Design goals:

* **Zero new dependencies** — plain ``SimpleNamespace`` objects that quack
  like the OpenAI SDK response (duck typing).
* **Zero behavioural drift** — the mock LLM emits exactly the tool-call
  shapes the loop expects; everything downstream is the real code path.
* **Opt-in only** — unless explicitly enabled nothing is patched, so
  production behaviour is unchanged.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

# Extra intents per built-in skill, on top of tokens mined from the skill's
# own name/description. Bilingual on purpose: the demo is often the first
# thing a Chinese-speaking visitor runs.
_EXTRA_KEYWORDS: Dict[str, List[str]] = {
    "weather_skill": ["weather", "forecast", "temperature", "天气", "气温", "下雨"],
    # Note: bare "计算" is deliberately omitted — it false-matches "量子计算"
    # (quantum computing) etc. In demo mode a *miss* is fine: it shows off
    # Meta-Evolution instead of calling the wrong skill.
    "calculator_skill": ["calculate", "compute", "math", "算一下", "等于"],
    "web_search_skill": ["search", "google", "lookup", "find", "搜索", "查一下", "查找"],
    "translation_skill": ["translate", "translation", "翻译"],
    "news_skill": ["news", "headline", "新闻", "头条"],
    "data_analysis_skill": ["analy", "statistics", "data", "average", "mean", "分析", "统计", "均值"],
}

# argument name -> callable(user_query) -> JSON-serialisable value
_DEFAULT_ARG_BUILDERS: Dict[str, Callable[[str], Any]] = {
    "location": lambda q: "Beijing",
    "expression": lambda q: "(2 + 3) * 4 ** 2",
    "query": lambda q: q,
    "text": lambda q: q,
    "numbers": lambda q: [23, 45, 12, 67, 34, 89, 56],
    "data": lambda q: [23, 45, 12, 67, 34, 89, 56],
}


def _completion(tool_calls: Optional[List[Tuple[str, str, str]]] = None,
                content: Optional[str] = None):
    """Build an OpenAI-shaped chat completion from simple tuples.

    ``tool_calls`` items are ``(id, name, arguments_json)``.
    """
    if tool_calls is not None:
        calls = [
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(name=name, arguments=args_json),
            )
            for call_id, name, args_json in tool_calls
        ]
        message = SimpleNamespace(role="assistant", content=None, tool_calls=calls)
    else:
        message = SimpleNamespace(role="assistant", content=content or "", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def _result_text(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "model_dump_json"):
        try:
            return value.model_dump_json()
        except Exception:
            pass
    return str(value)


class MockLLM:
    """Deterministic, keyword-routed mock LLM for demo mode."""

    def __init__(self, skills: Optional[Dict[str, Any]] = None):
        # ``skills`` may be attached after construction (the router discovers
        # them during its own __init__, after demo patching happens).
        self.skills = skills
        self._history: List[Dict[str, Any]] = []
        self._created = False
        self._attempts: Dict[str, int] = {}

    def _catalog(self) -> Dict[str, Any]:
        return self.skills if self.skills is not None else {}

    def _match_skill(self, query: str) -> Optional[str]:
        q = query.lower()
        best: Tuple[int, Optional[str]] = (0, None)
        for name, skill in self._catalog().items():
            score = 0
            desc = getattr(skill, "description", "") or ""
            for token in _EXTRA_KEYWORDS.get(name, []):
                if token.lower() in q:
                    score += 2
            for token in name.lower().replace("_skill", "").split("_"):
                if len(token) > 2 and token in q:
                    score += 1
            for word in desc.lower().replace("，", " ").replace("。", " ").split():
                if len(word) > 3 and word in q:
                    score += 1
            if score > best[0]:
                best = (score, name)
        return best[1]

    def _build_args(self, skill_name: str, query: str) -> str:
        skill = self._catalog().get(skill_name)
        model = getattr(skill, "expected_args", None)
        try:
            fields = list(model.model_fields.keys()) if model is not None else []
        except Exception:
            fields = []
        args = {f: _DEFAULT_ARG_BUILDERS.get(f, lambda q: q)(query) for f in fields}
        return json.dumps(args, ensure_ascii=False)


    # -- the fake completion -------------------------------------------------

    async def create(self, model: str, messages: List[Dict[str, Any]], **kwargs):
        # A new tool result arrived iff the conversation grew since the last
        # call and the newest message is a tool message.
        grew = len(messages) > len(self._history)
        last = messages[-1] if messages else {}
        if grew and last.get("role") == "tool":
            new_tools = [m for m in messages if m.get("role") == "tool"]
            self._history = list(messages)
            return self._after_tools(new_tools)
        self._history = list(messages)
        return self._first_turn(messages)

    def _last_user_query(self, messages: List[Dict[str, Any]]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                return m.get("content") or ""
        return ""

    def _first_turn(self, messages: List[Dict[str, Any]]):
        query = self._last_user_query(messages)

        if self._created and query:
            return _completion(content=(
                "（Mock LLM）这是一个演示回复。真实模式下我会基于刚才的技能结果组织自然语言回答。"
            ))

        skill_name = self._match_skill(query) if query else None
        if skill_name:
            self._attempts[skill_name] = self._attempts.get(skill_name, 0) + 1
            args_json = self._build_args(skill_name, query)
            return _completion(tool_calls=[("call_mock_1", skill_name, args_json)])

        if query:
            return _completion(tool_calls=[(
                "call_mock_meta", "request_new_skill",
                json.dumps({"intent": query[:60]}, ensure_ascii=False),
            )])
        return _completion(content="（Mock LLM）你好！试试问天气、计算、翻译、新闻或数据分析。")

    def _after_tools(self, tool_msgs: List[Dict[str, Any]]):
        joined = " ".join(str(m.get("content", "")) for m in tool_msgs)
        if "Meta-Evolution failed to generate" in joined or "Skill generated successfully" in joined:
            self._created = True
            return _completion(content=(
                "🧬 Meta-Evolution 已触发（演示模式不生成代码）：我识别到没有现成技能能处理这个请求，"
                "真实模式下现在会现场编写一个新的 Python 技能文件，经过语法/安全/棘轮验证后立即投入使用。"
            ))
        last = tool_msgs[-1]
        return _completion(content=(
            "（Mock LLM 演示回答）根据技能返回的结果：\n\n"
            f"{last.get('content', '')}\n\n"
            "配置 OPENAI_API_KEY 后，这里会替换为真实模型生成的自然语言回答。"
        ))

    # -- activation ----------------------------------------------------------

    def patch(self) -> None:
        """Monkey-patch the OpenAI SDK. Call once per process (idempotent)."""
        from openai.resources.chat.completions import AsyncCompletions

        AsyncCompletions.create = self.create  # type: ignore[assignment]

