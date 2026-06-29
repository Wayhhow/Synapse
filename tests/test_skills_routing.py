import pytest
import json
import os
from unittest.mock import patch, MagicMock, AsyncMock
from router.router import SkillRouter
from core.memory import Memory
from core.skill_registry import SkillRegistry
from skills.weather_skill import WeatherResponse

@pytest.fixture
def router(tmpdir):
    # Pass a dummy API key so the initialization doesn't fail if no .env exists.
    # Use a temp registry + in-memory memory so tests never pollute the shared
    # data/skill_registry.json (which is surfaced via GET /stats). Mock skills
    # injected via patch.dict() get auto-registered through record_execution,
    # so isolation is mandatory.
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    r = SkillRouter(api_key="test-api-key", registry=registry)
    # Disable sandbox for testing (mocks can't be pickled for multiprocessing)
    r.sandbox = None
    # Use an in-memory Memory (no persist_path) for test isolation
    r.memory = Memory(max_history=10)
    return r

def test_auto_discovery(router):
    # Verify that the router successfully discovered the weather skill
    assert "weather_skill" in router.skills

    # Verify all 6 skills are discovered
    assert "weather_skill" in router.skills
    assert "web_search_skill" in router.skills
    assert "data_analysis_skill" in router.skills
    assert "calculator_skill" in router.skills
    assert "translation_skill" in router.skills
    assert "news_skill" in router.skills

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_weather_skill_execution(mock_get, router):
    # Test routing to weather skill
    skill = router.route("What is the weather like in Seattle today?")
    assert skill is not None
    assert skill.name == "weather_skill"

    # Setup mock responses for geocoding and weather API calls
    def mock_response_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        if "geocoding-api.open-meteo.com" in url:
            mock_resp.json.return_value = {
                "results": [
                    {
                        "name": "Seattle",
                        "latitude": 47.6062,
                        "longitude": -122.3321,
                    }
                ]
            }
        elif "api.open-meteo.com" in url:
            mock_resp.json.return_value = {
                "current_weather": {
                    "temperature": 25.0,
                    "weathercode": 0,
                }
            }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_get.side_effect = mock_response_side_effect

    # Test executing the skill with valid arguments as a dict/kwargs
    input_kwargs = {"location": "Seattle", "date": "today"}
    result = await skill.execute(**input_kwargs)

    # Verify the result is of the correct Pydantic model type
    assert isinstance(result, WeatherResponse)

    # Verify the contents
    assert result.location == "Seattle"
    assert result.weather == "Clear sky"
    assert result.temperature == 25.0

    # Test executing the skill with different optional argument
    input_kwargs_tomorrow = {"location": "Seattle", "date": "tomorrow"}
    result2 = await skill.execute(**input_kwargs_tomorrow)

    assert isinstance(result2, WeatherResponse)
    assert result2.location == "Seattle"
    assert result2.weather == "Clear sky"
    assert result2.temperature == 25.0

def test_missing_skill(router):
    skill = router.route("Do something completely unrelated like juggling flamingos")
    assert skill is None

@pytest.mark.asyncio
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
async def test_process_query_tool_call(mock_create, mock_get, router):
    # Mock the LLM returning a tool call
    mock_message = MagicMock()
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "weather_skill"
    mock_tool_call.function.arguments = json.dumps({"location": "San Francisco", "date": "today"})
    mock_message.tool_calls = [mock_tool_call]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=mock_message)]
    mock_create.return_value = mock_response

    # Mock HTTP responses for the weather skill
    def mock_response_side_effect(url, **kwargs):
        mock_resp = MagicMock()
        if "geocoding-api.open-meteo.com" in url:
            mock_resp.json.return_value = {
                "results": [
                    {
                        "name": "San Francisco",
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                    }
                ]
            }
        elif "api.open-meteo.com" in url:
            mock_resp.json.return_value = {
                "current_weather": {
                    "temperature": 22.0,
                    "weathercode": 1,
                }
            }
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_get.side_effect = mock_response_side_effect

    result = await router.process_query("What is the weather in San Francisco?")

    # Verify the LLM was called
    mock_create.assert_called_once()

    # Verify the skill was executed and returned the expected Pydantic model
    assert isinstance(result, WeatherResponse)
    assert result.location == "San Francisco"
    assert result.weather == "Mainly clear"

@pytest.mark.asyncio
@patch('openai.resources.chat.completions.AsyncCompletions.create', new_callable=AsyncMock)
@patch('meta.skill_creator.SkillCreator.generate_skill', new_callable=AsyncMock)
async def test_process_query_meta_evolution(mock_generate, mock_create, router):
    # Setup LLM to first request a new skill, then on retry, route to the newly generated skill

    # First call: LLM calls request_new_skill
    mock_msg1 = MagicMock()
    mock_tc1 = MagicMock()
    mock_tc1.function.name = "request_new_skill"
    mock_tc1.function.arguments = json.dumps({"intent": "Get stock price"})
    mock_msg1.tool_calls = [mock_tc1]

    # Second call (Retry): LLM calls the new skill
    mock_msg2 = MagicMock()
    mock_tc2 = MagicMock()
    mock_tc2.function.name = "stock_skill" # Pretend it was created and loaded
    mock_tc2.function.arguments = json.dumps({"symbol": "AAPL"})
    mock_msg2.tool_calls = [mock_tc2]

    mock_create.side_effect = [
        MagicMock(choices=[MagicMock(message=mock_msg1)]),
        MagicMock(choices=[MagicMock(message=mock_msg2)])
    ]

    # Mock the generator succeeding
    mock_generate.return_value = True

    # We need to mock the router's execution of the new skill since it doesn't really exist in the dict
    with patch.dict(router.skills, {"stock_skill": MagicMock(execute=AsyncMock(return_value="AAPL is $150"))}):
        result = await router.process_query("What is the stock price of AAPL?", session_id="test-session-123")

        # Verify generate was called with correct intent
        mock_generate.assert_called_once_with(intent="Get stock price", requirements="")

        # Verify LLM was called twice (initial + retry)
        assert mock_create.call_count == 2

        # Verify final result is what the skill executed
        assert result == "AAPL is $150"

        # Verify both the original request and the retry request were recorded as user messages
        history = router.memory.get_history("test-session-123")
        user_messages = [m for m in history if m["role"] == "user"]
        assert len(user_messages) == 2

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


def test_router_fixture_uses_isolated_registry(router, tmpdir):
    """Regression guard: the router fixture must use a temp registry so test
    runs never pollute the shared data/skill_registry.json. Before this fix,
    test_process_query_meta_evolution leaked a 'stock_skill' entry into the
    shared file because record_execution auto-registers unknown skills."""
    # The fixture's registry must persist to tmpdir, not the project data dir
    assert router.registry.persist_path.startswith(str(tmpdir))
    assert "data/skill_registry.json" not in router.registry.persist_path
    # And memory must be in-memory (no persist_path leaking to data/memory.json)
    assert router.memory.persist_path is None
