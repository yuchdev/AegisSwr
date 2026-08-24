# 02 - Managed mode subprocess start/stop

**Parent task:** 03.0 Process Lifecycle Manager
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03, 04

## Objective

Implement the **managed mode** (`auto_start=True`) path of `OpenClaudeProcess`
(C6). `__aenter__` launches the OpenClaude binary as a subprocess via
`asyncio.create_subprocess_exec` — never `subprocess.Popen` in an async path
(C9) — passing tool-allowlist and Bash-allowlist flags derived from
`settings.allowed_tools` / `settings.bash_allowlist` (C7). It then waits for the
gRPC port to open using `asyncio.sleep` backoff bounded by
`settings.connect_timeout_s`, and on readiness emits `OpenClaudeConnected`.
`__aexit__` sends `SIGTERM`, awaits termination within a grace period, escalates
to `SIGKILL` if still alive, and emits `OpenClaudeDisconnected`. The critical
invariant: managed mode **always** terminates the subprocess on exit — even when
`__aenter__` raised *after* the process had already started (e.g. the port never
opened within the timeout). This requires a try/finally guarantee, not a
happy-path-only shutdown.

## File: `aegis/openclaude/process.py`

```python
from __future__ import annotations

import asyncio
from typing import Optional


class OpenClaudeProcess:
    # ... external-mode surface from subtask 01 ...

    async def _start_managed(self):
        """Launch the sidecar and block until its gRPC port is accepting.

        Builds the argv (binary + allowlist flags), starts the process via
        :func:`asyncio.create_subprocess_exec`, then polls the resolved port
        with :func:`asyncio.sleep` backoff bounded by
        ``settings.connect_timeout_s``. On readiness the caller emits
        :class:`OpenClaudeConnected`.

        :raises OpenClaudeUnavailableError: If the port does not open within
            ``connect_timeout_s`` (the started process is terminated by the
            enclosing ``__aenter__`` finally-guard before this propagates).
        """
        ...

    def _build_argv(self) -> list[str]:
        """Assemble the OpenClaude launch argv with allowlist flags (C7).

        Derives ``--allowed-tools`` from ``settings.allowed_tools`` and the
        ``Bash`` binary allowlist from ``settings.bash_allowlist``, plus the
        resolved gRPC bind address (see subtask 03 for port-0 resolution).

        :return: Argument vector for :func:`asyncio.create_subprocess_exec`.
        """
        ...

    async def _await_port_open(self):
        """Poll the resolved gRPC port until it accepts a TCP connection.

        Uses :func:`asyncio.sleep` backoff; the total wait is bounded by
        ``settings.connect_timeout_s``. Never uses :func:`time.sleep` (C9).

        :raises OpenClaudeUnavailableError: On timeout before the port opens.
        """
        ...

    async def _terminate_managed(self):
        """Terminate the owned subprocess: SIGTERM, grace wait, then SIGKILL.

        Idempotent and safe to call when the process is already dead or was
        never started. Awaits the process's exit so no zombie remains.
        """
        ...
```

## Implementation notes

- **Async spawn only.** Use `asyncio.create_subprocess_exec(*argv, stdout=DEVNULL,
  stderr=asyncio.subprocess.PIPE)` — `stdout` is discarded (gRPC traffic is on
  the channel, not stdout; C6); `stderr` is piped for forwarding in subtask 04.
  Never `subprocess.Popen` in an async path (C9).
- **Allowlist flags (C7).** `_build_argv` maps `settings.allowed_tools` to the
  OpenClaude `--allowed-tools` flag and `settings.bash_allowlist` to the Bash
  binary allowlist flag. These are the launch-time enforcement mechanism that
  guarantees read-only forensic analysis; do not omit them and do not read the
  env directly (values come from `settings`, C1).
- **Readiness probe.** `_await_port_open` performs a cheap TCP connect to the
  resolved host:port in a loop, sleeping with `asyncio.sleep` between attempts
  (small fixed or linearly-growing interval), and gives up once the cumulative
  elapsed time reaches `connect_timeout_s`. On give-up it raises
  `OpenClaudeUnavailableError`. A full gRPC `health_check` may also be used, but
  the TCP-accept probe is sufficient and avoids a premature RPC.
- **Termination sequence.** `_terminate_managed`: if the process is still
  running, send `SIGTERM` (`process.terminate()`), then `await
  asyncio.wait_for(process.wait(), timeout=grace)`. On `asyncio.TimeoutError`,
  send `SIGKILL` (`process.kill()`) and `await process.wait()`. Guard every step
  so a process that already exited (non-`None` `returncode`) is a no-op.
- **Always-terminate invariant.** Structure `__aenter__` so that once
  `create_subprocess_exec` has returned a live process, any subsequent failure
  (port never opened, health probe raised, cancellation) runs
  `_terminate_managed` before the exception leaves `__aenter__`. Use a
  `try/except: await self._terminate_managed(); raise` around the readiness
  wait, and keep the process handle stored so `__aexit__` also terminates it if
  it survives. The stderr-forwarding task (subtask 04) must likewise be
  cancelled on this failure path.
- **Event exactly-once.** `OpenClaudeConnected` is emitted only after the port
  is confirmed open. `OpenClaudeDisconnected` is emitted exactly once from
  `__aexit__` (shared idempotency flag with subtask 01), *after*
  `_terminate_managed` completes.
- **Grace period.** Introduce a module-level constant (e.g.
  `_TERMINATE_GRACE_S`) rather than a magic literal; document its default.
- Import `OpenClaudeConnected` / `OpenClaudeDisconnected` /
  `OpenClaudeUnavailableError` from Task 05.0; do not redefine.

## Constraints

- `asyncio.create_subprocess_exec`, never `subprocess.Popen` in an async path
  (C6, C9).
- `asyncio.sleep` for readiness backoff — never `time.sleep` (C9).
- Managed mode **always** terminates the subprocess on exit, including the
  entry-raised-after-start case (C6).
- `OpenClaudeConnected` exactly once on successful entry;
  `OpenClaudeDisconnected` exactly once on exit (C6).
- Allowlist flags derived from `settings`, never from `os.environ` directly
  (C1, C7).
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).
- `ruff check src/ tests/` - clean.

## Success criteria

- [ ] With `auto_start=True`, `__aenter__` calls
      `asyncio.create_subprocess_exec` exactly once with argv containing the
      allowlist flags derived from `settings`.
- [ ] `stdout` is discarded (`DEVNULL`); `stderr` is piped.
- [ ] `__aenter__` waits for the port with `asyncio.sleep` backoff and emits
      `OpenClaudeConnected` only after the port accepts.
- [ ] Port never opening within `connect_timeout_s` raises
      `OpenClaudeUnavailableError` **and** the started process is terminated
      before the exception propagates (verified via a mock/fake process).
- [ ] `__aexit__` sends SIGTERM, awaits within the grace period, and escalates
      to SIGKILL only if the process is still alive; the process is reaped (no
      zombie).
- [ ] `OpenClaudeDisconnected` emitted exactly once on exit.
- [ ] No `subprocess.Popen` and no `time.sleep` anywhere in the module.
- [ ] `ruff check src/ tests/` - clean.
