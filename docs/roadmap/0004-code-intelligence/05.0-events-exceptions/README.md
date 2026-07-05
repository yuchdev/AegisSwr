# Task 05.0 — Event Types & Exceptions

**Parent milestone:** [Milestone 0005 — OpenClaude Integration](/docs/roadmap/0005-openclaude/plan.md)
**Status:** ⬜ Not started

## Scope

Create `aegis/openclaude/events.py` with the seven `frozen=True` event
dataclasses of contract C8 (`OpenClaudeConnected`, `OpenClaudeDisconnected`,
`OpenClaudeToolCall`, `OpenClaudeToolResult`, `OpenClaudePermissionDenied`,
`OpenClaudeStreamCompleted`, `OpenClaudeStreamError`). Each carries `run_id`, a
UTC `timestamp`, and a `ClassVar[str]` `event_type` sentinel;
`OpenClaudeStreamCompleted` additionally carries the boundary `token_estimate`
and a stream-frame count. Register the event types with the existing `EventBus`
type registry using the same mechanism the router events use, and add the
`openclaude.*` events to the registry documentation.

Create `aegis/openclaude/exceptions.py` with three types:
`OpenClaudeUnavailableError` (raised by `process.py` and `grpc/client.py`),
`PermissionDeniedError` (raised by `tool.py` on a non-allowlisted
`PERMISSION_REQ`), and `OpenClaudeConfigError` (raised by `config.py` on invalid
settings — distinct from the router's `ConfigValidationError`). This task can be
written alongside task 02.0 since tasks 03.0 and 04.0 depend on these types.

## Subtasks

| # | Name | Status |
|---|------|--------|
| 01 | Seven event dataclasses | ⬜ Not started |
| 02 | Three exception types | ⬜ Not started |
| 03 | EventBus registry update | ⬜ Not started |

## Key constraints

- All event types are `frozen=True`, keyword-only construction, and carry **no
  `Any` fields**; they round-trip through the `EventBus` without error.
- Event payloads never carry raw incident payload or unredacted response text
  (C9); only counts, ids, estimates, and status strings.
- `OpenClaudeStreamCompleted` is the only event carrying the token estimate; it
  is not duplicated across events (C8).
- `Optional[T]`, `from __future__ import annotations`, `mypy --strict` clean.
