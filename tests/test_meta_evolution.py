import pytest
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock
from core.skill_registry import SkillRegistry
from meta.skill_creator import SkillCreator

@pytest.fixture
def skill_creator(tmpdir):
    # Use a temporary directory for skills AND a temp registry so we don't
    # pollute the shared data/skill_registry.json (which is also used by the
    # live SkillRouter and surfaced via GET /stats).
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    return SkillCreator(
        skills_dir=str(tmpdir),
        api_key="test-api-key",
        registry=registry,
    )

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_generate_skill_success(mock_create, skill_creator, tmpdir):
    # Mock LLM returning a valid JSON string conforming to GeneratedSkill
    mock_json = json.dumps({
        "filename": "test_math_skill.py",
        "class_name": "TestMathSkill",
        "code": "from pydantic import BaseModel\nfrom core.base import BaseSkill\nclass MathArgs(BaseModel):\n    a: int\nclass MathResp(BaseModel):\n    result: int\nclass TestMathSkill(BaseSkill):\n    @property\n    def name(self): return 'math'\n    @property\n    def description(self): return 'test'\n    @property\n    def expected_args(self): return MathArgs\n    @property\n    def expected_response_type(self): return MathResp\n    async def execute(self, **kwargs): return MathResp(result=kwargs['a'])"
    })

    mock_message = MagicMock()
    mock_message.content = mock_json
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    result = await skill_creator.generate_skill(intent="Add two numbers")

    assert result is True

    # Verify the file was created in the temp directory
    filepath = os.path.join(str(tmpdir), "test_math_skill.py")
    assert os.path.exists(filepath)

    with open(filepath, 'r') as f:
        content = f.read()
        assert "class TestMathSkill(BaseSkill):" in content

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_generate_skill_syntax_error(mock_create, skill_creator, tmpdir):
    # Mock LLM returning code with a syntax error
    mock_json = json.dumps({
        "filename": "bad_skill.py",
        "class_name": "BadSkill",
        "code": "def bad_function() # missing colon\n    pass"
    })

    mock_message = MagicMock()
    mock_message.content = mock_json
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    result = await skill_creator.generate_skill(intent="Do something bad")

    # Should fail AST validation
    assert result is False

    # Verify file was NOT created
    filepath = os.path.join(str(tmpdir), "bad_skill.py")
    assert not os.path.exists(filepath)


@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_generate_skill_ratchet_rollback_on_lower_quality(mock_create, skill_creator, tmpdir):
    """
    Ratchet mechanism: when a new version of an existing skill has LOWER code
    quality than the old version, the new file must be rejected and the old
    content restored.
    """
    skill_filename = "ratchet_skill.py"
    filepath = os.path.join(str(tmpdir), skill_filename)

    # Old version: complete, clean code (structure 20 + antipattern 15 = 35)
    old_code = (
        "# OLD_VERSION_MARKER\n"
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class RatchetSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'ratchet_skill'\n"
        "    @property\n"
        "    def description(self): return 'ratchet test'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='clean')\n"
    )
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(old_code)

    # New version: still loadable (all 5 members) but contains an antipattern
    # `eval(` -> structure 20 + antipattern 10 = 30 < 35 -> ratchet must roll back.
    new_code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class RatchetSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'ratchet_skill'\n"
        "    @property\n"
        "    def description(self): return 'ratchet test'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        x = eval('1+1')\n"
        "        return XResp(result=str(x))\n"
    )

    mock_json = json.dumps({
        "filename": skill_filename,
        "class_name": "RatchetSkill",
        "code": new_code,
    })
    mock_message = MagicMock()
    mock_message.content = mock_json
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    result = await skill_creator.generate_skill(intent="ratchet test")

    # Ratchet rejected the lower-quality new version
    assert result is False

    # Old content restored
    with open(filepath, "r", encoding="utf-8") as f:
        restored = f.read()
    assert "OLD_VERSION_MARKER" in restored
    assert "eval(" not in restored


def test_skill_creator_fixture_uses_isolated_registry(skill_creator, tmpdir):
    """Regression guard: the skill_creator fixture must use a temp registry so
    test runs do not pollute the shared data/skill_registry.json (which is
    surfaced via GET /stats and would otherwise accumulate stale entries like
    'test_math_skill', 'ratchet_skill', etc.)."""
    # The fixture's registry must persist to the tmpdir, not the project's data dir
    assert skill_creator.registry.persist_path.startswith(str(tmpdir))
    assert "data/skill_registry.json" not in skill_creator.registry.persist_path
    # And the temp registry file path is under tmpdir
    assert os.path.dirname(skill_creator.registry.persist_path) == str(tmpdir)
