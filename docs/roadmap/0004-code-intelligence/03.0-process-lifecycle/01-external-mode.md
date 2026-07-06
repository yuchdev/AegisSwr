# 01 - External mode `__aenter__` / `__aexit__`

**Parent task:** 03.0 Process Lifecycle Manager
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04

## Objective

Establish the `OpenClaudeProcess` async-context-manager skeleton and the
default **external mode** (`auto_start=False`) path (C6). In external mode
Aegis SWR assumes the OpenClaude sidecar is already running; `__aenter__`
performs only a health check against the configured gRPC endpoint — it never
launches a process. On success it emits `OpenClaudeConnected` and exposes a
ready `grpc_url`; on failure it raises `OpenClaudeUnavailableError`. `__aexit__`
emits `OpenClaudeDisconnected` exactly once (there is no process to terminate in
this mode, but the disconnect event still fires). This subtask also defines the
`grpc_url` accessor guard: reading it before `__aenter__` completes raises
`RuntimeError`.

## File: `aegis/openclaude/process.py`

```python
from __future__ import annotations

from types import TracebackType
from typing import Optional

from aegis.core.events import EventBus
from aegis.openclaude.config import OpenClaudeSettings
from aegis.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis.openclaude.exceptions import OpenClaudeUnavailableError
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient


class OpenClaudeProcess:
    """Async context manager owning the OpenClaude sidecar lifecycle (C6).

    This is the only module that starts, stops, or health-checks the OpenClaude
    Node.js subprocess (C3). It supports two modes selected by
    ``settings.auto_start``: **external** (default; health-check only, this
    subtask) and **managed** (subtask 02). ``grpc_url`` is only readable inside
    the ``async with`` block; accessing it earlier raises ``RuntimeError``.

    :ivar _settings: Environment-sourced OpenClaude configuration.
    :ivar _bus: Shared :class:`EventBus` for lifecycle event emission.
    :ivar _client: Health-check client; injected for tests or built from
        ``settings`` at entry.
    :ivar _run_id: Correlation id attached to every emitted event.
    """

    def __init__(
        self,
        settings: OpenClaudeSettings,
        bus: EventBus,
        run_id: str,
        client: Optional[OpenClaudeGrpcClient] = None,
    ) -> None:
        """Store configuration; perform no I/O and start no process here.

        :param settings: Validated :class:`OpenClaudeSettings`.
        :param bus: Shared event bus for ``OpenClaude*`` lifecycle events.
        :param run_id: Investigation run id stamped onto emitted events.
        :param client: Optional pre-built gRPC client (test seam). When
            ``None``, one is constructed from ``settings`` at ``__aenter__``.
        """
        ...

    @property
    def grpc_url(self) -> str:
        """Return the ready gRPC endpoint for the active session.

        :raises RuntimeError: If accessed before ``__aenter__`` has completed
            successfully (no endpoint is resolved yet).
        :return: Bare ``host[:port]`` the caller should dial.
        """
        ...

    async def __aenter__(self) -> "OpenClaudeProcess":
        """Enter external mode: health-check the endpoint, emit connect.

        Resolves ``grpc_url`` from ``settings``, runs
        :meth:`OpenClaudeGrpcClient.health_check`, and on success emits
        :class:`OpenClaudeConnected` exactly once. Starts no subprocess.

        :raises OpenClaudeUnavailableError: If the endpoint is unreachable or
            the health check fails.
        :return: ``self``, with ``grpc_url`` now readable.
        """
        ...

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        """Exit the context, emitting :class:`OpenClaudeDisconnected` once.

        In external mode there is no owned process to terminate; the disconnect
        event still fires exactly once. Never suppresses an in-flight exception
        (returns ``None``).
        """
        ...
```

## Implementation notes

- **Mode dispatch.** `__aenter__`/`__aexit__` branch on `settings.auto_start`.
  This subtask implements the `False` branch fully; the `True` branch is a
  documented placeholder wired in subtask 02. Keep the branch explicit so
  subtask 02 slots in without reshaping the public surface.
- **`grpc_url` guard.** Back the property with a private `Optional[str]`
  initialised to `None`. It is set only inside `__aenter__` once the endpoint is
  resolved. The property raises `RuntimeError` (not `OpenClaudeUnavailableError`)
  when still `None` — this is a programming error, not an availability failure.
- **Health check.** Construct `OpenClaudeGrpcClient` from `settings` only if one
  was not injected. Call `health_check()` with `settings.connect_timeout_s`.
  Any failure (connection refused, timeout, disallowed-tool probe per C7) is
  wrapped and re-raised as `OpenClaudeUnavailableError` — never leak a raw gRPC
  status object to callers.
- **Event ordering.** Emit `OpenClaudeConnected` only *after* the health check
  succeeds and `grpc_url` is set, so a subscriber that reacts to the event can
  safely read `grpc_url`. If the health check raises, no connect event is
  emitted and `__aexit__` is not called by the `async with` machinery.
- **Disconnect exactly once.** Guard `OpenClaudeDisconnected` with an
  idempotency flag so re-entrant or double `__aexit__` calls cannot double-emit.
- **`OpenClaudeConnected` / `OpenClaudeDisconnected` / `OpenClaudeUnavailableError`**
  are defined in Task 05.0 (`events.py`, `exceptions.py`); import them, do not
  redefine.
- **Never suppress exceptions.** `__aexit__` returns `None` so any exception
  raised inside the `with` body propagates.

## Constraints

- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` at the top of the file (C9).
- External mode starts **no** process and issues **no** `create_subprocess_exec`
  call (C6).
- `OpenClaudeConnected` emitted exactly once on successful entry;
  `OpenClaudeDisconnected` exactly once on exit — in this mode too (C6).
- No raw endpoint credentials or probe payload text reaches any log sink;
  loguru sinks carry `SensitiveFilter` (C9).
- `mypy --strict`, `ruff`, and `replace_optional.py --check` stay clean.

## Success criteria

- [ ] Reading `.grpc_url` before `__aenter__` raises `RuntimeError`.
- [ ] With `auto_start=False` and a reachable endpoint, `__aenter__` runs a
      health check, sets `grpc_url`, and emits exactly one `OpenClaudeConnected`.
- [ ] With `auto_start=False` and an unreachable endpoint, `__aenter__` raises
      `OpenClaudeUnavailableError` and emits **no** `OpenClaudeConnected`.
- [ ] External mode never calls `asyncio.create_subprocess_exec`.
- [ ] `__aexit__` emits exactly one `OpenClaudeDisconnected`, including the
      exception-in-body case, and does not suppress the exception.
- [ ] An injected mock `OpenClaudeGrpcClient` is used verbatim (no real client
      constructed) — the unit-test seam holds.
- [ ] `mypy --strict`, `ruff`, `replace_optional.py --check` clean.
