# 02 - `OpenHandsProcess` sidecar lifecycle

**Parent task:** 07.0 OpenHands Client & Process Lifecycle
**State:** ⬜ Not started
**Depends on:** 01 (`OpenHandsClient.health_check()` is the readiness probe), 06.0 (`OpenHandsSettings`)
**Blocks:** 08.0 (`OpenHandsTool` runs inside this context), 10.0 (composition root registers this on the app `AsyncExitStack`)

## Objective

Implement `aegis_swr/openhands/process.py` — `OpenHandsProcess`, the async
context manager owning the OpenHands sidecar lifecycle (contract C8), mirroring
`OpenClaudeProcess`'s proven shape (0004 C6) closely. It is the **only** module
that starts, stops, or health checks the OpenHands sidecar (C3). It takes
`OpenHandsSettings` and the `EventBus` and exposes a ready `server_url` inside the
`async with` block (accessing it before entry raises `RuntimeError`).

In **external mode** (`auto_start=False`, default) `__aenter__` runs a health
check against the configured server and either emits `OpenHandsConnected` or
raises `OpenHandsUnavailableError` — it starts no process. In **managed mode**
(`auto_start=True`, available only where the deployment supports launching the
OpenHands server as a subprocess) it spawns the server via
`asyncio.create_subprocess_exec`, waits for the port to accept a TCP connection
with `asyncio.sleep` backoff bounded by `settings.connect_timeout_s`, then emits
`OpenHandsConnected`. `__aexit__` sends `SIGTERM` and awaits termination (grace
period, then `SIGKILL`) in managed mode and emits `OpenHandsDisconnected` exactly
once in both modes — even if `__aenter__` raised after the process started.
Managed-mode subprocess stderr is forwarded to the logger at `DEBUG` under
`SensitiveFilter`; stdout is discarded. The critical invariant is the same as
OpenClaude's: managed mode **always** reaps the subprocess on exit, including the
entry-raised-after-start case.

> **Managed-mode caveat (C8).** OpenHands' distinguishing value is that its
> runtime executes tools inside a **Docker sandbox**; the sandboxed runtime is
> selected by `OpenHandsSettings` by default. In practice most deployments run
> OpenHands as an already-running container and use **external mode** — managed
> mode here launches the *server* process (which then manages its own Docker
> runtime), it does **not** manage Docker itself. Where a deployment cannot spawn
> the server as a subprocess, `auto_start` stays `False` and only the external
> path is exercised; the managed path mirrors `OpenClaudeProcess` for parity and
> for the co-located-server case.

## File: `aegis_swr/openhands/process.py`

