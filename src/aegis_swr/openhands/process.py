"""OpenHands sidecar process lifecycle manager (Task 07.0, contract C8).

This module owns the OpenHands sidecar lifecycle as an async context manager,
mirroring :class:`~aegis_swr.openclaude.process.OpenClaudeProcess`'s proven shape
(0004 C6) closely. It is the only module that starts, stops, or health-checks the
OpenHands sidecar (C3). Two modes are selected by ``settings.auto_start``:
**external** (default; health-check an already-running server) and **managed**
(Aegis-started server process, where the deployment supports it).

OpenHands is normally an already-running container, so **external mode is the
primary path**. Managed mode launches the OpenHands *server* process, which owns
its own Docker-sandboxed runtime; this class **never** shells out to Docker
itself. Registration on the app ``AsyncExitStack`` is the composition root's job
(Task 10.0), exactly as ``OpenClaudeProcess`` is wired.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import tempfile
from types import TracebackType
from typing import Optional
from urllib.parse import urlsplit

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

# argv-token whitelist: a managed-mode argv value may contain only these
# characters. A leading ``-``, an ``=``, whitespace, or a control char is
# rejected at the argv boundary to defeat flag injection (mirrors OpenClaude).
_ARGV_TOKEN_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

# Explicit, neutral working directory for the spawned server so it never inherits
# an attacker-influenced cwd (and cwd is never folded onto PATH).
_SAFE_CWD = tempfile.gettempdir()

# Launch binary for the managed OpenHands server process. A bare command name
# resolved on the operator-controlled PATH (the managed path is exercised only
# where the deployment supports launching the server as a subprocess).
_SERVER_BINARY = "openhands"


def _is_loopback_host(host: str) -> bool:
    """Return whether *host* names the local loopback interface.

    :param host: The host portion of the resolved server URL.
    :return: ``True`` for ``localhost``, ``127.0.0.1``, or any ``127.*`` host;
        ``False`` for every other (including wildcard) address.
    """
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


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
        self._settings = settings
        self._bus = bus
        self._run_id = run_id
        self._client = client
        self._server_url: Optional[str] = None
        self._disconnected = False
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None

    @property
    def server_url(self) -> str:
        """Return the ready OpenHands server endpoint for the active session.

        :raises RuntimeError: If accessed before ``__aenter__`` has completed
            successfully (no endpoint is resolved yet).
        :return: The base server URL the caller / client should dial.
        """
        if self._server_url is None:
            raise RuntimeError(
                "OpenHandsProcess.server_url is not available until __aenter__ has "
                "completed; read it inside the 'async with' block"
            )
        return self._server_url

    async def __aenter__(self) -> OpenHandsProcess:
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
        if self._settings.auto_start:
            return await self._enter_managed()
        return await self._enter_external()

    async def _enter_external(self) -> OpenHandsProcess:
        """Health-check an already-running server and emit connect (C8).

        Resolves ``server_url`` from settings, builds a client from settings only
        when none was injected, and runs :meth:`OpenHandsClient.health_check`.
        Starts no subprocess. On success sets ``server_url`` first, then emits
        exactly one :class:`OpenHandsConnected` tagged ``"external"``.

        :raises OpenHandsUnavailableError: If ``server_url`` is unset or the
            health check reports the server unreachable.
        :return: ``self``, with ``server_url`` now readable.
        """
        server_url = self._settings.server_url
        if server_url is None:
            raise OpenHandsUnavailableError(
                "OpenHands server_url is not configured; the backend is not registered",
                retriable=False,
            )

        client = self._client
        if client is None:
            client = OpenHandsClient(self._settings)
            self._client = client

        # health_check() is a resilience boundary: it never raises for a normal
        # transport failure, returning False instead, and it never leaks a raw
        # library error (translation happens inside the client, C3).
        healthy = await client.health_check()
        if not healthy:
            raise OpenHandsUnavailableError(
                "OpenHands sidecar health check failed in external mode",
                server_url=server_url,
            )

        # Set server_url BEFORE emitting so a subscriber reacting to the connect
        # event can safely read it.
        self._server_url = server_url
        self._bus.publish(OpenHandsConnected(run_id=self._run_id, server_url=server_url, mode=_EXTERNAL_MODE))
        logger.debug("OpenHands external-mode session connected for run {}", self._run_id)
        return self

    async def _enter_managed(self) -> OpenHandsProcess:
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
        server_url = self._settings.server_url
        if server_url is None:
            raise OpenHandsUnavailableError(
                "OpenHands server_url is not configured; managed mode has no address to bind",
                retriable=False,
            )
        self._server_url = server_url

        await self._start_managed()

        # Extend the always-terminate invariant to cover the full span between
        # "process is live" and "__aenter__ returns self": if the connect emit
        # (a bus subscriber raising) or cancellation lands in the cooperative gap
        # after readiness, __aexit__ would NOT run (it only runs when __aenter__
        # returned), so the sidecar must be reaped here first. BaseException so
        # CancelledError is covered too; the exception is always re-raised.
        try:
            self._bus.publish(OpenHandsConnected(run_id=self._run_id, server_url=server_url, mode=_MANAGED_MODE))
            logger.debug("OpenHands managed-mode session connected for run {}", self._run_id)
            return self
        except BaseException:
            await self._stop_stderr_forwarder()
            await self._terminate_managed()
            raise

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
            before this propagates) or the bind address is unusable.
        """
        argv = self._build_argv()
        logger.debug("Spawning OpenHands managed server for run {}", self._run_id)
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=_SAFE_CWD,
        )
        # Start draining stderr immediately, once, right after the process is
        # live — before the readiness wait — so diagnostics emitted during
        # startup are captured and no stderr backpressure can stall the child.
        self._start_stderr_forwarder()
        try:
            await self._await_port_open()
        except BaseException:
            # Always-terminate invariant: once the process is live, any failure
            # (port never opened, cancellation) stops the forwarder and
            # terminates the process before the exception leaves __aenter__.
            # BaseException so CancelledError is covered too; the exception is
            # always re-raised, never swallowed. Both callees are idempotent so
            # the overlap with __aexit__ cannot double-cancel/double-terminate.
            await self._stop_stderr_forwarder()
            await self._terminate_managed()
            raise

    def _resolve_bind_address(self) -> tuple[str, int]:
        """Resolve the loopback ``host, port`` the managed server binds and we probe.

        Parses the resolved ``server_url`` (set once at managed-mode entry).
        Managed mode requires an explicit port and a loopback host; a wildcard or
        otherwise non-loopback host is refused rather than launching a server
        reachable off-box.

        :raises OpenHandsUnavailableError: If the endpoint is unset, carries no
            explicit port, or names a non-loopback host.
        :return: The ``(host, port)`` pair to bind and probe.
        """
        server_url = self._server_url
        if server_url is None:
            raise OpenHandsUnavailableError(
                "OpenHands server_url is not configured; managed mode has no address to bind",
                retriable=False,
            )
        parts = urlsplit(server_url)
        host = parts.hostname
        port = parts.port
        if host is None or port is None:
            raise OpenHandsUnavailableError(
                "OpenHands managed mode requires server_url to carry an explicit host and port",
                server_url=server_url,
                retriable=False,
            )
        if not _is_loopback_host(host):
            raise OpenHandsUnavailableError(
                "OpenHands managed mode refuses to bind a non-loopback host; use 127.0.0.1/localhost",
                server_url=server_url,
                retriable=False,
            )
        return host, port

    def _build_argv(self) -> list[str]:
        """Assemble the OpenHands server launch argv (managed mode).

        Derives the sandboxed-runtime selector from ``settings.runtime_mode`` and
        the bind host:port from the resolved ``server_url``, validating each value
        at the argv boundary (fail closed) exactly as ``OpenClaudeProcess`` does,
        so no value can be reparsed as a flag. The argv shape is
        assumed-pending-integration-test (Task 11.0).

        :raises OpenHandsUnavailableError: If the bind address is unusable
            (missing port or non-loopback host).
        :return: Argument vector for :func:`asyncio.create_subprocess_exec`.
        """
        host, port = self._resolve_bind_address()
        runtime = self._validate_argv_token(self._settings.runtime_mode, field="runtime_mode")
        return [
            _SERVER_BINARY,
            f"--runtime={runtime}",
            f"--host={host}",
            f"--port={port}",
        ]

    @staticmethod
    def _validate_argv_token(value: str, *, field: str) -> str:
        """Validate a single argv value at the boundary (fail closed).

        Accepts only ``\\A[A-Za-z0-9._-]+\\Z`` and additionally rejects a leading
        ``-`` (which would be re-parsed as a flag). The ``\\A``/``\\Z`` anchors
        (not ``^``/``$``) reject a value with a trailing newline. Never silently
        drops a bad value — raises so the spawn aborts before any process starts.

        :param value: A single argv value derived from settings.
        :param field: The originating settings field, for the error message.
        :raises OpenHandsUnavailableError: If *value* is not a safe single token.
        :return: *value* unchanged when it is a safe single token.
        """
        if not isinstance(value, str) or not value or value.startswith("-") or _ARGV_TOKEN_RE.match(value) is None:
            raise OpenHandsUnavailableError(
                f"OpenHands managed-mode {field} is not a safe argv token",
                retriable=False,
            )
        return value

    async def _await_port_open(self):
        """Poll the resolved loopback port until it accepts a TCP connection.

        Probes the same loopback ``host:port`` the server was told to bind,
        sleeping ``_PORT_POLL_INTERVAL_S`` between attempts with
        :func:`asyncio.sleep` (never :func:`time.sleep`). The cumulative wait is
        bounded by ``settings.connect_timeout_s``.

        :raises OpenHandsUnavailableError: On timeout before the port opens.
        """
        host, port = self._resolve_bind_address()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.connect_timeout_s
        while True:
            if await self._probe_port(host, port):
                logger.debug("OpenHands managed server port is accepting for run {}", self._run_id)
                return
            if loop.time() >= deadline:
                raise OpenHandsUnavailableError(
                    "OpenHands managed server port did not open within connect_timeout_s",
                    server_url=f"{host}:{port}",
                    retriable=True,
                )
            await asyncio.sleep(_PORT_POLL_INTERVAL_S)

    @staticmethod
    async def _probe_port(host: str, port: int) -> bool:
        """Attempt one TCP connect to *host*:*port*, reporting acceptance.

        A refused/unreachable port (``ConnectionRefusedError`` is an ``OSError``)
        is a normal not-yet-ready condition and yields ``False``; it never raises.
        On success the probe connection is closed immediately — no payload is sent
        or read.

        :param host: Loopback host to probe.
        :param port: TCP port to probe.
        :return: ``True`` if the port accepted the connection; ``False`` if it
            refused or was unreachable.
        """
        try:
            _, writer = await asyncio.open_connection(host, port)
        except OSError:
            logger.debug("OpenHands managed port is not accepting connections yet")
            return False
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            logger.debug("OpenHands managed port probe close raced with the server")
        return True

    def _start_stderr_forwarder(self):
        """Spawn the background task draining the managed child's stderr.

        Creates an :class:`asyncio.Task` running :meth:`_forward_stderr` and
        stores its handle for cancellation on every managed exit path. Called once
        after the subprocess is spawned; never called in external mode.
        """
        self._stderr_task = asyncio.create_task(self._forward_stderr())

    async def _forward_stderr(self):
        """Read child stderr line-by-line and log each at ``DEBUG`` (C13).

        Loops over ``process.stderr.readline()`` until EOF, decoding with
        ``errors="replace"`` and passing the line as a bound argument (never the
        format template) to ``logger.debug`` so the loguru ``SensitiveFilter`` on
        every sink redacts it. A per-line decode/read failure is caught narrowly
        and the loop keeps draining; ``asyncio.CancelledError`` is not caught so
        it propagates to the cancel path.
        """
        process = self._process
        if process is None or process.stderr is None:
            return
        stream = process.stderr
        while True:
            try:
                line = await stream.readline()
                if not line:
                    return  # EOF — the child closed stderr.
                text = line.decode(errors="replace").rstrip()
                logger.debug("OpenHands managed server stderr [run {}]: {}", self._run_id, text)
            except (ValueError, OSError, asyncio.LimitOverrunError) as exc:
                # Narrow, non-fatal: a per-line decode/log failure or a transient
                # stream error must not kill the manager. Keep draining. A broad
                # ``except Exception`` is forbidden (X002) and would wrongly
                # swallow ``CancelledError``.
                logger.debug("OpenHands server stderr drain: transient read error [run {}]: {}", self._run_id, exc)
                continue

    async def _stop_stderr_forwarder(self):
        """Cancel the stderr-forwarding task and await its clean shutdown.

        Idempotent; safe when the forwarder was never started (external mode) or
        already finished. Awaits the cancelled task inside
        :func:`contextlib.suppress` so the resulting
        :class:`asyncio.CancelledError` never leaks and no pending-task warning
        appears.
        """
        task = self._stderr_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _terminate_managed(self):
        """Terminate the owned subprocess: SIGTERM, grace wait, then SIGKILL.

        Operates only on the stored asyncio process handle — never ``os.kill`` on
        a raw pid — and guards every step on ``returncode is None``. Sends
        ``SIGTERM``, awaits exit within ``_TERMINATE_GRACE_S``, and on timeout
        escalates to ``SIGKILL``; either way the process is reaped so no zombie
        remains. Idempotent: a no-op when never started or already dead.
        """
        process = self._process
        if process is None or process.returncode is not None:
            return
        logger.debug("Terminating OpenHands managed server for run {}", self._run_id)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_S)
        except asyncio.TimeoutError:
            logger.debug("OpenHands managed server ignored SIGTERM; escalating to SIGKILL")
            if process.returncode is None:
                try:
                    process.kill()
                except OSError:
                    # A SIGCHLD arriving between the returncode check and kill()
                    # can surface as ProcessLookupError/OSError — the child
                    # already died, so treat it as success and still reap below.
                    logger.debug("OpenHands managed server already exited before SIGKILL")
            await process.wait()

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
        if self._settings.auto_start:
            # Cancel the stderr forwarder before reaping the process; both are
            # idempotent, so this is safe even when an entry-raised guard already
            # ran them. External mode never started a forwarder, so the stop is a
            # no-op there (``_stderr_task`` stays ``None``).
            await self._stop_stderr_forwarder()
            await self._terminate_managed()
        if self._disconnected:
            return None
        self._disconnected = True
        self._bus.publish(OpenHandsDisconnected(run_id=self._run_id, reason=_DISCONNECT_REASON))
        logger.debug("OpenHands session disconnected for run {}", self._run_id)
        return None
