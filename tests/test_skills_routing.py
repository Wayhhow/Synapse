import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from router.router import SkillRouter
from skills.weather_skill import WeatherResponse

@pytest.fixture
def router():
    # Pass a dummy API key so the initialization doesn't fail if no .env exists
    return SkillRouter(api_key="test-api-key")

def test_auto_discovery(router):
    # Verify that the router successfully discovered the weather skill
    assert "weather_skill" in router.skills

    # Verify the translation skill is no longer present since mock_skills was deleted
    assert "translation_skill" not in router.skills

@pytest.mark.asyncio
async def test_weather_skill_execution(router):
    # Test routing to weather skill
    skill = router.route("What is the weather like in Seattle today?")
    assert skill is not None
    assert skill.name == "weather_skill"

    # Test executing the skill with valid arguments as a dict/kwargs
    input_kwargs = {"location": "Seattle", "date": "today"}
    result = await skill.execute(**input_kwargs)

    # Verify the result is of the correct Pydantic model type
    assert isinstance(result, WeatherResponse)

    # Verify the contents
    assert result.location == "Seattle"
    assert result.weather == "Sunny"
    assert result.temperature == 25.0

    # Test executing the skill with different optional argument
    input_kwargs_tomorrow = {"location": "Seattle", "date": "tomorrow"}
    result2 = await skill.execute(**input_kwargs_tomorrow)

    assert isinstance(result2, WeatherResponse)
    assert result2.location == "Seattle"
    assert result2.weather == "Cloudy"
    assert result2.temperature == 25.0

def test_missing_skill(router):
    skill = router.route("Do something completely unrelated like calculate gravity")
    assert skill is None

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_process_query_tool_call(mock_create, router):
    # Mock the LLM returning a tool call
    mock_message = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "weather_skill"
    mock_tool_call.function.arguments = json.dumps({"location": "San Francisco", "date": "today"})
    mock_message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    result = await router.process_query("What is the weather in San Francisco?")

    # Verify the LLM was called
    mock_create.assert_called_once()

    # Verify the skill was executed and returned the expected Pydantic model
    assert isinstance(result, WeatherResponse)
    assert result.location == "San Francisco"
    assert result.weather == "Sunny"

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_process_query_text_response(mock_create, router):
    # Mock the LLM returning normal text (no tool call)
    mock_message = MagicMock()
    mock_message.tool_calls = None
    mock_message.content = "I'm just a simple routing agent, but hello there!"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    result = await router.process_query("Hello, how are you?")

    # Verify the LLM was called
    mock_create.assert_called_once()

    # Verify it just returns the text string
    assert isinstance(result, str)
    assert result == "I'm just a simple routing agent, but hello there!"
