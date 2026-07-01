# Task 01.0 — agents.yaml Schema Extension

**Parent milestone:** [Milestone 0003 — LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Extend `aegis/config/agents.yaml` with a top-level `providers` block that
declares each model provider's credentials and endpoints, and augment each
agent entry with `fallback`, `timeout_s`, and `retry` fields. This is the
**only task that touches YAML**; all other tasks read from the typed
`RouterConfig` Python objects that `RouterConfig.from_yaml()` produces.

This task is self-contained: no Python source changes, only configuration and
the `RouterConfig` loader (which lives in Task 02.0 but validates this schema).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [providers block](01-providers-block.md) | ⬜ Not started | 02, 03 |
| 02 | [per-agent fallback/timeout/retry fields](02-agent-fields.md) | ⬜ Not started | 03 |
| 03 | [RouterConfig validation contract](03-config-validation.md) | ⬜ Not started | 02.0 |

## Key constraints

- All existing fields (`model`, `role`) remain valid without the new optional
  fields — no breaking change to `agents.yaml` consumers.
- `${ENV_VAR}` references in `api_key` and `base_url` are resolved at load
  time; missing vars surface as a **single** `ConfigValidationError` that lists
  all missing names at once, not one at a time.
- A reference to an undefined `providers` key in an agent entry raises
  `ConfigValidationError` with a clear message.
- No credentials hard-coded in YAML — all secrets come from environment
  variables per `.claude/CLAUDE.md` §3.
