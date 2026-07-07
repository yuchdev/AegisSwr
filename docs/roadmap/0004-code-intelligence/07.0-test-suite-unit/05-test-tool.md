# 05 - `test_tool.py` (100% branch required)

**Parent task:** 07.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** 01 (fixtures), 04.0 (`OpenClaudeTool.run()`), 05.0 (events +
`PermissionDeniedError`), 06.0 subtask 01 (`CallBudget`, `ToolContext`,
`CodeResult`).
**Blocks:** none

## Objective

Exercise **every branch** of `OpenClaudeTool.run()` — the milestone mandates
**100% branch coverage on `tool.py`** (Global acceptance criteria; Task 04.0 key
constraints). Each decision point in `run()` gets at least one dedicated test:
the budget pre-check, the dry-run short-circuit, per-frame dispatch (`TEXT_CHUNK`
/ `TOOL_CALL` / `TOOL_RESULT` / allowlisted `PERMISSION_REQ` / non-allowlisted
`PERMISSION_REQ` / `DONE` / `ERROR`), content truncation, and the two gRPC error
classes (`UNAVAILABLE` → retriable, other → non-retriable). The gRPC client is
always the `mock_grpc_client` scripting plain frame dicts; no process, no
network, no proto import. `run()` must let **no** exception escape — every error
path returns a failure `CodeResult`.

## File: `tests/openclaude/unit/test_tool.py`

```python
from __future__ import annotations

import pytest

from aegis.openclaude.tool import OpenClaudeTool
from aegis.openclaude.exceptions import (
    OpenClaudeUnavailableError,
    PermissionDeniedError,
)
from aegis.openclaude.events import (
    OpenClaudeToolCall,
    OpenClaudeToolResult,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
)
from aegis.code_intel.budget import CallBudget


def _tool(client, settings, bus) -> OpenClaudeTool:
    """Construct OpenClaudeTool with fully injected collaborators."""
    return OpenClaudeTool(client=client, settings=settings, bus=bus)


# --- 1. Happy path ----------------------------------------------------------

async def test_run_success_stream_returns_concatenated_text(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """TEXT_CHUNK... + DONE → result.text is the concatenation, success, no error event."""


# --- 2. Budget pre-check short-circuit --------------------------------------

async def test_run_budget_insufficient_short_circuits(
    settings_with_grpc, mock_event_bus, mock_grpc_client, live_ctx,
) -> None:
    """CallBudget(0) < max_response_tokens//4 → non-retriable failure, client.query NEVER called."""


# --- 3. Dry-run short-circuit -----------------------------------------------

async def test_run_dry_run_short_circuits(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, dry_run_ctx,
) -> None:
    """ctx.dry_run → '[dry-run]' result, zero token estimate, client.query NEVER called."""


# --- 4. TOOL_CALL / TOOL_RESULT emission ------------------------------------

async def test_run_tool_call_frame_emits_openclaude_tool_call(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """A TOOL_CALL frame emits OpenClaudeToolCall and increments the tool-call count."""

async def test_run_tool_result_frame_emits_openclaude_tool_result(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """A TOOL_RESULT frame emits OpenClaudeToolResult."""


# --- 5. Permission branches -------------------------------------------------

async def test_run_allowlisted_permission_auto_approved(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """PERMISSION_REQ for an allowlisted binary is auto-approved; stream continues to DONE; success."""

async def test_run_non_allowlisted_permission_denied(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """PERMISSION_REQ for a non-allowlisted binary → PermissionDeniedError → non-retriable failure + OpenClaudePermissionDenied emitted; budget uncorrupted."""


# --- 6. Truncation ----------------------------------------------------------

async def test_run_content_truncated_at_max_tokens(
    mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """Accumulated content beyond max_response_tokens is truncated; result metadata truncated=True."""

async def test_run_content_not_truncated_when_within_limit(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """Content within max_response_tokens → truncated=False (the false side of the branch)."""


# --- 7. Terminal ERROR frame ------------------------------------------------

async def test_run_error_frame_returns_non_retriable_failure(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """A terminal ERROR frame → OpenClaudeStreamError emitted, non-retriable failure result."""


# --- 8/9. gRPC error classes ------------------------------------------------

async def test_run_grpc_unavailable_returns_retriable_failure(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """query() raising OpenClaudeUnavailableError(UNAVAILABLE) → retriable failure + OpenClaudeStreamError."""

async def test_run_grpc_other_error_returns_non_retriable_failure(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """query() raising a non-UNAVAILABLE OpenClaudeUnavailableError → non-retriable failure + OpenClaudeStreamError."""


# --- 10. Stream-completed estimate ------------------------------------------

async def test_stream_completed_carries_boundary_token_estimate(
    settings_with_grpc, mock_event_bus, mock_grpc_client, ample_budget, live_ctx,
) -> None:
    """On DONE, OpenClaudeStreamCompleted.token_estimate == max(1, len(content)//4)."""

async def test_budget_charged_after_stream_completion_not_precharged(
    settings_with_grpc, mock_event_bus, mock_grpc_client, live_ctx,
) -> None:
    """Budget is charged max(1, len(content)//4) AFTER DONE, never pre-charged before query()."""
```

