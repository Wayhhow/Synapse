import pytest
import os
import json
from unittest.mock import patch, MagicMock, AsyncMock
from meta.skill_creator import SkillCreator

@pytest.fixture
def skill_creator(tmpdir):
    # Use a temporary directory for skills so we don't pollute the actual project
    return SkillCreator(skills_dir=str(tmpdir), api_key="test-api-key")

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
