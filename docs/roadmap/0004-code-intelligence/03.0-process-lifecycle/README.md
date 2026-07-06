# Task 03.0 — Process Lifecycle Manager

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Create `aegis/openclaude/process.py` — `OpenClaudeProcess`, the only file that
manages the OpenClaude Node.js subprocess lifecycle (contract C6). It is an
async context manager taking `OpenClaudeSettings` and the `EventBus`, exposing a
ready `grpc_url` inside the `with` block (accessing it before entry raises
`RuntimeError`).

In **external mode** (`auto_start=False`, default) `__aenter__` runs a health
check and either emits `OpenClaudeConnected` or raises
`OpenClaudeUnavailableError` without starting any process. In **managed mode**
(`auto_start=True`) it launches the OpenClaude binary via
`asyncio.create_subprocess_exec` with the allowlist flags derived from C7, waits
for the gRPC port to open with `asyncio.sleep` backoff (bounded by
`connect_timeout_s`), then emits `OpenClaudeConnected`. `__aexit__` sends
`SIGTERM` and awaits termination (grace period, then `SIGKILL`) in managed mode
and emits `OpenClaudeDisconnected` in both modes — even if `__aenter__` raised
after the process started. Managed-mode subprocess stderr is forwarded to the
logger at `DEBUG`; stdout is discarded. When `grpc_url` is `localhost:0`, a free
port is chosen by binding and releasing a temporary socket, and the resolved
port is exposed via `grpc_url`.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [External mode `__aenter__` / `__aexit__`](01-external-mode.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [Managed mode subprocess start/stop](02-managed-mode.md) | ⬜ Not started | 03, 04 |
| 03 | [Port-0 free-port selection](03-port-selection.md) | ⬜ Not started | 04.0 |
| 04 | [stderr forwarding to `logger`](04-stderr-forwarding.md) | ⬜ Not started | 04.0 |

## Key constraints

- This is the **only** module that starts/stops/health-checks the OpenClaude
  process (C3, C6).
- All subprocess calls use `asyncio.create_subprocess_exec`; never
  `subprocess.Popen` in an async path (C9).
- `OpenClaudeConnected` emitted exactly once per successful `__aenter__`;
  `OpenClaudeDisconnected` exactly once per `__aexit__`. Managed mode always
  terminates the process on exit, including the entry-raised-after-port-open
  case.
- `asyncio.sleep` for backoff — never `time.sleep`.
- Subprocess stderr goes to the logger under `SensitiveFilter`; no raw payload
  text is logged (C9).
