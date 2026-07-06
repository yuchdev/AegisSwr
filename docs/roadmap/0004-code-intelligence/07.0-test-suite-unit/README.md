# Task 07.0 — Test Suite — Unit

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Author the unit suite under `tests/openclaude/unit/`, written incrementally
alongside tasks 01.0–06.0. `conftest.py` provides the injection seams: a
`mock_grpc_client` factory that turns a list of plain frame dicts into an
`AsyncMock` `OpenClaudeGrpcClient` whose `query()` yields them in order; a
recording `mock_event_bus`; `settings_no_grpc` / `settings_with_grpc`
fixtures; an ample `CallBudget`; and a dry-run `ToolContext`. Mock frame
sequences are plain dicts, so the tests carry no protobuf dependency and start
no Node.js process.

Test files mirror the implementation: `test_config.py` (valid parse, invalid
`grpc_url` and unknown `allowed_tools` raise `OpenClaudeConfigError`,
`enabled_when`-absent role omission), `test_grpc_client.py` (scripted frame
yield, `health_check()` `False`-on-`UNAVAILABLE`,
`OpenClaudeUnavailableError`-on-`DEADLINE_EXCEEDED`, `from_channel`
construction), `test_process.py` (external-mode raise on failed health check,
managed-mode terminate on clean exit, `SIGKILL` after grace, connected/
disconnected emitted exactly once), `test_tool.py` (**100% branch coverage
required** — normal stream, budget pre-check, dry-run, allowlisted vs
non-allowlisted permission, truncation, `ERROR` frame, `UNAVAILABLE`
retriable), and `test_events.py` (all seven types instantiate and emit;
`OpenClaudeStreamCompleted` carries the estimate and frame count).

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [`conftest.py` fixtures](01-conftest-fixtures.md) | ⬜ Not started | 02, 03, 04, 05, 06 |
| 02 | [`test_config.py`](02-test-config.md) | ⬜ Not started | - |
| 03 | [`test_grpc_client.py`](03-test-grpc-client.md) | ⬜ Not started | - |
| 04 | [`test_process.py`](04-test-process.md) | ⬜ Not started | - |
| 05 | [`test_tool.py` (100% branch required)](05-test-tool.md) | ⬜ Not started | - |
| 06 | [`test_events.py`](06-test-events.md) | ⬜ Not started | - |

## Key constraints

- All unit tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary
  on `PATH`.
- 100% branch coverage on `tool.py`; ≥ 90% overall unit coverage (gate in
  task 09.0).
- No `monkeypatch` of module-level globals; every gRPC and process dependency
  is injected (via `from_channel`, `mock_grpc_client`, mock event bus).
- Mock `AgentMessage` sequences are plain dicts — no proto dependency in tests.
