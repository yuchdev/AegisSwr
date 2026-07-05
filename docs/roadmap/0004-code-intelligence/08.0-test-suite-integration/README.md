# Task 08.0 — Test Suite — Integration

**Parent milestone:** [Milestone 0005 — OpenClaude Integration](/docs/roadmap/0005-openclaude/plan.md)
**Status:** ⬜ Not started

## Scope

Author the integration suite under `tests/openclaude/integration/`, exercising a
**live** OpenClaude process end to end. `conftest.py` carries a session-scoped
skip guard (skip the whole module when the `openclaude` binary is absent or, for
external-mode tests, `OPENCLAUDE_GRPC_URL` is unset), a `live_openclaude_process`
managed-mode fixture that starts OpenClaude against a small throwaway Python
stub project in a temp directory and tears it down in a finaliser, and a
`live_grpc_client` connected to that process.

Test files: `test_process_lifecycle.py` (managed start within
`connect_timeout_s`, `OpenClaudeConnected` emitted, stop within the grace
period, `OpenClaudeDisconnected` emitted), `test_grpc_stream.py` (a `query`
returns a non-empty `DONE` frame preceded by at least one `TEXT_CHUNK`;
`health_check()` returns `True` live), `test_tool_live.py`
(`OpenClaudeTool.run()` returns a non-empty result, `OpenClaudeStreamCompleted`
carries a positive estimate, at least one `OpenClaudeToolCall` is emitted —
proving OpenClaude actually navigated rather than answering from priors), and
`test_allowlist_enforcement.py` (a task requiring a write tool is denied under
the default allowlist; a `Read`/`Grep`-only task succeeds). These tests also
serve as the runtime-quality check flagged in Background — a weak model that
cannot sustain multi-step tool flows will surface here.

## Subtasks

| # | Name | Status |
|---|------|--------|
| 01 | `integration/conftest.py` + skip guards | ⬜ Not started |
| 02 | `test_process_lifecycle.py` | ⬜ Not started |
| 03 | `test_grpc_stream.py` | ⬜ Not started |
| 04 | `test_tool_live.py` | ⬜ Not started |
| 05 | `test_allowlist_enforcement.py` | ⬜ Not started |

## Key constraints

- All integration tests are **skipped** (not failed) when the binary is absent
  or the env var is unset.
- Tests that run pass without mocks; no integration test leaves a running
  OpenClaude process after the session.
- Tests use a dedicated temp-directory stub project, never the Aegis SWR source
  tree, and run read-only under the allowlist.
- Gated behind an `OPENCLAUDE_INTEGRATION` CI signal (task 09.0): skipped on
  PRs, optional on main.
