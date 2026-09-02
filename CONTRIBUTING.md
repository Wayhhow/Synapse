# Contributing to Synapse

Thanks for your interest in improving Synapse! This document covers the
basics; the architecture is described in the [README](README.md).

## Development setup

```bash
git clone https://github.com/Wayhhow/Synapse.git
cd Synapse
pip install -r requirements.txt -e ".[dev]"
```

## Running the checks

```bash
pytest -q          # full suite (~141 tests, no real LLM calls, no network)
ruff check .       # lint (CI enforces this)
```

Tests are hermetic: they mock the OpenAI SDK and never call the network,
never write outside `tmpdir` (fixtures inject temp registry/memory paths
and disable tracing). Keep it that way — CI burns zero tokens.

## Project conventions

- **Every skill is a `BaseSkill` subclass** in `skills/` with Pydantic
  arg/response models, a description ending in "Trigger words: ...", and
  try/except error handling that sets the `error` field instead of raising.
- **Security gates are load-bearing**: `SkillCreator._check_top_level_safety`
  runs *before* any generated module is imported. If you touch the
  generation pipeline, keep that ordering.
- **The ratchet must never be bypassable**: any code path that replaces a
  skill file must go through the score comparison + archive helper.
- **New features need config knobs, tests, and a CHANGELOG entry.**
  Prefer `SYNAPSE_*` env vars over config files; keep the zero-extra-deps
  rule (standard library + existing requirements only).
- **Update the README** (both the Chinese and English sections) when the
  architecture or user-facing behavior changes. Honesty rules: document
  limitations, don't oversell.

## Commit style

Short imperative subjects (`feat: ...`, `fix: ...`, `docs: ...`,
`test: ...`, `refactor: ...`). Reference the mechanism (e.g. "ratchet")
rather than issue numbers when relevant.

## Where to help

- More built-in skills (the skill template in the README is the contract)
- A container-based sandbox option alongside the process sandbox
- Import-side SKILL.md compatibility (read standard skill folders)
- Better evaluator dimensions (e.g. lint-based structure scoring)