```python
from __future__ import annotations

import asyncio
import contextlib
import socket
from types import TracebackType
from typing import Optional

from loguru import logger

from aegis_swr.core.events import EventBus
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import OpenHandsConnected, OpenHandsDisconnected
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError

_EXTERNAL_MODE = "external"
_MANAGED_MODE = "managed"
_DISCONNECT_REASON = "context_exit"

# Grace period (seconds) between SIGTERM and the SIGKILL escalation during
# managed-sidecar teardown; lets the server flush and exit cleanly on SIGTERM
# before we force-kill a process that ignored it. Mirrors OpenClaudeProcess.
_TERMINATE_GRACE_S: float = 5.0

# Fixed backoff (seconds) between successive TCP-accept readiness probes while
# waiting for the managed sidecar's port to open. ``asyncio.sleep`` only —
# never ``time.sleep`` (C13).
_PORT_POLL_INTERVAL_S: float = 0.05

# Loopback hosts the managed sidecar is permitted to bind/probe. A wildcard
# address (``0.0.0.0``/``::``) is never acceptable — it would expose the
# tool-executing sidecar off-box.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})


class OpenHandsProcess:
    """Async context manager owning the OpenHands sidecar lifecycle (C8).

    The only module that starts, stops, or health-checks the OpenHands sidecar
    (C3). Two modes are selected by ``settings.auto_start``: **external**
    (default; health-check only) and **managed** (Aegis-started server process,
    where the deployment supports it). ``server_url`` is only readable inside the
    ``async with`` block; accessing it earlier raises ``RuntimeError``. Mirrors
    :class:`~aegis_swr.openclaude.process.OpenClaudeProcess` (0004 C6) closely.

    :ivar _settings: Environment-sourced OpenHands configuration (C8).
    :ivar _bus: Shared :class:`EventBus` for lifecycle event emission.
    :ivar _run_id: Correlation id attached to every emitted event.
    :ivar _client: Health-check client; injected for tests or built from
        ``settings`` at entry.
    :ivar _server_url: Resolved endpoint, ``None`` until ``__aenter__`` succeeds.
    :ivar _disconnected: Idempotency guard so disconnect emits at most once.
    :ivar _process: The owned managed-mode subprocess handle, or ``None`` in
        external mode / before a managed spawn.
    :ivar _stderr_task: Background task draining the managed child's stderr, or
        ``None``. Cancelled and awaited on every managed exit path.
    """

    def __init__(
        self,
        settings: OpenHandsSettings,
        bus: EventBus,
        run_id: str,
        client: Optional[OpenHandsClient] = None,
    ):
        """Store configuration; perform no I/O and start no process here.

        :param settings: Validated :class:`OpenHandsSettings`.
        :param bus: Shared event bus for ``OpenHands*`` lifecycle events.
        :param run_id: Investigation run id stamped onto emitted events.
        :param client: Optional pre-built client (test seam). When ``None``, one
            is constructed from ``settings`` at ``__aenter__``.
        """
        ...

    @property
    def server_url(self) -> str:
        """Return the ready OpenHands server endpoint for the active session.

        :raises RuntimeError: If accessed before ``__aenter__`` has completed
            successfully (no endpoint is resolved yet).
        :return: The base server URL the caller / client should dial.
        """
        ...

    async def __aenter__(self) -> "OpenHandsProcess":
        """Enter the context, dispatching on ``settings.auto_start``.

        The external branch (``auto_start=False``) health-checks a pre-running
        server and starts no process. The managed branch (``auto_start=True``)
        spawns the server via :func:`asyncio.create_subprocess_exec`, waits for
        its port to open, and emits :class:`OpenHandsConnected`. If the port
        never opens the started process is terminated before the exception leaves
        this method (always-terminate invariant).

        :raises OpenHandsUnavailableError: If the external-mode health check
            fails, or the managed sidecar's port does not open in time.
        :return: ``self``, with ``server_url`` now readable.
        """
        ...

    async def _enter_external(self) -> "OpenHandsProcess":
        """Health-check an already-running server and emit connect (C8).

        Resolves ``server_url`` from settings, builds a client from settings only
        when none was injected, and runs :meth:`OpenHandsClient.health_check`.
        Starts no subprocess. On success sets ``server_url`` first, then emits
        exactly one :class:`OpenHandsConnected` tagged ``"external"``.

        :raises OpenHandsUnavailableError: If ``server_url`` is unset or the
            health check reports the server unreachable.
        :return: ``self``, with ``server_url`` now readable.
        """
        ...

    async def _enter_managed(self) -> "OpenHandsProcess":
        """Spawn the managed server, await readiness, and emit connect (C8).

        Resolves and stores ``server_url`` up front, delegates the spawn-and-wait
        to :meth:`_start_managed` (which enforces the always-terminate
        invariant), then publishes exactly one :class:`OpenHandsConnected` tagged
        ``"managed"``. If the connect emit (a bus subscriber raising) or
        cancellation lands in the gap after readiness, the sidecar is reaped here
        first — ``__aexit__`` would not otherwise run.

        :raises OpenHandsUnavailableError: If ``server_url`` is unset, the port
            never opens (the started process is terminated first), or the bind
            address is non-loopback.
        :return: ``self``, with ``server_url`` now readable.
        """
        ...

    async def _start_managed(self):
        """Launch the server and block until its port is accepting.

        Builds the argv (binary + sandboxed-runtime flags + loopback bind
        address), starts the process via :func:`asyncio.create_subprocess_exec`
        with ``stdout`` discarded and ``stderr`` piped, starts the stderr
        forwarder, then awaits readiness via :meth:`_await_port_open`. Any failure
        *after* the process is live — including cancellation — stops the forwarder
        and terminates the process before the exception propagates, so an
        entry-raised-after-start never orphans a sidecar.

        :raises OpenHandsUnavailableError: If the port does not open within
            ``settings.connect_timeout_s`` (the started process is terminated
            before this propagates).
        """
        ...

    def _build_argv(self) -> list[str]:
        """Assemble the OpenHands server launch argv (managed mode).

        Derives the sandboxed-runtime selector from ``settings.runtime_mode`` and
        the bind host:port from the resolved ``server_url``, validating each value
        at the argv boundary (fail closed) exactly as ``OpenClaudeProcess`` does,
        so no value can be reparsed as a flag.

        :return: Argument vector for :func:`asyncio.create_subprocess_exec`.
        """
        ...

    async def _await_port_open(self):
        """Poll the resolved loopback port until it accepts a TCP connect.

        Probes the same loopback ``host:port`` the server was told to bind,
        sleeping ``_PORT_POLL_INTERVAL_S`` between attempts with
        :func:`asyncio.sleep` (never :func:`time.sleep`). The cumulative wait is
        bounded by ``settings.connect_timeout_s``.

        :raises OpenHandsUnavailableError: On timeout before the port opens.
        """
        ...

    async def _terminate_managed(self):
        """Terminate the owned subprocess: SIGTERM, grace wait, then SIGKILL.

        Operates only on the stored asyncio process handle — never ``os.kill`` on
        a raw pid — and guards every step on ``returncode is None``. Sends
        ``SIGTERM``, awaits exit within ``_TERMINATE_GRACE_S``, and on timeout
        escalates to ``SIGKILL``; either way the process is reaped so no zombie
        remains. Idempotent: a no-op when never started or already dead.
        """
        ...

    def _start_stderr_forwarder(self):
        """Spawn the background task draining the managed child's stderr.

        Creates an :class:`asyncio.Task` running :meth:`_forward_stderr` and
        stores its handle for cancellation on every managed exit path. Called once
        after the subprocess is spawned; never called in external mode.
        """
        ...

    async def _forward_stderr(self):
        """Read child stderr line-by-line and log each at ``DEBUG`` (C13).

        Loops over ``process.stderr.readline()`` until EOF, decoding with
        ``errors="replace"`` and passing the line as a bound argument (never the
        format template) to ``logger.debug`` so the loguru ``SensitiveFilter`` on
        every sink redacts it. A per-line decode/read failure is caught narrowly
        and the loop keeps draining; ``asyncio.CancelledError`` is not caught so
        it propagates to the cancel path.
        """
        ...

    async def _stop_stderr_forwarder(self):
        """Cancel the stderr-forwarding task and await its clean shutdown.

        Idempotent; safe when the forwarder was never started (external mode) or
        already finished. Awaits the cancelled task inside
        :func:`contextlib.suppress` so the resulting
        :class:`asyncio.CancelledError` never leaks and no pending-task warning
        appears.
        """
        ...

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Optional[bool]:
        """Exit the context, emitting :class:`OpenHandsDisconnected` once.

        In managed mode the stderr forwarder is cancelled and the owned
        subprocess terminated first (both idempotent), so the disconnect event
        fires only after teardown. In external mode there is no owned process.
        Either way the disconnect fires exactly once, guarded by the shared
        idempotency flag. Never suppresses an in-flight exception (returns
        ``None``).

        :param exc_type: Exception type raised in the ``async with`` body, if any.
        :param exc: Exception instance raised in the body, if any.
        :param tb: Traceback for the raised exception, if any.
        """
        ...
```

