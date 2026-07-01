# Task 02.0 - Router Foundation Types

**Parent milestone:** [Milestone 0003 - LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Create the `aegis/router/` package skeleton and implement the three pure-Python
foundation modules - `config.py`, `events.py`, `exceptions.py` - that carry
**no `litellm` dependency**. These become the shared types that every other
router module imports from.

The isolation rule is strict: none of these files may import `litellm`,
`anthropic`, `openai`, or `deepseek`. Failing that check blocks the milestone.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [config.py - RouterConfig dataclasses](01-config-dataclasses.md) | ⬜ Not started | 03.0, 04.0 |
| 02 | [events.py - RouterEvent dataclasses](02-events-dataclasses.md) | ⬜ Not started | 04.0 |
| 03 | [exceptions.py - exception hierarchy](03-exceptions.md) | ⬜ Not started | 03.0, 04.0 |
| 04 | [package __init__.py](04-package-init.md) | ⬜ Not started | - |

## Key constraints

- All dataclasses must be `frozen=True` (immutability is a design invariant).
- `from __future__ import annotations` in every file.
- `RouterConfig.from_yaml()` must be idempotent (two calls on the same file
  return equal objects).
- Env-var resolution failure lists **all** missing names at once.
- `Optional[T]` from `typing`, never `T | None` (see C5 in plan.md).
