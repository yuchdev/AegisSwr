# Task 07.0 — OpenHands Client & Process Lifecycle

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ✅ Complete (2026-08-25) — both subtasks

## Scope

Author the two files that let Aegis SWR speak to an OpenHands sidecar and own its
lifecycle, mirroring the OpenClaude split from Milestone 0004
(`grpc/client.py` + `process.py`) but for OpenHands' REST/WS transport
(contract C8).

Create `aegis_swr/openhands/client.py` — `OpenHandsClient`, the **sole** file in
the entire codebase permitted to import the OpenHands HTTP/WS client library
(contract C3, exactly as `openclaude/grpc/client.py` is the only `grpc`
importer). It creates a conversation over REST, subscribes to the OpenHands
Socket.IO `oh_event` stream, and exposes `run(task, run_id)` as an async
generator yielding typed, library-free `AgentEvent` projections of the
Action/Observation stream up to the terminal agent state. `health_check()`
probes the server's REST status endpoint within `connect_timeout_s`, returning
`False` (never raising) when unreachable. Transport errors are surfaced as
`OpenHandsUnavailableError`; no raw library exception escapes the file (C3). The
underlying REST/WS session is injectable via a `from_session(...)` classmethod so
unit tests script an event sequence with no live sidecar.

Create `aegis_swr/openhands/process.py` — `OpenHandsProcess`, the async context
manager owning the OpenHands sidecar lifecycle (C8, mirroring 0004's C6). In
**external mode** (`auto_start=False`, default) `__aenter__` health-checks an
already-running server and either emits `OpenHandsConnected` or raises
`OpenHandsUnavailableError` without starting anything. In **managed mode**
(`auto_start=True`, where the deployment supports launching the server as a
subprocess) it spawns the server via `asyncio.create_subprocess_exec`, waits for
the port to accept with `asyncio.sleep` backoff bounded by `connect_timeout_s`,
then emits `OpenHandsConnected`. `__aexit__` sends `SIGTERM` then escalates to
`SIGKILL` after a grace period in managed mode and emits `OpenHandsDisconnected`
exactly once in both modes. The process is registered on the app
`AsyncExitStack` by the composition root (Task 10.0) for RAII teardown.

## Subtasks

| #  | Name                                                                       | Status         | Blocks     |
|----|----------------------------------------------------------------------------|----------------|------------|
| 01 | [`OpenHandsClient` (sole client-library importer)](01-openhands-client.md) | ✅ Complete    | 02, 08.0   |
| 02 | [`OpenHandsProcess` sidecar lifecycle](02-openhands-process.md)            | ✅ Complete    | 08.0, 10.0 |

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- The OpenHands HTTP/WS client library is imported in **`client.py` only** (C3); enforced by the per-package isolation `grep` CI check and the pytest isolation test (Task 11.0), mirroring 0004's `openclaude-isolation` job.
- `OpenHandsProcess` is the **only** module that starts/stops/health-checks the OpenHands sidecar (C3, C8); it is an async context manager with an external-mode and (where applicable) a managed-mode path.
- `OpenHandsConnected` emitted exactly once per successful `__aenter__`; `OpenHandsDisconnected` exactly once per `__aexit__` — including the entry-raised-after-start case (C8).
- All subprocess spawns use `asyncio.create_subprocess_exec`, never `subprocess.Popen` in an async path; `asyncio.sleep` for backoff, never `time.sleep` (C13).
- `health_check()` returns `bool` and never raises; `run()` raises `OpenHandsUnavailableError` on transport failure — no raw client-library exception escapes `client.py` (C3).
- Session/client injectable via `from_session`; unit tests drive a scripted `oh_event` sequence through a mock session with no live OpenHands process.
- `OpenHandsUnavailableError`, `OpenHandsConnected`, and `OpenHandsDisconnected` are **forward-declared minimally** here (as OpenClaude's `events.py` / `exceptions.py` were declared ahead of their canonical task); Task 09.0 supplies the canonical versions and must preserve these shapes (C10).
- No raw incident payload, task text, response text, or credential ever reaches a log sink or exception message; loguru sinks carry `SensitiveFilter` (C13).

## Files

```
src/aegis_swr/openhands/
├── client.py       ← OpenHandsClient: sole OpenHands HTTP/WS client-library importer; REST create-conversation; Socket.IO oh_event stream → AgentEvent (subtask 01, C3, C8)
├── process.py      ← OpenHandsProcess: external/managed sidecar lifecycle; Connected/Disconnected exactly once; RAII teardown (subtask 02, C8)
├── exceptions.py   ← minimal forward-declaration of OpenHandsUnavailableError (canonical: Task 09.0)
└── events.py       ← minimal forward-declaration of OpenHandsConnected / OpenHandsDisconnected (canonical: Task 09.0)
```

> `config.py` (`OpenHandsSettings`) is delivered by Task 06.0 and consumed here.
> `tool.py` (`OpenHandsTool`) is delivered by Task 08.0, which consumes
> `OpenHandsClient`. The canonical `events.py` / `exceptions.py` are Task 09.0;
> this task only forward-declares the three symbols `process.py` / `client.py`
> must emit or raise before then.