## Test cases (branch map)

| Test | Branch / behaviour verified |
|------|------------------------------|
| `test_run_success_stream_returns_concatenated_text` | happy path: `TEXT_CHUNK`* → `DONE`; `CodeResult` success, `text` == concatenation |
| `test_run_budget_insufficient_short_circuits` | C5 pre-check false branch: budget < `max_response_tokens // 4` → non-retriable failure, `client.query` never called (no connection) |
| `test_run_dry_run_short_circuits` | C5/C9 dry-run branch: `ctx.dry_run` True → `[dry-run]` result, `token_estimate == 0`, `client.query` never called |
| `test_run_tool_call_frame_emits_openclaude_tool_call` | `TOOL_CALL` dispatch branch → `OpenClaudeToolCall` emitted, tool-call count += 1 |
| `test_run_tool_result_frame_emits_openclaude_tool_result` | `TOOL_RESULT` dispatch branch → `OpenClaudeToolResult` emitted |
| `test_run_allowlisted_permission_auto_approved` | C7 allowlisted `PERMISSION_REQ` branch: auto-approve, stream continues to `DONE`, success |
| `test_run_non_allowlisted_permission_denied` | C2/C7 non-allowlisted `PERMISSION_REQ` branch: raise `PermissionDeniedError` → non-retriable failure, `OpenClaudePermissionDenied` emitted, budget not corrupted |
| `test_run_content_truncated_at_max_tokens` | C5 truncation true branch: content > `max_response_tokens` → truncated, `metadata.truncated is True` |
| `test_run_content_not_truncated_when_within_limit` | C5 truncation false branch: `metadata.truncated is False` |
| `test_run_error_frame_returns_non_retriable_failure` | terminal `ERROR` frame branch → `OpenClaudeStreamError`, non-retriable failure |
| `test_run_grpc_unavailable_returns_retriable_failure` | `UNAVAILABLE` gRPC error branch → **retriable** failure, `OpenClaudeStreamError` |
| `test_run_grpc_other_error_returns_non_retriable_failure` | non-`UNAVAILABLE` gRPC error branch → **non-retriable** failure, `OpenClaudeStreamError` |
| `test_stream_completed_carries_boundary_token_estimate` | C5/C8: `OpenClaudeStreamCompleted.token_estimate == max(1, len(content)//4)` |
| `test_budget_charged_after_stream_completion_not_precharged` | C5: budget charged **after** `DONE`, never pre-charged; charge == `max(1, len(content)//4)` |

## Constraints

- **100% branch coverage on `aegis/openclaude/tool.py`** — enforced under
  `--cov=aegis.openclaude.tool --cov-branch --cov-fail-under=100` scoped to this
  file in task 09.0. Every `if`/`elif`/`else`, every frame-type dispatch arm,
  both sides of the truncation test, and both gRPC error classes must be hit.
  Include the true **and** false side of the truncation branch and both the
  allowlisted/non-allowlisted permission arms explicitly.
- All tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary on
  `PATH`; frames are plain dicts via `mock_grpc_client`, so no `grpc` / `_pb2`
  import appears in this file.
- Every collaborator is constructor-injected (`client=`, `settings=`, `bus=`);
  **no `monkeypatch`** of `tool.py` module globals.
- `run()` must never let an exception escape — assert every failure path returns
  a `CodeResult` with the correct `retriable` flag rather than raising.
- Assert the non-allowlisted-permission path leaves `CallBudget` accounting
  intact (the boundary charge is not applied on a denied invocation, or is
  applied consistently — assert against whichever 04.0 defines and flag if
  ambiguous).
- No unredacted response text is asserted against any log sink (C9).
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).

## Success criteria

- [ ] All 14 test functions present and passing.
- [ ] `pytest --cov=aegis.openclaude.tool --cov-branch` reports **100%** branch
      coverage for `tool.py` with these tests alone.
- [ ] `test_run_budget_insufficient_short_circuits` and
      `test_run_dry_run_short_circuits` both assert `client.query` was **never**
      called.
- [ ] `test_run_grpc_unavailable_returns_retriable_failure` asserts
      `result.retriable is True`; `test_run_grpc_other_error_...` asserts
      `result.retriable is False`.
- [ ] `test_stream_completed_carries_boundary_token_estimate` asserts the
      emitted `OpenClaudeStreamCompleted.token_estimate == max(1, len(content)//4)`.
- [ ] `test_run_non_allowlisted_permission_denied` asserts exactly one
      `OpenClaudePermissionDenied` emission and a non-retriable failure.
- [ ] No `grpc` / `_pb2` import in this file.
- [ ] `ruff`, `replace_optional.py --check` clean.
