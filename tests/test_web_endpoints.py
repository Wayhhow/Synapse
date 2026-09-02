"""Tests for the newer web endpoints: /traces, DELETE /history, /chat/stream."""
import json
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient

from web.app import app


def test_traces_endpoint(tmpdir):
    mock_router = MagicMock()
    mock_router.tracer.read_recent.return_value = [{"query": "hi", "final_type": "text"}]
    with patch("web.app.router_instance", mock_router):
        client = TestClient(app)
        response = client.get("/traces?limit=5")
    assert response.status_code == 200
    assert response.json() == [{"query": "hi", "final_type": "text"}]
    mock_router.tracer.read_recent.assert_called_once_with(limit=5)


def test_delete_history_endpoint():
    mock_router = MagicMock()
    with patch("web.app.router_instance", mock_router):
        client = TestClient(app)
        response = client.delete("/history/abc")
    assert response.status_code == 200
    assert response.json()["status"] == "cleared"
    mock_router.memory.clear.assert_called_once_with("abc")


def test_chat_reports_skills_used():
    mock_router = MagicMock()
    mock_router.process_query = AsyncMock(return_value="here you go")
    mock_router.last_skills_used = ["weather_skill"]
    with patch("web.app.router_instance", mock_router):
        client = TestClient(app)
        response = client.post("/chat", json={"message": "weather?"})
    data = response.json()
    assert data["skill_used"] == "weather_skill"
    assert data["skills_used"] == ["weather_skill"]


def test_chat_stream_yields_sse_events():
    async def fake_events(query, session_id=None):
        yield {"type": "session", "session_id": "fixed-session"}
        yield {"type": "llm", "step": 1, "duration_ms": 12.0}
        yield {"type": "final", "text": "the answer", "result": None, "skills_used": []}

    mock_router = MagicMock()
    mock_router.process_query_events = fake_events
    with patch("web.app.router_instance", mock_router):
        client = TestClient(app)
        response = client.post("/chat/stream", json={"message": "hi", "session_id": "fixed-session"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for line in response.text.split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    assert events[0]["type"] == "session"
    assert events[-1]["type"] == "final"
    assert events[-1]["text"] == "the answer"