## File: `aegis_swr/openhands/events.py` (minimal forward-declaration)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    :return: ``datetime.now`` bound to UTC (never a naive timestamp).
    """
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class OpenHandsConnected(DomainEvent):
    """Emitted once when an OpenHands session is ready to serve requests (C10).

    **Forward-declared here** so ``process.py`` (Task 07.0) can emit it before
    Task 09.0 canonicalises the full ``openhands.*`` taxonomy — mirroring how
    ``openclaude/events.py`` was declared ahead of its canonical task. It
    **subclasses the live** :class:`~aegis_swr.core.events.DomainEvent` (the shape
    the bus actually dispatches on — a plain dataclass would reach zero
    subscribers). Task 09.0 must preserve both the subclassing and these field
    names and may only extend them.

    :ivar run_id: Investigation run id this session is bound to.
    :ivar server_url: Ready server endpoint the caller may dial; configuration,
        never incident payload (C13).
    :ivar mode: Lifecycle mode — ``"external"`` for a pre-running server,
        ``"managed"`` for an Aegis-started process.
    :ivar timestamp: Timezone-aware UTC time the connection was established.
    """

    event_type: ClassVar[str] = "openhands.connected"

    run_id: str
    server_url: str
    mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsDisconnected(DomainEvent):
    """Emitted once when an OpenHands session is torn down (C10).

    Forward-declared here (see :class:`OpenHandsConnected`); Task 09.0
    canonicalises it while preserving this shape.

    :ivar run_id: Investigation run id this session was bound to.
    :ivar reason: Short, payload-free reason string (e.g. ``"context_exit"``).
    :ivar timestamp: Timezone-aware UTC time the disconnect fired.
    """

    event_type: ClassVar[str] = "openhands.disconnected"

    run_id: str
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)
```

## Implementation notes

- **Mirror `OpenClaudeProcess` (0004 C6) closely.** The mode dispatch, the
  `server_url` guard (a private `Optional[str]` initialised `None`, set only
  inside `__aenter__`, raising `RuntimeError` — a programming error, not an
  availability failure — when read early), the exactly-once disconnect guard, the
  always-terminate invariant, the loopback-bind refusal, the stderr forwarder,
  and the SIGTERM→grace→SIGKILL teardown are all lifted from that proven module.
  Deviate only where the transport differs (URL/health-check instead of
  gRPC/port, no gRPC channel object).
- **External mode is the primary path (C8).** OpenHands is typically an
  already-running container; `auto_start=False` (default) health checks it and
  never spawns anything. `_enter_external` builds `OpenHandsClient` from settings
  only when none was injected, calls `health_check()` (which never raises and
  never leaks a raw library error — C3), and on `False` raises
  `OpenHandsUnavailableError`. It sets `server_url` **before** emitting
  `OpenHandsConnected` so a subscriber reacting to the event can safely read it.
- **Managed mode parity.** Where a deployment can launch the server as a
  subprocess, `_start_managed` uses `asyncio.create_subprocess_exec` (never
  `subprocess.Popen` in an async path — C13) with `stdout=DEVNULL`,
  `stderr=PIPE`, and a neutral cwd, starts the stderr forwarder, then awaits a
  TCP-accept readiness probe bounded by `connect_timeout_s`. Managed mode drives
  the *server* process; the server owns its own Docker sandbox runtime — this
  class never shells out to Docker itself.
- **Always-terminate invariant.** Structure `_start_managed` / `_enter_managed`
  so that once `create_subprocess_exec` returns a live process, any subsequent
  failure (port never opened, connect-emit subscriber raising, cancellation) runs
  `_stop_stderr_forwarder()` then `_terminate_managed()` before the exception
  leaves `__aenter__`. Both are idempotent so overlap with `__aexit__` cannot
  double-cancel or double-terminate. Catch `BaseException` on that guard so
  `CancelledError` is covered; always re-raise.
- **Readiness probe.** `_await_port_open` performs a cheap TCP connection to the
  resolved loopback host:port in a loop, `asyncio.sleep(_PORT_POLL_INTERVAL_S)`
  between attempts, giving up at `connect_timeout_s` with
  `OpenHandsUnavailableError`. A full `health_check()` may also be used once the
  port accepts, but the TCP-accept probe avoids a premature REST call.
- **Exactly-once events (C8, C10).** `OpenHandsConnected` is emitted only after
  the health check (external) or the port accepts (managed).
  `OpenHandsDisconnected` is emitted exactly once from `__aexit__`, after
  teardown, guarded by the shared `_disconnected` flag — including the
  exception-in-body and entry-raised-after-start cases.
- **stderr / SensitiveFilter (C13).** In managed mode only, the child's stderr is
  drained line-by-line and logged at `DEBUG` under the project-wide
  `SensitiveFilter`; stdout is `DEVNULL`. Never add an unfiltered sink; never log
  above `DEBUG`; a decode/log error inside the loop must not crash the manager
  (narrow catch, keep draining — no bare `except:`).
- **Forward-declared symbols.** `OpenHandsConnected` / `OpenHandsDisconnected`
  (in `openhands/events.py`, skeleton above) and `OpenHandsUnavailableError`
  (in `openhands/exceptions.py`, subtask 01) are declared by Task 07.0 and
  imported here; Task 09.0 canonicalizes them and must preserve these shapes.
  Import them; do not redefine.
- **AsyncExitStack registration (C4, deferred to Task 10.0).** This class does
  **not** register itself. The composition root (Task 10.0) calls
  `await stack.enter_async_context(process)` (non-dry-run only) so `__aexit__`
  — and thus `OpenHandsDisconnected` (C8) — always runs on app shutdown via
  RAII, exactly as `openclaude/composition.py` registers `OpenClaudeProcess`.
- **Dry-run (C13).** Dry-run is a composition-root axis, not this class's
  concern: under `dry_run` the process is simply **not entered** (no health
  check, no spawn, no `Connected`/`Disconnected`), mirroring how
  `build_code_agent` skips `enter_async_context` for OpenClaude.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- This is the **only** module that starts/stops/health-checks the OpenHands sidecar (C3, C8).
- `asyncio.create_subprocess_exec`, never `subprocess.Popen` in an async path; `asyncio.sleep` for readiness backoff, never `time.sleep` (C13).
- Managed mode **always** terminates the subprocess on exit, including the entry-raised-after-start case (C8).
- `OpenHandsConnected` emitted exactly once on successful entry (both modes); `OpenHandsDisconnected` exactly once on exit (both modes) (C8).
- External mode starts **no** process and issues **no** `create_subprocess_exec` call.
- Reading `.server_url` before `__aenter__` raises `RuntimeError`.
- Managed-mode stderr forwarded at `DEBUG` under `SensitiveFilter`; stdout discarded; no raw payload text is ever logged unredacted (C13).

## Success criteria

- [ ] Reading `.server_url` before `__aenter__` raises `RuntimeError`.
- [ ] With `auto_start=False` and a reachable server, `__aenter__` runs a health check, sets `server_url`, and emits exactly one `OpenHandsConnected` tagged `"external"`.
- [ ] With `auto_start=False` and an unreachable server, `__aenter__` raises `OpenHandsUnavailableError` and emits **no** `OpenHandsConnected`.
- [ ] External mode never calls `asyncio.create_subprocess_exec`.
- [ ] With `auto_start=True`, `__aenter__` spawns via `asyncio.create_subprocess_exec` (stdout `DEVNULL`, stderr piped), waits for the port with `asyncio.sleep` backoff, and emits `OpenHandsConnected` tagged `"managed"` only after the port accepts.
- [ ] The port never opening within `connect_timeout_s` raises `OpenHandsUnavailableError` **and** the started process is terminated before the exception propagates (verified via a mock/fake process).
- [ ] `__aexit__` sends SIGTERM, awaits within the grace period, escalates to `SIGKILL` only if still alive, and reaps the process (no zombie).
- [ ] `OpenHandsDisconnected` emitted exactly once on exit, including the exception-in-body case; the exception is not suppressed.
- [ ] An injected mock `OpenHandsClient` is used verbatim (no real client constructed) — the unit-test seam holds.
- [ ] Managed-mode stderr is drained to `DEBUG` under `SensitiveFilter`; the forwarder is canceled and awaited with no leaked `CancelledError`.
- [ ] No `subprocess.Popen` and no `time.sleep` anywhere in the module.
- [ ] `ruff check src/ tests/` - clean.

