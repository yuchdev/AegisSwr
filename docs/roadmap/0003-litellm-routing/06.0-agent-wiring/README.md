# Task 06.0 — Agent Wiring

**Parent milestone:** [Milestone 0003 — LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Update `aegis/core/agents/` to call `ModelRouter.complete()` instead of any
direct provider SDK, and update `aegis/app.py` (the composition root) to
construct `RouterConfig → LiteLLMClient → ModelRouter` and inject the router
into all agents. After this task, no direct provider import (`anthropic`,
`openai`, `deepseek`) exists anywhere in `aegis/core/`.

This task also implements the `NullClient` for `--dry-run` mode.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [BaseAgent.reason() using ModelRouter](01-base-agent-router.md) | ⬜ Not started | 02 |
| 02 | [constructor injection for all concrete agents](02-agent-constructor-injection.md) | ⬜ Not started | 03 |
| 03 | [app.py composition root](03-app-composition-root.md) | ⬜ Not started | 04 |
| 04 | [NullClient for --dry-run](04-dry-run-null-client.md) | ⬜ Not started | — |

## Key constraints

- **No provider imports in `aegis/core/agents/`** after this task. The existing
  CI grep check (C2 from plan.md) enforces this.
- `BaseAgent.__init__` receives `ModelRouter` via constructor injection — no
  global state, no module-level singletons.
- `AllProvidersExhausted` must result in a `PipelineError` event on the bus
  **before** propagating (so the UI can show the failure).
- `RouterConfig` is instantiated once at startup, not per-call.
- `ModelRouter` is shared across all agents — one instance.
- `--dry-run` uses `NullClient` (returns `content="[dry-run]"`, zero tokens,
  zero cost, 0 ms latency) — the pipeline runs end-to-end without any API keys.
