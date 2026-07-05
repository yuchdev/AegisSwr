# Task 04.0 — OpenClaudeTool Implementor

**Parent milestone:** [Milestone 0005 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Create `aegis/openclaude/tool.py` — `OpenClaudeTool`, the **sole `CodeBackend`
implementation** (contract C4). It takes an open-ended task string, delegates it
to OpenClaude over gRPC, and returns a single text result; there is no
multi-tool selection on the Aegis SWR side. The class holds an
`OpenClaudeGrpcClient`, `OpenClaudeSettings`, and the `EventBus`, and exposes a
short description advertising it as the open-ended multi-file navigation
backend.

`run()` behaviour: pre-check the `CallBudget` against `max_response_tokens // 4`
and return a non-retriable failure without opening a connection if insufficient
(C5); short-circuit to a `[dry-run]` zero-token result when `ctx.dry_run`; else
call `client.query(task, run_id)` and iterate the stream — accumulating
`TEXT_CHUNK` content, emitting `OpenClaudeToolCall` / `OpenClaudeToolResult` for
the corresponding frames, auto-approving allowlisted `PERMISSION_REQ` and
raising `PermissionDeniedError` (→ non-retriable failure + emit
`OpenClaudePermissionDenied`) for non-allowlisted ones. On `DONE` it emits
`OpenClaudeStreamCompleted` with the boundary token estimate
(`max(1, len(content) // 4)`) and returns the result; on `ERROR` or gRPC error
it emits `OpenClaudeStreamError` and returns a retriable failure for
`UNAVAILABLE`, non-retriable otherwise. Accumulated content is truncated at
`max_response_tokens` with a `truncated` metadata flag; result metadata also
carries tool-call and stream-frame counts for observability.

## Subtasks

| # | Name | Status |
|---|------|--------|
| 01 | Tool skeleton + input schema | ⬜ Not started |
| 02 | Stream processing + content accumulation | ⬜ Not started |
| 03 | Permission request handling + allowlist | ⬜ Not started |
| 04 | Budget pre-check + truncation | ⬜ Not started |

## Key constraints

- Implements the minimal `CodeBackend` contract from `aegis/code_intel/`
  (task 06.0); it never imports `aegis.code_intel`-internal state beyond that
  contract, and `aegis/code_intel/` never imports it (C3).
- Budget is charged **after** stream completion, never pre-charged; accounting
  is a boundary estimate — OpenClaude's internal token usage is opaque (C5).
- Non-allowlisted `PERMISSION_REQ` is denied without corrupting budget
  accounting; forensic analysis stays read-only (C7).
- `--dry-run` returns `[dry-run]`/`0` without calling `client.query`.
- 100% branch coverage required on this file (task 07.0); no unhandled
  exceptions escape `run()`.
- `Optional[T]`, `from __future__ import annotations`, `mypy --strict` /
  `ruff` clean; no unredacted response text logged (C9).
