"""
Self-healing tests: consecutive-failure tracking in the registry, the router's
auto-repair trigger, and the ratchet-gated ``SkillCreator.repair_skill``
(Voyager-style execution-feedback loop).
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.skill_registry import SkillRegistry
from core.memory import Memory
from meta.skill_creator import SkillCreator
from router.router import SkillRouter
from core.config import SynapseConfig

VALID_SKILL_CODE = (
    "from pydantic import BaseModel\n"
    "from core.base import BaseSkill\n"
    "class A(BaseModel):\n"
    "    x: int = 1\n"
    "class R(BaseModel):\n"
    "    result: str\n"
    "    error: str = ''\n"
    "class FixSkill(BaseSkill):\n"
    "    @property\n"
    "    def name(self): return 'fix_skill'\n"
    "    @property\n"
    "    def description(self): return 'repair target'\n"
    "    @property\n"
    "    def expected_args(self): return A\n"
    "    @property\n"
    "    def expected_response_type(self): return R\n"
    "    async def execute(self, **kwargs):\n"
    "        return R(result='fixed')\n"
)


def _mock_llm_json(code, filename="fix_skill.py", class_name="FixSkill"):
    message = MagicMock()
    message.content = json.dumps({"filename": filename, "class_name": class_name, "code": code})
    return MagicMock(choices=[MagicMock(message=message)])


# ---------------------------------------------------------------------------
# Registry: consecutive failure tracking
# ---------------------------------------------------------------------------

def test_consecutive_failures_accumulate_and_reset(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    for i in range(3):
        registry.record_execution("s", success=False, error=f"e{i}")
    assert registry.get_stats("s")["consecutive_failures"] == 3
    registry.record_execution("s", success=True)
    assert registry.get_stats("s")["consecutive_failures"] == 0
    registry.record_execution("s", success=False, error="x")
    assert registry.get_stats("s")["consecutive_failures"] == 1


def test_reset_failures_persists(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    registry.record_execution("s", success=False, error="e")
    registry.record_execution("s", success=False, error="e")
    registry.reset_failures("s")
    # Reload from disk to prove persistence
    registry2 = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    assert registry2.get_stats("s")["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# Router: auto-repair trigger
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_repair_triggers_at_threshold(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(auto_repair=True, auto_repair_threshold=3, trace_enabled=False)
    router = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    router.memory = Memory(max_history=10)

    for i in range(2):
        registry.record_execution("weather_skill", success=False, error="e")
    with patch.object(router.skill_creator, "repair_skill", new_callable=AsyncMock) as repair:
        await router._maybe_repair_skill("weather_skill", "e2")
        repair.assert_not_awaited()  # threshold not reached

    registry.record_execution("weather_skill", success=False, error="e3")
    with patch.object(router.skill_creator, "repair_skill", new_callable=AsyncMock, return_value=True) as repair, \
         patch.object(router, "_discover_skills", MagicMock()) as discover:
        await router._maybe_repair_skill("weather_skill", "e3")
        repair.assert_awaited_once()
        discover.assert_called_once()

    # Counter was reset so the next trigger needs a fresh failure run
    assert registry.get_stats("weather_skill")["consecutive_failures"] == 0


@pytest.mark.asyncio
async def test_auto_repair_disabled_via_config(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(auto_repair=False, auto_repair_threshold=1, trace_enabled=False)
    router = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    router.memory = Memory(max_history=10)
    registry.record_execution("weather_skill", success=False, error="e")
    with patch.object(router.skill_creator, "repair_skill", new_callable=AsyncMock) as repair:
        await router._maybe_repair_skill("weather_skill", "e")
        repair.assert_not_awaited()


# ---------------------------------------------------------------------------
# SkillCreator.repair_skill
# ---------------------------------------------------------------------------

@pytest.fixture
def skill_creator_with_broken_skill(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    skills_dir = os.path.join(str(tmpdir), "skills")
    os.makedirs(skills_dir, exist_ok=True)
    broken_code = VALID_SKILL_CODE.replace("return R(result='fixed')", "return R(result=1/0)")
    with open(os.path.join(skills_dir, "fix_skill.py"), "w", encoding="utf-8") as f:
        f.write(broken_code)
    creator = SkillCreator(skills_dir=skills_dir, api_key="test-key", registry=registry)
    return creator, skills_dir, broken_code


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_repair_skill_replaces_broken_code(mock_create, skill_creator_with_broken_skill):
    creator, skills_dir, broken_code = skill_creator_with_broken_skill
    mock_create.return_value = _mock_llm_json(VALID_SKILL_CODE)

    ok = await creator.repair_skill("fix_skill", error="ZeroDivisionError: division by zero")

    assert ok is True
    with open(os.path.join(skills_dir, "fix_skill.py"), "r", encoding="utf-8") as f:
        new_code = f.read()
    assert "1/0" not in new_code
    assert "return R(result='fixed')" in new_code
    # The broken version was archived, not destroyed
    archive_root = os.path.join(skills_dir, ".archive")
    archived = []
    for root, _, files in os.walk(archive_root):
        for name in files:
            archived.append(open(os.path.join(root, name), encoding="utf-8").read())
    assert any("1/0" in code for code in archived)


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_repair_skill_ratchet_rejects_worse_code(mock_create, skill_creator_with_broken_skill):
    creator, skills_dir, broken_code = skill_creator_with_broken_skill
    # "Repaired" code that is actually worse: strips required members
    worse_code = "from core.base import BaseSkill\nclass FixSkill(BaseSkill):\n    pass\n"
    mock_create.return_value = _mock_llm_json(worse_code)

    ok = await creator.repair_skill("fix_skill", error="anything")

    assert ok is False
    with open(os.path.join(skills_dir, "fix_skill.py"), "r", encoding="utf-8") as f:
        assert f.read() == broken_code  # untouched


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_repair_skill_rolls_back_on_load_failure(mock_create, skill_creator_with_broken_skill):
    creator, skills_dir, broken_code = skill_creator_with_broken_skill
    # Code that passes all AST gates but raises NameError during import
    # (a class-body assignment referencing an undefined name).
    load_bomb = VALID_SKILL_CODE.replace(
        "class FixSkill(BaseSkill):\n",
        "class FixSkill(BaseSkill):\n    broken_attr = undefined_name\n",
    )
    mock_create.return_value = _mock_llm_json(load_bomb)

    ok = await creator.repair_skill("fix_skill", error="x")

    assert ok is False
    with open(os.path.join(skills_dir, "fix_skill.py"), "r", encoding="utf-8") as f:
        assert f.read() == broken_code


@pytest.mark.asyncio
async def test_repair_unknown_skill_returns_false(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    creator = SkillCreator(skills_dir=str(tmpdir), api_key="test-key", registry=registry)
    assert await creator.repair_skill("nope", error="e") is False


# ---------------------------------------------------------------------------
# SkillCreator.generate_skill: Voyager-style validation feedback loop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_generate_skill_recovers_after_first_bad_attempt(mock_create, tmpdir):
    """Round 1 returns broken code; round 2 (fed the validation errors)
    returns valid code and the skill is created — the core Voyager loop."""
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    creator = SkillCreator(skills_dir=str(tmpdir), api_key="test-key", registry=registry)

    bad_code = "def broken(:\n    pass"
    good_code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class A(BaseModel):\n"
        "    x: int = 1\n"
        "class R(BaseModel):\n"
        "    result: str\n"
        "class VoyagerSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'voyager_skill'\n"
        "    @property\n"
        "    def description(self): return 'test'\n"
        "    @property\n"
        "    def expected_args(self): return A\n"
        "    @property\n"
        "    def expected_response_type(self): return R\n"
        "    async def execute(self, **kwargs):\n"
        "        return R(result='ok')\n"
    )

    mock_create.side_effect = [
        _mock_llm_json(bad_code),
        _mock_llm_json(good_code),
    ]

    ok = await creator.generate_skill(intent="voyager test")
    assert ok is True
    assert mock_create.call_count == 2
    # The second prompt must contain the feedback from the first failure
    second_prompt = mock_create.call_args_list[1].kwargs["messages"][1]["content"]
    assert "rejected" in second_prompt or "SyntaxError" in second_prompt
    assert os.path.isfile(os.path.join(str(tmpdir), "fix_skill.py"))


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_generate_skill_exhausts_attempts_on_persistent_bad_code(mock_create, tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    creator = SkillCreator(skills_dir=str(tmpdir), api_key="test-key", registry=registry)
    bad_code = "def broken(:\n    pass"
    mock_create.return_value = _mock_llm_json(bad_code)

    ok = await creator.generate_skill(intent="hopeless")
    assert ok is False
    assert mock_create.call_count == creator.config.generate_max_attempts


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_unsafe_filename_is_sanitized_not_rejected(mock_create, tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    creator = SkillCreator(skills_dir=str(tmpdir), api_key="test-key", registry=registry)
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class A(BaseModel):\n"
        "    x: int = 1\n"
        "class R(BaseModel):\n"
        "    result: str\n"
        "class SafeNameSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'safe_name'\n"
        "    @property\n"
        "    def description(self): return 'test'\n"
        "    @property\n"
        "    def expected_args(self): return A\n"
        "    @property\n"
        "    def expected_response_type(self): return R\n"
        "    async def execute(self, **kwargs):\n"
        "        return R(result='ok')\n"
    )
    payload = json.loads(_mock_llm_json(code).choices[0].message.content)
    payload["filename"] = "../../evil_skill.py"
    message = MagicMock()
    message.content = json.dumps(payload)
    mock_create.return_value = MagicMock(choices=[MagicMock(message=message)])

    ok = await creator.generate_skill(intent="filename test")
    assert ok is True
    # Path traversal is stripped to a safe basename; nothing escapes the dir.
    files = [f for f in os.listdir(str(tmpdir)) if f.endswith(".py")]
    assert files == ["evil_skill.py"]
