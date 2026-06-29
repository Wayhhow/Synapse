from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from web.app import app
from skills.weather_skill import WeatherResponse

client = TestClient(app)


def test_health_endpoint():
    mock_router = MagicMock()
    mock_router.skills = {"weather_skill": MagicMock(), "calculator_skill": MagicMock()}
    with patch("web.app.router_instance", mock_router):
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["skills_count"] == 2


def test_stats_endpoint():
    mock_router = MagicMock()
    report = {"weather_skill": {"score": 0.9, "executions": 3}}
    mock_router.evaluator.generate_improvement_report.return_value = report
    with patch("web.app.router_instance", mock_router):
        response = client.get("/stats")
    assert response.status_code == 200
    assert response.json() == report
    mock_router.evaluator.generate_improvement_report.assert_called_once()


def test_history_endpoint():
    mock_router = MagicMock()
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    mock_router.memory.get_history.return_value = history
    with patch("web.app.router_instance", mock_router):
        response = client.get("/history/abc-123")
    assert response.status_code == 200
    assert response.json() == history
    mock_router.memory.get_history.assert_called_once_with("abc-123")


def test_chat_text_response_skill_used_none():
    mock_router = MagicMock()
    mock_router.process_query = AsyncMock(return_value="hello")
    with patch("web.app.router_instance", mock_router):
        response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    data = response.json()
    assert data["skill_used"] is None
    assert data["reply"] == "hello"


def test_chat_model_response_skill_used_classname():
    mock_router = MagicMock()
    weather = WeatherResponse(location="Seattle", weather="Clear sky", temperature=25.0)
    mock_router.process_query = AsyncMock(return_value=weather)
    with patch("web.app.router_instance", mock_router):
        response = client.post("/chat", json={"message": "weather in Seattle"})
    assert response.status_code == 200
    data = response.json()
    assert data["skill_used"] == "WeatherResponse"
