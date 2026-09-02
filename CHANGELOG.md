# Changelog

All notable changes to Synapse are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning follows semver.

## [2.0.0] - 2026-09-02

A major evolution of the framework, borrowing proven patterns from
OpenManus (ReAct loop, provider-agnostic config), Voyager (iterative
skill refinement), mem0/Letta (layered memory), and the Agent Skills
open standard (SKILL.md export).

### Added

- **ReAct agent loop** (`SkillRouter.process_query_events`): bounded
  multi-step reasoning with tool-result feedback; every tool call of a
  turn executes (proper fix for the old "only first tool_call" warning);
  `SYNAPSE_MAX_STEPS=1` restores legacy single-shot behavior.
- **Self-healing skills**: `SkillRegistry` tracks consecutive failures;
  after `SYNAPSE_AUTO_REPAIR_THRESHOLD` (default 3), the router triggers
  `SkillCreator.repair_skill`, which feeds the real execution error back
  to the LLM and replaces the skill only if the ratchet allows it.
- **Voyager-style generation loop**: `generate_skill` retries up to
  `SYNAPSE_GENERATE_MAX_ATTEMPTS` rounds, feeding validation/syntax/
  security/ratchet/import errors back into the next attempt.
- **Skill fossil archive**: replaced skill files are archived under
  `skills/.archive/<name>/<timestamp>.py` instead of being destroyed.
- **Rolling memory summaries** (opt-in): dropped turns are compressed by
  an LLM summarizer and prepended to context; persisted to a sidecar
  file; degrades gracefully to plain FIFO without an API key.
- **Multi-provider LLM support**: `SYNAPSE_LLM_BASE_URL` (or
  `OPENAI_BASE_URL`) routes to any OpenAI-compatible endpoint (DeepSeek,
  Qwen, GLM, OpenRouter, Ollama, ...).
- **Central config** (`core/config.SynapseConfig`): all knobs via
  `SYNAPSE_*` environment variables.
- **Resilience layer** (`core/resilience.with_retries`): exponential
  backoff with jitter for transient LLM errors (rate limits, timeouts,
  5xx), on top of the SDK's transport retries.
- **JSONL tracing** (`core/tracer`): one record per query with per-step
  timings; `GET /traces` endpoint; disable via `SYNAPSE_TRACE=0`.
- **SKILL.md standard export** (`meta/skill_exporter`, `cli --export`):
  exports every skill as an [agentskills.io](https://agentskills.io)
  folder (`SKILL.md` + `skill.py`).
- **Web**: SSE streaming chat (`POST /chat/stream`), `DELETE
  /history/{id}`, `skills_used` attribution on `/chat`, refreshed dark
  UI with skill/health sidebar and markdown rendering (zero JS deps).
- **CLI**: slash commands (`/help /skills /stats /history /clear
  /export`), ANSI colors, `--stats` and `--export` flags.
- **Packaging & CI**: `pyproject.toml` (pip-installable, `synapse`
  console script), MIT `LICENSE`, GitHub Actions matrix (Ubuntu/Windows
  x Python 3.10–3.13) running pytest + ruff.

### Changed

- `process_query` now returns the loop's final natural-language answer
  (str) in loop mode; the structured Pydantic result is returned only in
  legacy `max_steps=1` mode.
- Memory persist format: main file unchanged (backward compatible);
  summaries stored in `<persist_path>.summaries.json`.
- Unsafe generated filenames are sanitized to a safe basename (with a
  class-name fallback) instead of hard-failing.
- README rewritten to document the new architecture honestly.

### Fixed

- Multiple tool calls per LLM turn are now all executed and answered
  (previously only the first was processed with a warning).
- `request_new_skill` called repeatedly for the same intent no longer
  triggers duplicate generations within one query.

### Tests

- Suite grew from 93 to 141 tests, adding coverage for the agent loop,
  self-healing, resilience, config, tracer, memory summaries, exporter
  and the new web endpoints.

## [1.x] - earlier

Initial architecture: skill discovery, LLM routing, Meta-Evolution,
5-dimension evaluation with ratchet, process sandbox, session memory,
CLI + FastAPI web UI. See git history.
