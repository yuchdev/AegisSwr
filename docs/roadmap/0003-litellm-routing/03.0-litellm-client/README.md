# Task 03.0 — LiteLLM Client

**Parent milestone:** [Milestone 0003 — LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Implement `aegis/router/client.py` — the **single file in the entire codebase
that imports `litellm`**. This file is a thin async wrapper around
`litellm.acompletion`. It handles provider auth configuration, latency
measurement, cost extraction, and error normalization. It does **not** implement
retry or fallback — that is `ModelRouter`'s responsibility (Task 04.0).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [CompletionRequest / CompletionResponse types](01-completion-types.md) | ⬜ Not started | 02, 03 |
| 02 | [_configure_providers() — provider auth setup](02-provider-setup.md) | ⬜ Not started | 03 |
| 03 | [async complete() — call, latency, cost](03-async-complete.md) | ⬜ Not started | 04.0 |
| 04 | [isolation boundary enforcement](04-isolation-boundary.md) | ⬜ Not started | — |

## Key constraints

- `litellm` is imported **only** in this file — `grep -r "import litellm"
  aegis/` must return exactly one hit pointing here. This is enforced by a
  pytest test (`test_litellm_is_only_imported_in_client`) and a CI lint step.
- All `litellm` exceptions are caught and re-raised as `RouterException` with
  the original as `__cause__`. Litellm internals never escape this module.
- `latency_ms` is measured wall-clock from call entry to response receipt.
- `cost_usd` is `None` (not an exception) when `litellm.completion_cost()`
  is unavailable or raises.
- `self_hosted` provider resolves to LiteLLM's `openai/` prefix + `base_url`
  from `ProviderConfig`.
