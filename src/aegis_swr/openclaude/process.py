"""OpenClaude sidecar process lifecycle manager (Task 03.0).

This module owns the OpenClaude sidecar lifecycle as an async context manager.
It is the only module that starts, stops, or health-checks the OpenClaude
Node.js subprocess (contract C3). Two modes are selected by
``settings.auto_start``: **external** (default; health-check only - implemented
here) and **managed** (Aegis-started subprocess - arrives in subtask 02).

**Port-0 free-port selection (managed mode only).** When the operator
configures ``grpc_url`` with a wildcard port (``host:0``), the OS assigns a
concrete free port *before* the child is spawned: a temporary socket is bound to
port ``0``, the assigned port is read, and the socket is closed (RAII). The
resolved concrete endpoint is stored once, up-front, as the single source of
truth every consumer reads (child bind flag, caller-visible ``grpc_url``, and
the readiness-probe target all agree). This "bind-0, close, hand the number off"
pattern carries an inherent, well-understood **TOCTOU race**: another process
could claim the released port before the child binds it. This is an accepted,
standard limitation and is *not* eliminated here (the child is a separate
Node.js process and cannot portably inherit a Python-held fd); a failed child
bind simply surfaces via the subtask-02 readiness probe as
``OpenClaudeUnavailableError``. **Prefer a fixed, concrete port in production.**
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import socket
import tempfile
from types import TracebackType
from typing import Optional

from loguru import logger

from aegis_swr.core.events import EventBus
from aegis_swr.openclaude.config import OpenClaudeConfigError, OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis_swr.openclaude.exceptions import OpenClaudeUnavailableError
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient

_EXTERNAL_MODE = "external"
_MANAGED_MODE = "managed"
_DISCONNECT_REASON = "context_exit"

# Grace period (seconds) between SIGTERM and the SIGKILL escalation during
# managed-sidecar teardown. The default of 5.0s lets the Node.js sidecar flush
# and exit cleanly on SIGTERM before we force-kill a process that ignored it.
_TERMINATE_GRACE_S: float = 5.0

# Fixed backoff (seconds) between successive TCP-accept readiness probes while
# waiting for the managed sidecar's gRPC port to open. ``asyncio.sleep`` only -
# never ``time.sleep`` (C9).
_PORT_POLL_INTERVAL_S: float = 0.05

# argv-token whitelist: a single allowlist value may contain only these
# characters. A leading ``-``, a ``,`` CSV separator, an ``=``, whitespace, or a
# control char is rejected at the argv boundary to defeat flag injection (C7).
_ARGV_TOKEN_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

# Loopback hosts the managed sidecar is permitted to bind/probe. A wildcard
# address (``0.0.0.0``/``::``) is never acceptable - it would expose the
# tool-executing sidecar off-box.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})

# Explicit, neutral working directory for the spawned sidecar so it never
# inherits an attacker-influenced cwd (and cwd is never folded onto PATH).
_SAFE_CWD = tempfile.gettempdir()


def _is_loopback_host(host: str) -> bool:
    """Return whether *host* names the local loopback interface.

    :param host: The host portion of a bare ``host[:port]`` endpoint.
    :return: ``True`` for ``localhost``, ``127.0.0.1``, or any ``127.*`` host;
        ``False`` for every other (including wildcard) address.
    """
    return host in _LOOPBACK_HOSTS or host.startswith("127.")


class OpenClaudeProcess:
    """Async context manager owning the OpenClaude sidecar lifecycle (C6).

    This is the only module that starts, stops, or health-checks the OpenClaude
    Node.js subprocess (C3). It supports two modes selected by
    ``settings.auto_start``: **external** (default; health-check only, this
    subtask) and **managed** (subtask 02). ``grpc_url`` is only readable inside
    the ``async with`` block; accessing it earlier raises ``RuntimeError``.

    :ivar _settings: Environment-sourced OpenClaude configuration.
    :ivar _bus: Shared :class:`EventBus` for lifecycle event emission.
    :ivar _run_id: Correlation id attached to every emitted event.
    :ivar _client: Health-check client; injected for tests or built from
        ``settings`` at entry.
    :ivar _grpc_url: Resolved endpoint, ``None`` until ``__aenter__`` succeeds.
    :ivar _disconnected: Idempotency guard so disconnect emits at most once.
    :ivar _process: The owned managed-mode subprocess handle, or ``None`` in
        external mode / before a managed spawn. Kept after readiness so
        subtask 04 can attach the stderr-forwarding task.
    :ivar _stderr_task: Background task draining the managed child's stderr, or
        ``None`` in external mode / before the managed spawn. Cancelled and
        awaited on every managed exit path so no task is left pending.
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
        self._settings = settings
        self._bus = bus
        self._run_id = run_id
        self._client = client
        self._grpc_url: Optional[str] = None
        self._disconnected = False
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task[None]] = None

    @property
    def grpc_url(self) -> str:
        """Return the ready gRPC endpoint for the active session.

        :raises RuntimeError: If accessed before ``__aenter__`` has completed
            successfully (no endpoint is resolved yet).
        :return: Bare ``host[:port]`` the caller should dial.
        """
        if self._grpc_url is None:
            raise RuntimeError(
                "OpenClaudeProcess.grpc_url is not available until __aenter__ has "
                "completed; read it inside the 'async with' block"
            )
        return self._grpc_url

    async def __aenter__(self) -> OpenClaudeProcess:
        """Enter the context, dispatching on ``settings.auto_start``.

        The external branch (``auto_start=False``) health-checks a pre-running
        sidecar and starts no process. The managed branch (``auto_start=True``)
        spawns the sidecar via :func:`asyncio.create_subprocess_exec`, waits for
        its gRPC port to open, and emits :class:`OpenClaudeConnected`. If the
        port never opens the started process is terminated before the exception
        leaves this method (always-terminate invariant).

        :raises OpenClaudeUnavailableError: If the external-mode health check
            fails, or if the managed sidecar's port does not open in time.
        :raises OpenClaudeConfigError: If managed-mode argv construction rejects
            a hostile allowlist value or an invalid binary path.
        :return: ``self``, with ``grpc_url`` now readable.
        """
        if self._settings.auto_start:
            return await self._enter_managed()
        return await self._enter_external()

    async def _enter_external(self) -> OpenClaudeProcess:
        """Health-check an already-running sidecar and emit connect (C6).

        Resolves ``grpc_url`` from settings, builds a client from settings only
        when none was injected, and runs
        :meth:`OpenClaudeGrpcClient.health_check`. Starts no subprocess and
        issues no ``create_subprocess_exec`` call. On success sets ``grpc_url``
        first, then emits exactly one :class:`OpenClaudeConnected`.

        :raises OpenClaudeUnavailableError: If ``grpc_url`` is unset or the
            health check reports the endpoint unreachable.
        :return: ``self``, with ``grpc_url`` now readable.
        """
        grpc_url = self._settings.grpc_url
        if grpc_url is None:
            raise OpenClaudeUnavailableError(
                "OpenClaude grpc_url is not configured; the backend is not registered",
                retriable=False,
            )

        client = self._client
        if client is None:
            client = OpenClaudeGrpcClient(self._settings)
            self._client = client

        # health_check() is a resilience boundary: it never raises for a normal
        # transport failure, returning False instead, and it never leaks a raw
        # gRPC status (translation happens inside the client, C3).
        healthy = await client.health_check()
        if not healthy:
            raise OpenClaudeUnavailableError(
                "OpenClaude sidecar health check failed in external mode",
                grpc_url=grpc_url,
            )

        # Set grpc_url BEFORE emitting so a subscriber reacting to the connect
        # event can safely read it.
        self._grpc_url = grpc_url
        self._bus.publish(OpenClaudeConnected(run_id=self._run_id, grpc_url=grpc_url, mode=_EXTERNAL_MODE))
        logger.debug("OpenClaude external-mode session connected for run {}", self._run_id)
        return self

    async def _enter_managed(self) -> OpenClaudeProcess:
        """Spawn the managed sidecar, await readiness, and emit connect (C6).

        Resolves the endpoint **once** up front via :meth:`_resolve_grpc_url`
        (substituting a concrete free port for a ``host:0`` wildcard) and stores
        it in ``_grpc_url`` *before* argv construction and the spawn - making
        that field the single source of truth every downstream consumer reads
        (the child bind flag, the caller-visible ``grpc_url``, and the readiness
        probe all reference the same concrete port). Delegates the spawn-and-wait
        to :meth:`_start_managed` (which enforces the always-terminate
        invariant), then publishes exactly one :class:`OpenClaudeConnected`
        tagged ``"managed"``.

        :raises OpenClaudeUnavailableError: If ``grpc_url`` is unset, the port
            never opens (the started process is terminated first), or the bind
            address is non-loopback.
        :raises OpenClaudeConfigError: If argv construction rejects a value.
        :return: ``self``, with ``grpc_url`` now readable.
        """
        # Resolve the port ONCE, before argv construction and the spawn, so a
        # ``host:0`` wildcard maps to a single concrete free port that the child
        # bind flag, ``grpc_url``, and the readiness probe all share. Re-parsing
        # ``settings.grpc_url`` per-consumer would pick a *different* free port
        # each time, so every consumer reads this stored value instead.
        resolved = self._resolve_grpc_url()
        self._grpc_url = resolved

        await self._start_managed()

        # Extend the always-terminate invariant to cover the full span between
        # "process is live" and "__aenter__ returns self": if the connect emit
        # (a bus subscriber raising) or cancellation lands in the cooperative gap
        # after readiness, __aexit__ would NOT run (it only runs when __aenter__
        # returned), so the sidecar must be reaped here first. BaseException so
        # CancelledError is covered too; the exception is always re-raised.
        try:
            self._bus.publish(OpenClaudeConnected(run_id=self._run_id, grpc_url=resolved, mode=_MANAGED_MODE))
            logger.debug("OpenClaude managed-mode session connected for run {}", self._run_id)
            return self
        except BaseException:
            await self._stop_stderr_forwarder()
            await self._terminate_managed()
            raise

    async def _start_managed(self) -> None:
        """Launch the sidecar and block until its gRPC port is accepting.

        Builds and validates the argv (binary + allowlist flags + loopback bind
        address), starts the process via :func:`asyncio.create_subprocess_exec`
        with ``stdout`` discarded and ``stderr`` piped, then awaits readiness via
        :meth:`_await_port_open`. Any failure *after* the process is live -
        including cancellation - runs :meth:`_terminate_managed` before the
        exception propagates, so an entry-raised-after-start never orphans a
        sidecar.

        :raises OpenClaudeUnavailableError: If the port does not open within
            ``settings.connect_timeout_s`` (the started process is terminated
            before this propagates).
        :raises OpenClaudeConfigError: If argv validation rejects a value.
        """
        argv = self._build_argv()
        logger.debug("Spawning OpenClaude managed sidecar for run {}", self._run_id)
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            cwd=_SAFE_CWD,
        )
        # Start draining stderr immediately, once, right after the process is
        # live - before the readiness wait - so diagnostics emitted during
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

    def _start_stderr_forwarder(self) -> None:
        """Spawn the background task that drains the managed child's stderr.

        Creates an :class:`asyncio.Task` running :meth:`_forward_stderr` and
        stores its handle in ``_stderr_task`` for cancellation on every managed
        exit path. Called once, right after the subprocess is spawned in managed
        mode; never called in external mode.
        """
        self._stderr_task = asyncio.create_task(self._forward_stderr())

    async def _forward_stderr(self) -> None:
        """Read the child's stderr line-by-line and log each at ``DEBUG`` (C9).

        Loops over ``process.stderr.readline()`` until EOF (an empty ``bytes``),
        decoding each line with ``errors="replace"`` and stripping the trailing
        newline, then emits it via the project ``logger`` at ``DEBUG`` only - so
        the loguru ``SensitiveFilter`` on every configured sink redacts it and no
        unfiltered sink is introduced. The line is passed as a bound argument (a
        value, never the format template) so untrusted text cannot inject format
        directives. stdout is never read (it is ``DEVNULL``); only stderr is
        drained.

        A per-line decode/log failure - including a ``ValueError`` /
        ``LimitOverrunError`` from ``readline`` on an over-long line - is caught
        narrowly and the loop keeps draining, so a single bad line never crashes
        the lifecycle manager. ``asyncio.CancelledError`` (a ``BaseException``)
        is deliberately *not* caught, so it propagates to the cancel path in
        :meth:`_stop_stderr_forwarder`.
        """
        process = self._process
        if process is None or process.stderr is None:
            return
        stream = process.stderr
        while True:
            try:
                line = await stream.readline()
                if not line:
                    return  # EOF - the child closed stderr.
                text = line.decode(errors="replace").rstrip()
                logger.debug("OpenClaude managed sidecar stderr [run {}]: {}", self._run_id, text)
            except (ValueError, OSError, asyncio.LimitOverrunError):
                # Narrow, non-fatal: a per-line decode/log failure or a transient
                # stream error must not kill the manager. Keep draining.
                # ``readline()`` re-raises an over-long line as ``ValueError``
                # (CPython's ``StreamReader.readline`` catches the internal
                # ``LimitOverrunError`` and re-raises it as ``ValueError``), so
                # that case is covered by ``ValueError`` today.
                # ``asyncio.LimitOverrunError`` (whose MRO is
                # ``LimitOverrunError -> Exception`` - it is NOT a ``ValueError``
                # subclass) is listed defensively to future-proof a switch to
                # ``readuntil()``, which surfaces it directly. A broad
                # ``except Exception`` is forbidden (X002) and would wrongly
                # swallow ``CancelledError``.
                continue

    async def _stop_stderr_forwarder(self) -> None:
        """Cancel the stderr-forwarding task and await its clean shutdown.

        Idempotent: a no-op when the forwarder was never started (external mode,
        ``_stderr_task is None``) or already finished. Otherwise cancels the task
        and awaits it inside :func:`contextlib.suppress` so the resulting
        :class:`asyncio.CancelledError` never leaks and no "Task was destroyed
        but it is pending" warning can appear.
        """
        task = self._stderr_task
        if task is None or task.done():
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def _build_argv(self) -> list[str]:
        """Assemble and validate the OpenClaude launch argv (C7).

        Emits the allowlist flags in the **joined single-token** form
        (``--allowed-tools=v1,v2`` / ``--bash-allowlist=v1,v2``) so no value can
        be reparsed as a separate flag, and appends the resolved loopback gRPC
        bind address. Every ``allowed_tools`` and ``bash_allowlist`` value is run
        through :meth:`_validate_argv_token` (fail closed) before it reaches the
        argv, and the binary is resolved via :meth:`_resolve_binary`.

        :raises OpenClaudeConfigError: If any allowlist value or the binary path
            is rejected.
        :raises OpenClaudeUnavailableError: If the bind address is unusable
            (missing port or non-loopback host).
        :return: Argument vector for :func:`asyncio.create_subprocess_exec`.
        """
        binary = self._resolve_binary()
        host, port = self._resolve_bind_address()
        allowed = ",".join(
            self._validate_argv_token(value, field="allowed_tools") for value in self._settings.allowed_tools
        )
        bash = ",".join(
            self._validate_argv_token(value, field="bash_allowlist") for value in self._settings.bash_allowlist
        )
        return [
            binary,
            f"--allowed-tools={allowed}",
            f"--bash-allowlist={bash}",
            f"--grpc-address={host}:{port}",
        ]

    @staticmethod
    def _validate_argv_token(value: str, *, field: str) -> str:
        """Validate a single allowlist value at the argv boundary (fail closed).

        Accepts only ``\\A[A-Za-z0-9._-]+\\Z`` and additionally rejects a leading
        ``-`` (which would be re-parsed as a flag). The ``\\A``/``\\Z`` anchors
        (not ``^``/``$``) reject a value with a trailing newline, which ``$``
        would otherwise admit. A ``,``, ``=``, whitespace, or control char is
        already excluded by the pattern. Never silently drops a bad value -
        raises so the spawn aborts before any process starts.

        :param value: A single ``allowed_tools`` / ``bash_allowlist`` entry.
        :param field: The originating settings field, for the error message.
        :raises OpenClaudeConfigError: If *value* is not a safe single token.
        :return: *value* unchanged when it is a safe single token.
        """
        if not isinstance(value, str) or not value:
            raise OpenClaudeConfigError(field=field, reason="allowlist entry must be a non-empty string")
        if value.startswith("-"):
            raise OpenClaudeConfigError(
                field=field,
                reason="allowlist entry must not begin with '-' (would be parsed as a flag)",
            )
        if _ARGV_TOKEN_RE.match(value) is None:
            raise OpenClaudeConfigError(
                field=field,
                reason="allowlist entry may contain only [A-Za-z0-9._-] (no ',', '=', whitespace, or control chars)",
            )
        return value

    def _resolve_binary(self) -> str:
        """Resolve the launch binary from ``settings.process_binary`` only (C1).

        A bare command name (no path separator, e.g. the ``"openclaude"``
        default) is returned unchanged for PATH resolution under the documented
        operator-controlled-PATH assumption. A value containing a path separator
        must be an absolute path to an existing regular file; a relative or
        non-existent path is rejected. The environment is never read directly.

        :raises OpenClaudeConfigError: If a path-form binary is relative or does
            not resolve to an existing regular file.
        :return: The binary name or absolute path to hand to the spawn.
        """
        binary = self._settings.process_binary
        has_separator = os.sep in binary or (os.altsep is not None and os.altsep in binary)
        if has_separator:
            if not os.path.isabs(binary):
                raise OpenClaudeConfigError(
                    field="process_binary",
                    reason="a path (containing a separator) must be absolute, not relative",
                )
            if not os.path.isfile(binary):
                raise OpenClaudeConfigError(
                    field="process_binary",
                    reason="path does not resolve to an existing regular file",
                )
        return binary

    def _resolve_grpc_url(self) -> str:
        """Resolve ``settings.grpc_url`` to a concrete dialable endpoint.

        Parses the validated bare ``host[:port]`` from settings. **Only** when
        the port component is exactly ``0`` (wildcard) is a free port chosen via
        :meth:`_pick_free_port` and substituted; a concrete port, or an absent
        port, passes through unchanged. Called once at managed-mode entry -
        before :meth:`_build_argv` and the spawn - so the stored result is the
        single source of truth the child bind flag, the caller-visible
        ``grpc_url``, and the readiness probe all share. Loopback enforcement is
        applied later, on the resolved value, by :meth:`_resolve_bind_address`.

        :raises OpenClaudeUnavailableError: If ``grpc_url`` is unset (managed
            mode has no address to bind).
        :return: Bare ``host:port`` with a concrete (non-zero) port when the
            input named port ``0``; otherwise the configured value verbatim.
        """
        grpc_url = self._settings.grpc_url
        if grpc_url is None:
            raise OpenClaudeUnavailableError(
                "OpenClaude grpc_url is not configured; managed mode has no address to bind",
                retriable=False,
            )
        host, sep, port_text = grpc_url.partition(":")
        # Port-0 wildcard is the ONLY trigger; a concrete or absent port is used
        # verbatim (host defaulting is the caller's concern).
        if sep and port_text == "0":
            return f"{host}:{self._pick_free_port(host)}"
        return grpc_url

    @staticmethod
    def _pick_free_port(host: str) -> int:
        """Ask the OS for a currently-free TCP port on *host* (RAII probe).

        Binds a temporary :func:`socket.socket` to port ``0``, reads the
        OS-assigned port from ``getsockname``, and lets the ``with`` block close
        the socket before returning - releasing it so the child can bind it. No
        ``SO_REUSEADDR`` linger is set. See the module docstring for the
        inherent, accepted TOCTOU race between this release and the child's bind.

        :param host: Host to bind the probe socket on (e.g. ``localhost``).
        :return: An OS-assigned free TCP port number.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            return probe.getsockname()[1]

    def _resolve_bind_address(self) -> tuple[str, int]:
        """Resolve the loopback ``host, port`` the sidecar binds and we probe.

        Reads the **already-resolved** ``_grpc_url`` (set once at managed-mode
        entry by :meth:`_resolve_grpc_url`), *not* ``settings.grpc_url`` - so a
        ``host:0`` wildcard is not re-resolved to a different free port per call.
        Managed mode requires an explicit port and a loopback host; a wildcard or
        otherwise non-loopback host is refused rather than spawning a sidecar
        reachable off-box.

        :raises OpenClaudeUnavailableError: If the endpoint is unset, carries no
            explicit port, or names a non-loopback host.
        :return: The ``(host, port)`` pair to bind and probe.
        """
        grpc_url = self._grpc_url
        if grpc_url is None:
            raise OpenClaudeUnavailableError(
                "OpenClaude grpc_url is not configured; managed mode has no address to bind",
                retriable=False,
            )
        host, sep, port_text = grpc_url.partition(":")
        if not sep or not port_text:
            raise OpenClaudeUnavailableError(
                "OpenClaude managed mode requires grpc_url to carry an explicit port to bind and probe",
                grpc_url=grpc_url,
                retriable=False,
            )
        if not _is_loopback_host(host):
            raise OpenClaudeUnavailableError(
                "OpenClaude managed mode refuses to bind a non-loopback host; use 127.0.0.1/localhost",
                grpc_url=grpc_url,
                retriable=False,
            )
        return host, int(port_text)

    async def _await_port_open(self) -> None:
        """Poll the resolved loopback gRPC port until it accepts a TCP connect.

        Probes the same loopback ``host:port`` the sidecar was told to bind,
        sleeping ``_PORT_POLL_INTERVAL_S`` between attempts with
        :func:`asyncio.sleep` (never :func:`time.sleep`). The cumulative wait is
        bounded by ``settings.connect_timeout_s``.

        :raises OpenClaudeUnavailableError: On timeout before the port opens.
        """
        host, port = self._resolve_bind_address()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.connect_timeout_s
        while True:
            if await self._probe_port(host, port):
                logger.debug("OpenClaude managed sidecar port is accepting for run {}", self._run_id)
                return
            if loop.time() >= deadline:
                raise OpenClaudeUnavailableError(
                    "OpenClaude managed sidecar port did not open within connect_timeout_s",
                    grpc_url=f"{host}:{port}",
                    retriable=True,
                )
            await asyncio.sleep(_PORT_POLL_INTERVAL_S)

    @staticmethod
    async def _probe_port(host: str, port: int) -> bool:
        """Attempt one TCP connect to *host*:*port*, reporting acceptance.

        A refused/unreachable port (``ConnectionRefusedError`` is an
        ``OSError``) is a normal not-yet-ready condition and yields ``False``;
        it never raises. On success the probe connection is closed immediately -
        no payload is sent or read.

        :param host: Loopback host to probe.
        :param port: TCP port to probe.
        :return: ``True`` if the port accepted the connection; ``False`` if it
            refused or was unreachable.
        """
        try:
            _, writer = await asyncio.open_connection(host, port)
        except OSError:
            logger.debug("OpenClaude managed port is not accepting connections yet")
            return False
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            logger.debug("OpenClaude managed port probe close raced with the sidecar")
        return True

    async def _terminate_managed(self) -> None:
        """Terminate the owned subprocess: SIGTERM, grace wait, then SIGKILL.

        Operates only on the stored asyncio process handle - never ``os.kill``
        on a raw pid - and guards every step on ``returncode is None``. Sends
        ``SIGTERM`` (:meth:`terminate`), awaits exit within
        ``_TERMINATE_GRACE_S``, and on timeout escalates to ``SIGKILL``
        (:meth:`kill`); either way the process is reaped (``wait`` awaited) so no
        zombie remains. Idempotent: a no-op when never started or already dead.
        """
        process = self._process
        if process is None or process.returncode is not None:
            return
        logger.debug("Terminating OpenClaude managed sidecar for run {}", self._run_id)
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=_TERMINATE_GRACE_S)
        except asyncio.TimeoutError:
            logger.debug("OpenClaude managed sidecar ignored SIGTERM; escalating to SIGKILL")
            if process.returncode is None:
                try:
                    process.kill()
                except OSError:
                    # A SIGCHLD arriving between the returncode check and kill()
                    # can surface as ProcessLookupError/OSError on some POSIX
                    # platforms - the child already died, so treat it as success
                    # and still reap below. Narrow ``OSError`` only (X002).
                    logger.debug("OpenClaude managed sidecar already exited before SIGKILL")
            await process.wait()

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        """Exit the context, emitting :class:`OpenClaudeDisconnected` once.

        In managed mode the owned subprocess is terminated first
        (:meth:`_terminate_managed`, idempotent), so the disconnect event is
        emitted only *after* teardown completes. In external mode there is no
        owned process to terminate. Either way the disconnect fires exactly once,
        guarded by the shared idempotency flag. Never suppresses an in-flight
        exception (returns ``None``).

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
        self._bus.publish(OpenClaudeDisconnected(run_id=self._run_id, reason=_DISCONNECT_REASON))
        logger.debug("OpenClaude session disconnected for run {}", self._run_id)
        return None
