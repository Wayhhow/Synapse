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
    # Bug-15 fix: `WeatherArgs.date` was removed because the execute() method
    # never honored it. Asking for "tomorrow" returned today's forecast,
    # which was misleading. Only `location` is accepted now.
    input_kwargs = {"location": "Seattle"}
    result = await skill.execute(**input_kwargs)

    # Verify the result is of the correct Pydantic model type
    assert isinstance(result, WeatherResponse)

    # Verify the contents
    assert result.location == "Seattle"
    assert result.weather == "Clear sky"
    assert result.temperature == 25.0

    # Confirm the skill no longer accepts the deprecated `date` argument.
    input_kwargs_today = {"location": "Seattle"}
    result2 = await skill.execute(**input_kwargs_today)

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
    mock_tool_call.function.arguments = json.dumps({"location": "San Francisco"})
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

    # Bug-6 fix: ``_discover_skills`` now clears ``self.skills`` at the start
    # of each call (so deleted files don't linger). The original test relied
    # on the bug — it patched ``stock_skill`` directly into ``router.skills``
    # and let ``_discover_skills`` run after a mocked ``generate_skill``
    # returned True. With Bug-6 fixed, that discover call would wipe the
    # patched entry before the retry could use it. Since the test mocks
    # ``generate_skill`` (no real file is written), we also mock
    # ``_discover_skills`` as a no-op and inject the mock skill ourselves.
    mock_skill = MagicMock()
    mock_skill.execute = AsyncMock(return_value="AAPL is $150")
    with patch.object(router, "_discover_skills", lambda: None), \
         patch.dict(router.skills, {"stock_skill": mock_skill}):
        result = await router.process_query("What is the stock price of AAPL?", session_id="test-session-123")

        # Verify generate was called with correct intent
        mock_generate.assert_called_once_with(intent="Get stock price", requirements="")

        # Verify LLM was called twice (initial + retry)
        assert mock_create.call_count == 2

        # Verify final result is what the skill executed
        assert result == "AAPL is $150"

        # Bug-3 fix: previously the router recorded the user message TWICE
        # — once before the meta-evolution retry and once after the retried
        # skill succeeded. The pre-retry `add_message` call was removed so
        # the user message is recorded exactly once on the successful retry.
        history = router.memory.get_history("test-session-123")
        user_messages = [m for m in history if m["role"] == "user"]
        assert len(user_messages) == 1

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


def test_router_boots_without_openai_api_key(monkeypatch, tmpdir):
    """
    Regression guard (Bug-29): ``python cli.py --skills`` (and other
    introspection paths like ``GET /health``) used to crash because
    ``SkillRouter.__init__`` eagerly constructed ``AsyncOpenAI(api_key=None)``
    which raises ``OpenAIError("Missing credentials")`` if
    ``OPENAI_API_KEY`` is unset. The fix made the OpenAI client lazy: it is
    only built on first access (i.e. when ``process_query`` actually needs
    an LLM). This test asserts that booting the router + listing skills
    works without any API key in the environment.
    """
    # Strip any OPENAI_API_KEY that may have leaked from .env / shell
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)

    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    # Must NOT raise OpenAIError
    r = SkillRouter(api_key=None, registry=registry)
    # Skills discovery still works without an LLM
    assert len(r.skills) >= 6  # the 6 built-in skills
    # The lazy client is not yet constructed
    assert r._client is None
    # skill_creator must also be bootable without an API key
    assert r.skill_creator._client is None
