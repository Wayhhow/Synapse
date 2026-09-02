"""
Central configuration for Synapse (borrowing the "configuration over hardcoding"
convention popularized by OpenManus ``config.toml`` / LangChain settings).

Every knob is environment-driven so deployments can switch LLM providers
(OpenAI, DeepSeek, Qwen, GLM, OpenRouter, Ollama, ... any OpenAI-compatible
endpoint), tune the agent loop, and enable/disable subsystems without touching
code. ``SynapseConfig.from_env()`` reads ``SYNAPSE_*`` variables once at
startup; constructors still accept explicit overrides (used heavily by tests).
"""

import os
from dataclasses import dataclass
from typing import Optional


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value


@dataclass(frozen=True)
class SynapseConfig:
    """Immutable snapshot of Synapse runtime configuration."""

    # --- LLM provider (any OpenAI-compatible endpoint) ---
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    llm_timeout: float = 60.0
    llm_max_retries: int = 2          # OpenAI SDK built-in transport retries
    app_retries: int = 2              # core.resilience retries on rate-limit/5xx

    # --- Agent loop ---
    max_steps: int = 5                # max LLM rounds per query (1 = legacy single-shot)

    # --- Sandbox ---
    sandbox_timeout: int = 10

    # --- Memory ---
    memory_max_history: int = 10
    memory_persist_path: str = "data/memory.json"

    # --- Registry ---
    registry_persist_path: str = "data/skill_registry.json"

    # --- Self-evolution ---
    generate_max_attempts: int = 3    # Voyager-style generate->validate->repair rounds
    auto_repair: bool = True          # regenerate a skill after N consecutive failures
    auto_repair_threshold: int = 3

    # --- Observability ---
    trace_enabled: bool = True
    trace_path: str = "data/traces.jsonl"

    @classmethod
    def from_env(cls) -> "SynapseConfig":
        load_env_file()
        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or None,
            base_url=os.getenv("SYNAPSE_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None,
            model=os.getenv("SYNAPSE_MODEL", "gpt-4o-mini"),
            temperature=_env_float("SYNAPSE_TEMPERATURE", 0.2),
            llm_timeout=_env_float("SYNAPSE_LLM_TIMEOUT", 60.0),
            llm_max_retries=_env_int("SYNAPSE_LLM_MAX_RETRIES", 2),
            app_retries=_env_int("SYNAPSE_APP_RETRIES", 2),
            max_steps=_env_int("SYNAPSE_MAX_STEPS", 5),
            sandbox_timeout=_env_int("SYNAPSE_SANDBOX_TIMEOUT", 10),
            memory_max_history=_env_int("SYNAPSE_MEMORY_MAX_HISTORY", 10),
            memory_persist_path=os.getenv("SYNAPSE_MEMORY_PATH", "data/memory.json"),
            registry_persist_path=os.getenv("SYNAPSE_REGISTRY_PATH", "data/skill_registry.json"),
            generate_max_attempts=_env_int("SYNAPSE_GENERATE_MAX_ATTEMPTS", 3),
            auto_repair=_env_bool("SYNAPSE_AUTO_REPAIR", True),
            auto_repair_threshold=_env_int("SYNAPSE_AUTO_REPAIR_THRESHOLD", 3),
            trace_enabled=_env_bool("SYNAPSE_TRACE", True),
            trace_path=os.getenv("SYNAPSE_TRACE_PATH", "data/traces.jsonl"),
        )


_ENV_LOADED = False


def load_env_file() -> None:
    """Load ``.env`` once per process (thin wrapper so modules don't each
    need to remember ``load_dotenv()``)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:  # pragma: no cover - dotenv is a hard dep, but be safe
        pass
    _ENV_LOADED = True
