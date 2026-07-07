# 04 - stderr forwarding to `logger`

**Parent task:** 03.0 Process Lifecycle Manager
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04.0

## Objective

Surface the managed subprocess's diagnostics without ever leaking sensitive
text (C6, C9). In managed mode the child's `stderr` stream is read continuously
by a background `asyncio.Task` and forwarded line-by-line to the Aegis SWR
`logger` at `DEBUG` level, under the existing `SensitiveFilter` — so no raw
incident/payload text is ever logged unredacted. `stdout` is discarded entirely
(gRPC traffic travels on the channel, not stdout). The forwarding task is
started right after the process is spawned and cancelled cleanly on `__aexit__`
so no task is left dangling and no `CancelledError` escapes.

## File: `aegis/openclaude/process.py`

```python
from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger


class OpenClaudeProcess:
    # ... external-, managed-, and port-selection surface from subtasks 01–03 ...

    def _start_stderr_forwarder(self) -> None:
        """Spawn the background task that drains the child's stderr.

        Creates an :class:`asyncio.Task` running :meth:`_forward_stderr` and
        stores its handle for cancellation at ``__aexit__``. Called once, right
        after the subprocess is spawned in managed mode.
        """
        ...

    async def _forward_stderr(self) -> None:
        """Read child stderr line-by-line and log each at ``DEBUG``.

        Loops over ``process.stderr.readline()`` until EOF, decoding each line
        and emitting it via ``logger.debug`` (subject to ``SensitiveFilter``).
        Returns on EOF; tolerates :class:`asyncio.CancelledError` at ``__aexit__``
        without re-raising a spurious error.
        """
        ...

    async def _stop_stderr_forwarder(self) -> None:
        """Cancel the forwarding task and await its clean shutdown.

        Idempotent; safe when the forwarder was never started (external mode) or
        already finished. Awaits the cancelled task and swallows the resulting
        :class:`asyncio.CancelledError`.
        """
        ...
```

## Implementation notes

- **stdout discarded.** The subprocess is spawned (subtask 02) with
  `stdout=asyncio.subprocess.DEVNULL`; no reader is attached to it. Only
  `stderr` is piped and drained here.
- **Read loop.** `_forward_stderr` loops: `line = await process.stderr.readline()`;
  break on empty bytes (EOF). Decode with `errors="replace"` and `rstrip` the
  trailing newline. Log via `logger.debug(...)`. Do not log at `INFO`/`WARNING`
  — child diagnostics are noisy and must default to `DEBUG` (C6).
- **SensitiveFilter (C9).** Rely on the project-wide loguru `SensitiveFilter`
  configured on every sink; do not add an unfiltered sink here. The forwarded
  line is treated as potentially payload-derived, so it must pass through the
  same redaction path as all other logs. Pass the line as a bound field / plain
  message that the filter inspects — never bypass the configured logger.
- **Task lifecycle.** `_start_stderr_forwarder` creates the task with
  `asyncio.create_task` and keeps the handle in an `Optional[asyncio.Task[None]]`
  field (initialised `None`). `_stop_stderr_forwarder` calls `task.cancel()`,
  then `await` the task inside a `try/except asyncio.CancelledError` (or
  `contextlib.suppress(asyncio.CancelledError)`) so cancellation does not leak.
- **Wiring into exit.** `_stop_stderr_forwarder` must run on every managed-mode
  exit path, including the entry-raised-after-start failure path from subtask 02
  — cancel the forwarder before/alongside `_terminate_managed`. Cancel the
  forwarder *before* killing the process is fine; draining a few final lines is
  not required for correctness. Ensure the task is always awaited so no
  "Task was destroyed but it is pending" warning appears.
- **No forwarder in external mode.** External mode owns no process and no piped
  stream; `_start_stderr_forwarder` is never called and
  `_stop_stderr_forwarder` is a no-op there.
- **Never crash the manager on log errors.** A decode or logging error inside
  the loop must not propagate and kill the context; catch narrowly, keep
  draining. Never use a bare `except:` (C9).

## Constraints

- stderr forwarded at `DEBUG` under `SensitiveFilter`; stdout discarded (C6, C9).
- No raw incident/payload text (dump/log/stack) is ever logged unredacted (C9).
- The forwarding task is cancelled and awaited cleanly on `__aexit__`; no
  dangling task, no leaked `CancelledError`.
- No bare `except:`; logging failures never crash the lifecycle manager.
- `Optional[T]` from `typing`; `from __future__ import annotations` (C9).
- `ruff`, `replace_optional.py --check` clean.

## Success criteria

- [ ] In managed mode a background task drains `process.stderr` line-by-line and
      each line is logged at `DEBUG` via the project `logger`.
- [ ] `stdout` is spawned with `DEVNULL` and has no reader attached.
- [ ] Every forwarded line passes through the configured `SensitiveFilter`; no
      unfiltered sink is added.
- [ ] The forwarder is cancelled and awaited on `__aexit__` with no leaked
      `CancelledError` and no pending-task warning — including the
      entry-raised-after-start failure path.
- [ ] External mode never starts a forwarder (`_stop_stderr_forwarder` is a
      safe no-op).
- [ ] A logging/decode error inside the loop does not propagate out of the
      context manager.
- [ ] `ruff`, `replace_optional.py --check` clean.
