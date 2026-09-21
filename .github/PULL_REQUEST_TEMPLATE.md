## What & why

<!-- What does this PR change, and why? Link the issue if there is one. -->

## Checklist

- [ ] `pytest -q` passes locally (tests stay hermetic: no network, no real LLM)
- [ ] `ruff check .` passes
- [ ] New behaviour has a test and, if user-facing, a CHANGELOG entry
- [ ] README (中文 + English) updated if architecture or usage changed
- [ ] Security gates / ratchet paths untouched, or the change keeps their ordering guarantees (see CONTRIBUTING.md)
