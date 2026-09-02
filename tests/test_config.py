"""Tests for SynapseConfig environment parsing."""

from core.config import SynapseConfig


def test_defaults():
    cfg = SynapseConfig.from_env()
    assert cfg.model == "gpt-4o-mini"
    assert cfg.max_steps == 5
    assert cfg.auto_repair is True
    assert cfg.auto_repair_threshold == 3
    assert cfg.sandbox_timeout == 10


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MODEL", "deepseek-chat")
    monkeypatch.setenv("SYNAPSE_LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("SYNAPSE_MAX_STEPS", "8")
    monkeypatch.setenv("SYNAPSE_AUTO_REPAIR", "0")
    monkeypatch.setenv("SYNAPSE_SANDBOX_TIMEOUT", "30")
    monkeypatch.setenv("SYNAPSE_TRACE", "off")

    cfg = SynapseConfig.from_env()
    assert cfg.model == "deepseek-chat"
    assert cfg.base_url == "https://api.deepseek.com/v1"
    assert cfg.max_steps == 8
    assert cfg.auto_repair is False
    assert cfg.sandbox_timeout == 30
    assert cfg.trace_enabled is False


def test_openai_base_url_fallback(monkeypatch):
    monkeypatch.delenv("SYNAPSE_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    cfg = SynapseConfig.from_env()
    assert cfg.base_url == "https://openrouter.ai/api/v1"


def test_invalid_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("SYNAPSE_MAX_STEPS", "not-a-number")
    monkeypatch.setenv("SYNAPSE_AUTO_REPAIR_THRESHOLD", "-5")
    cfg = SynapseConfig.from_env()
    assert cfg.max_steps == 5          # unparseable -> default
    assert cfg.auto_repair_threshold == 1  # clamped to minimum 1


def test_router_uses_config_base_url(tmpdir, monkeypatch):
    """The router's LLM client must receive the configured base_url."""
    from unittest.mock import patch, MagicMock
    from core.skill_registry import SkillRegistry
    from router.router import SkillRouter

    registry = SkillRegistry(persist_path=str(tmpdir.join("r.json")))
    cfg = SynapseConfig(base_url="https://api.deepseek.com/v1", api_key="k")
    router = SkillRouter(registry=registry, config=cfg, skills_dir=str(tmpdir))

    captured = {}
    def fake_async_openai(*args, **kwargs):
        captured.update(kwargs)
        client = MagicMock()
        client.chat.completions = MagicMock()
        return client

    with patch("router.router.AsyncOpenAI", side_effect=fake_async_openai):
        _ = router.client

    assert captured.get("base_url") == "https://api.deepseek.com/v1"
