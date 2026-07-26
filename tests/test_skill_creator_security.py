"""
Regression coverage for the security gates in ``meta.skill_creator.SkillCreator``.

Covers:
- Bug-1: top-level safety check rejects code that calls functions at module
  top level (e.g. `import os; os.system("rm -rf /")`) BEFORE the module is
  loaded via `exec_module`. The check must run before any file write so a
  rejected generation never touches the filesystem.
- Bug-28: AST-based antipattern detection catches `eval`/`exec`/`os.system`
  etc. even when obfuscated (e.g. whitespace, indented calls).
- Bug-10: when an existing skill's description has high keyword overlap with
  the requested intent, generation is skipped (no duplicate skill).
"""
import json
import os
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from core.skill_registry import SkillRegistry
from meta.skill_creator import SkillCreator


@pytest.fixture
def skill_creator(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    return SkillCreator(
        skills_dir=str(tmpdir),
        api_key="test-api-key",
        registry=registry,
    )


def _mock_llm_returning(code: str, filename: str = "x_skill.py", class_name: str = "XSkill"):
    mock_json = json.dumps({
        "filename": filename,
        "class_name": class_name,
        "code": code,
    })
    mock_message = MagicMock()
    mock_message.content = mock_json
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    return AsyncMock(return_value=mock_response)


# --- Bug-1: top-level safety check ---

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b01_top_level_os_system_rejected(mock_create, skill_creator, tmpdir):
    """
    Bug-1 regression: a generated skill whose top level calls os.system
    must be rejected and never written to disk.
    """
    malicious_code = (
        "import os\n"
        "os.system('echo pwned')\n"  # top-level Call → must be rejected
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(malicious_code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is False

    # File must NOT exist (the rejection happens before the write step).
    filepath = os.path.join(str(tmpdir), "x_skill.py")
    assert not os.path.exists(filepath)


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b01_top_level_print_call_rejected(mock_create, skill_creator, tmpdir):
    """
    Bug-1 regression: even a benign top-level call like `print("hi")` is
    rejected — the rule is "no calls at module top level" because we cannot
    statically prove they are safe before loading.
    """
    code = (
        "print('hello at import time')\n"
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is False
    assert not os.path.exists(os.path.join(str(tmpdir), "x_skill.py"))


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b01_top_level_assignment_with_call_rejected(mock_create, skill_creator, tmpdir):
    """
    Bug-1 regression: `x = os.system('rm -rf /')` is a top-level Assign
    whose value contains a Call. Must be rejected.
    """
    code = (
        "import os\n"
        "_ = os.system('echo hi')\n"  # Assign with Call in value
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is False


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b01_clean_top_level_passes_safety_gate(mock_create, skill_creator, tmpdir):
    """
    A clean skill file (only imports, class defs, and a module docstring)
    passes the top-level safety check and is written to disk.
    """
    clean_code = (
        '"""Module docstring is allowed."""\n'
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "ALLOWED_CONST = 42  # plain assignment, no call\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(clean_code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is True
    assert os.path.exists(os.path.join(str(tmpdir), "x_skill.py"))


# --- Bug-28: AST-based antipattern detection ---

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b28_three_dangerous_calls_rejected(mock_create, skill_creator, tmpdir):
    """
    Bug-28 regression: 3+ dangerous calls (eval+exec+os.system) at function
    body level must be rejected by the AST scan even though they're inside a
    function (the substring matcher would have flagged these too, but the
    AST check is the modern path).
    """
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        eval('1')\n"
        "        exec('2')\n"
        "        import os\n"
        "        os.system('3')\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is False


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b28_obfuscated_eval_caught_by_ast(mock_create, skill_creator, tmpdir):
    """
    Bug-28 regression: a single `eval('1')` is not enough to reject (only
    deducts 5 of 15 antipattern points). But the AST scan still detects it
    for scoring purposes. Here we verify that 3+ obfuscated calls (which the
    old substring matcher would have missed due to extra whitespace) are
    caught by the AST walker.

    The 3 calls below are formatted with extra whitespace, which the old
    substring `eval(` would have missed:
      eval  ("1")
      exec  ("2")
      compile  ("3", "<s>", "exec")
    """
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        eval  ('1')\n"
        "        exec  ('2')\n"
        "        compile  ('3', '<s>', 'exec')\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    result = await skill_creator.generate_skill(intent="do something")
    assert result is False


# --- Bug-10: similar-skill detection ---

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b10_similar_skill_skips_generation(mock_create, skill_creator, tmpdir):
    """
    Bug-10 regression: when the registry already contains a skill whose
    description has high keyword overlap with the requested intent, the
    generator must skip and return False (no duplicate skill written).
    """
    # Pre-populate the registry with a similar-sounding description.
    skill_creator.registry.register(
        "weather_skill",
        "Get the current weather for a specific location. Trigger words: weather, temperature, forecast, 天气, 温度",
    )

    # The LLM would have generated a new weather skill — but we should
    # never even reach the write step.
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    # Intent has high overlap with the registered description.
    result = await skill_creator.generate_skill(intent="weather temperature forecast for location")
    assert result is False
    # LLM was called but file was never written.
    assert not os.path.exists(os.path.join(str(tmpdir), "x_skill.py"))


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_b10_unrelated_intent_still_generates(mock_create, skill_creator, tmpdir):
    """
    Bug-10 negative case: when no similar skill exists, generation proceeds
    normally.
    """
    skill_creator.registry.register(
        "weather_skill",
        "Get the current weather for a specific location.",
    )

    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    mock_create.side_effect = _mock_llm_returning(code)

    # Intent is completely unrelated to weather — should generate.
    result = await skill_creator.generate_skill(intent="play heavy metal music")
    assert result is True
