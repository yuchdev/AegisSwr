"""Unit tests for :mod:`aegis_swr.openhands.process`.

These tests drive :class:`OpenHandsProcess` in both external mode
(``auto_start=False``) and managed mode (``auto_start=True``) with an injected
mock :class:`OpenHandsClient` and a faked ``asyncio.create_subprocess_exec`, so
no live OpenHands server, subprocess, or socket is ever required. A real
:class:`EventBus` with a capturing subscriber records lifecycle events.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import pytest
from loguru import logger

import aegis_swr.openhands.process as process_mod
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import OpenHandsConnected, OpenHandsDisconnected
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError
from aegis_swr.openhands.process import OpenHandsProcess

_SERVER_URL = "http://localhost:3000"
_MANAGED_URL = "http://127.0.0.1:3000"
_RUN_ID = "run-openhands-proc"


class _MockClient:
    """Mock OpenHands client exposing only the async ``health_check`` seam."""

    def __init__(self, *, healthy: bool = True, raises: Optional[BaseException] = None):
        """Store the scripted health verdict and optional error to raise."""
        self._healthy = healthy
        self._raises = raises
        self.health_calls = 0

    async def health_check(self) -> bool:
        """Return the scripted health verdict or raise the scripted error."""
        self.health_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._healthy


class _Capture:
    """Capturing :class:`DomainEvent` subscriber recording every event."""

    def __init__(self):
        """Initialise with an empty captured-event list."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent):
        """Append *event* to the captured-event list."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Return captured events of exactly *event_type*."""
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_capture() -> tuple[EventBus, _Capture]:
    """Return a bus subscribed to :class:`DomainEvent` with a capture sink."""
    bus = EventBus()
    capture = _Capture()
    bus.subscribe(DomainEvent, capture)
    return bus, capture


def _settings(*, server_url: Optional[str] = _SERVER_URL, auto_start: bool = False) -> OpenHandsSettings:
    """Build external-mode settings without reading the environment."""
    return OpenHandsSettings(server_url=server_url, auto_start=auto_start)


def _managed_settings(
    *,
    server_url: Optional[str] = _MANAGED_URL,
    connect_timeout_s: int = 10,
) -> OpenHandsSettings:
    """Build ``auto_start=True`` settings without reading the environment."""
    return OpenHandsSettings(server_url=server_url, auto_start=True, connect_timeout_s=connect_timeout_s)


# ---------------------------------------------------------------------------
# External mode
# ---------------------------------------------------------------------------


async def test_server_url_before_entry_raises_runtime_error():
    """[Unit] process: reading ``server_url`` before entry raises ``RuntimeError``.

    Scenario: a process is constructed but ``__aenter__`` has not run; the
    ``server_url`` property is read.

    Boundaries: only the property guard is exercised.

    On failure, first check: the property must reject reads before entry resolves
    the endpoint.
    """
    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(RuntimeError):
        _ = proc.server_url


async def test_reachable_server_emits_single_connected_and_exposes_url():
    """[Unit] process: a reachable server emits one connect and exposes the url.

    Scenario: external mode enters with a healthy mock client.

    Boundaries: the injected client's ``health_check`` is the only seam.

    On failure, first check: exactly one external ``OpenHandsConnected`` with the
    matching run id/url must be published, and ``server_url`` must be readable.
    """
    bus, capture = _bus_with_capture()
    client = _MockClient(healthy=True)
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=client)

    async with proc as entered:
        assert entered is proc
        assert proc.server_url == _SERVER_URL
        connected = capture.of(OpenHandsConnected)
        assert len(connected) == 1
        event = connected[0]
        assert isinstance(event, OpenHandsConnected)
        assert event.run_id == _RUN_ID
        assert event.server_url == _SERVER_URL
        assert event.mode == "external"

    assert client.health_calls == 1


async def test_unreachable_server_raises_and_emits_no_connected():
    """[Unit] process: an unhealthy server raises and emits no connect event.

    Scenario: the mock client reports ``healthy=False``; entry is attempted.

    Boundaries: only the ``health_check`` verdict drives the outcome.

    On failure, first check: entry must raise ``OpenHandsUnavailableError`` and
    publish neither connect nor disconnect.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=False))

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenHandsConnected) == []
    assert capture.of(OpenHandsDisconnected) == []


async def test_unset_server_url_raises_unavailable():
    """[Unit] process: an unset ``server_url`` raises unavailable at entry.

    Scenario: external-mode settings carry ``server_url=None``.

    Boundaries: the endpoint-resolution guard runs before any health check.

    On failure, first check: a missing endpoint must raise
    ``OpenHandsUnavailableError`` and publish no connect event.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(server_url=None), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenHandsConnected) == []


async def test_external_mode_never_spawns_subprocess(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: external mode never spawns a subprocess.

    Scenario: ``asyncio.create_subprocess_exec`` is spied; external mode enters
    and exits cleanly.

    Boundaries: the spawn primitive is monkeypatched.

    On failure, first check: external mode must record zero spawn calls and one
    health check.
    """
    bus, _ = _bus_with_capture()
    client = _MockClient(healthy=True)

    calls: list[tuple] = []

    async def _spy(*args: object, **kwargs: object):
        """Record a spawn attempt; external mode must never invoke this."""
        calls.append((args, kwargs))  # pragma: no cover - must never run

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy)

    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=client)
    async with proc:
        pass

    assert calls == []
    assert client.health_calls == 1


async def test_exit_emits_single_disconnected():
    """[Unit] process: clean ``__aexit__`` emits exactly one disconnect.

    Scenario: external mode enters and exits normally.

    Boundaries: only the exit path is under test.

    On failure, first check: exactly one ``OpenHandsDisconnected`` with reason
    ``context_exit`` and the correct run id must be emitted.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass

    disconnected = capture.of(OpenHandsDisconnected)
    assert len(disconnected) == 1
    event = disconnected[0]
    assert isinstance(event, OpenHandsDisconnected)
    assert event.run_id == _RUN_ID
    assert event.reason == "context_exit"


async def test_exit_is_idempotent_on_repeated_call():
    """[Unit] process: a repeated ``__aexit__`` does not double-emit disconnect.

    Scenario: after a normal exit, ``__aexit__`` is invoked a second time.

    Boundaries: exercises the exit-idempotency guard only.

    On failure, first check: the second exit must return ``None`` and leave the
    disconnect count at one.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass
    result = await proc.__aexit__(None, None, None)

    assert result is None
    assert len(capture.of(OpenHandsDisconnected)) == 1


async def test_exception_in_body_still_emits_disconnected_and_propagates():
    """[Unit] process: a body exception still emits one disconnect and propagates.

    Scenario: an error is raised inside the ``async with`` body after connect.

    Boundaries: only exit-on-error handling is exercised.

    On failure, first check: the body error must propagate while exactly one
    connect and one disconnect are emitted.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    class _BodyError(RuntimeError):
        """Sentinel error raised inside the ``async with`` body."""

    with pytest.raises(_BodyError):
        async with proc:
            raise _BodyError("boom")

    assert len(capture.of(OpenHandsConnected)) == 1
    assert len(capture.of(OpenHandsDisconnected)) == 1


async def test_injected_client_used_verbatim_no_real_client(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: an injected client is used verbatim; no real client built.

    Scenario: the ``OpenHandsClient`` constructor is patched to explode; entry
    runs with an injected mock client.

    Boundaries: the constructor patch proves the real client class is untouched.

    On failure, first check: entry must not construct ``OpenHandsClient`` and must
    use the injected client's ``health_check``.
    """

    def _boom(*args: object, **kwargs: object):
        """Fail if the real client constructor is invoked while injected."""
        raise AssertionError("OpenHandsClient must not be constructed when injected")

    monkeypatch.setattr(process_mod, "OpenHandsClient", _boom)

    bus, _ = _bus_with_capture()
    client = _MockClient(healthy=True)
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=client)

    async with proc:
        pass

    assert client.health_calls == 1


async def test_client_built_from_settings_when_not_injected(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: with no injected client, one is built from settings.

    Scenario: the client factory is patched to record settings; entry runs with
    no injected client.

    Boundaries: the factory patch captures the exact settings object passed.

    On failure, first check: entry must construct the client from the same
    settings instance and emit one connect event.
    """
    built: list[OpenHandsSettings] = []

    def _factory(settings: OpenHandsSettings) -> _MockClient:
        """Record *settings* and return a healthy mock client."""
        built.append(settings)
        return _MockClient(healthy=True)

    monkeypatch.setattr(process_mod, "OpenHandsClient", _factory)

    bus, capture = _bus_with_capture()
    settings = _settings()
    proc = OpenHandsProcess(settings, bus, _RUN_ID)

    async with proc:
        assert proc.server_url == _SERVER_URL

    assert built == [settings]
    assert len(capture.of(OpenHandsConnected)) == 1


async def test_events_carry_only_ids_and_status_strings():
    """[Unit] process: emitted events carry only ids/config/status, no payload (C13).

    Scenario: external mode enters and exits; the field sets of the connect and
    disconnect events are inspected.

    Boundaries: enforces the no-incident-payload constraint on events.

    On failure, first check: the connect/disconnect ``vars`` must be exactly the
    id/endpoint/mode/reason/timestamp fields, nothing more.
    """
    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass

    connected = capture.of(OpenHandsConnected)[0]
    disconnected = capture.of(OpenHandsDisconnected)[0]
    assert isinstance(connected, OpenHandsConnected)
    assert isinstance(disconnected, OpenHandsDisconnected)
    assert set(vars(connected)) == {"run_id", "server_url", "mode", "timestamp"}
    assert set(vars(disconnected)) == {"run_id", "reason", "timestamp"}
    assert connected.mode == "external"
    assert disconnected.reason == "context_exit"


# ---------------------------------------------------------------------------
# Managed mode (auto_start=True)
# ---------------------------------------------------------------------------


class _FakeStreamReader:
    """Fake ``asyncio.StreamReader`` yielding scripted stderr lines then blocking."""

    def __init__(self, lines: Optional[list[bytes]] = None):
        """Queue *lines* and initialise the exhaustion/block events and counter."""
        self._lines = list(lines or [])
        self.readline_calls = 0
        self.exhausted = asyncio.Event()
        self._block = asyncio.Event()

    async def readline(self) -> bytes:
        """Return the next scripted line, then signal EOF-drain and block."""
        self.readline_calls += 1
        if self._lines:
            return self._lines.pop(0)
        self.exhausted.set()
        await self._block.wait()
        return b""  # pragma: no cover - only reached if the block event is set


class _FakeProcess:
    """Fake ``asyncio.subprocess.Process`` recording teardown signal calls."""

    def __init__(
        self,
        *,
        terminate_exits: bool = True,
        exit_code: int = 0,
        stderr_lines: Optional[list[bytes]] = None,
    ):
        """Configure the reap-on-terminate behaviour, exit code, and stderr lines."""
        self.returncode: Optional[int] = None
        self._terminate_exits = terminate_exits
        self._exit_code = exit_code
        self._exited = asyncio.Event()
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0
        self.stdout = None
        self.stderr = _FakeStreamReader(stderr_lines)

    def terminate(self):
        """Record a SIGTERM; reap the process when ``terminate_exits`` is set."""
        self.terminate_calls += 1
        if self._terminate_exits:
            self.returncode = self._exit_code
            self._exited.set()

    def kill(self):
        """Record a SIGKILL and reap the process immediately."""
        self.kill_calls += 1
        self.returncode = -9
        self._exited.set()

    async def wait(self) -> int:
        """Block until the process has been reaped, then return its code."""
        self.wait_calls += 1
        await self._exited.wait()
        assert self.returncode is not None
        return self.returncode


def _spawn_recorder(monkeypatch: pytest.MonkeyPatch, fake: _FakeProcess) -> list[tuple[tuple, dict]]:
    """Monkeypatch ``asyncio.create_subprocess_exec`` to return *fake*."""
    calls: list[tuple[tuple, dict]] = []

    async def _spawn(*args: object, **kwargs: object) -> _FakeProcess:
        """Record the spawn ``(args, kwargs)`` and return the fake process."""
        calls.append((args, kwargs))
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


def _patch_probe(monkeypatch: pytest.MonkeyPatch, proc: OpenHandsProcess, *, opens: bool):
    """Replace *proc*'s TCP readiness probe with a scripted verdict."""

    async def _probe(host: str, port: int) -> bool:
        """Return the scripted *opens* verdict for the readiness probe."""
        return opens

    monkeypatch.setattr(proc, "_probe_port", _probe)


async def test_managed_mode_spawns_once_with_devnull_stdout_pipe_stderr(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: managed entry spawns once with DEVNULL stdout / PIPE stderr.

    Scenario: managed mode enters with a fake process and an always-open probe.

    Boundaries: the spawn primitive and readiness probe are faked.

    On failure, first check: exactly one spawn of the ``openhands`` binary with a
    ``--runtime=``/``--host=``/``--port=`` argv, DEVNULL stdout, PIPE stderr, and a
    managed connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        assert proc.server_url == _MANAGED_URL

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "openhands"
    assert "--runtime=docker" in args
    assert "--host=127.0.0.1" in args
    assert "--port=3000" in args
    assert kwargs["stdout"] is asyncio.subprocess.DEVNULL
    assert kwargs["stderr"] is asyncio.subprocess.PIPE
    assert "cwd" in kwargs

    connected = capture.of(OpenHandsConnected)
    assert len(connected) == 1
    assert connected[0].mode == "managed"
    assert connected[0].server_url == _MANAGED_URL


async def test_managed_non_loopback_host_raises_no_spawn(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a non-loopback server host is refused before spawning.

    Scenario: managed settings bind ``http://10.0.0.5:3000``.

    Boundaries: only loopback binds are permitted for a managed sidecar.

    On failure, first check: entry must raise ``OpenHandsUnavailableError`` with
    no recorded spawn and no connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(server_url="http://10.0.0.5:3000"), bus, _RUN_ID)

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []
    assert capture.of(OpenHandsConnected) == []


async def test_managed_missing_port_raises_no_spawn(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a server url without an explicit port is refused before spawn.

    Scenario: managed settings bind ``http://127.0.0.1`` with no port.

    Boundaries: exercises the endpoint-parsing guard before spawn.

    On failure, first check: entry must raise ``OpenHandsUnavailableError`` with
    no recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(server_url="http://127.0.0.1"), bus, _RUN_ID)

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_managed_unset_server_url_raises_no_spawn(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: managed mode with no server url never spawns.

    Scenario: managed settings carry ``server_url=None``.

    Boundaries: exercises the address-required guard for managed mode.

    On failure, first check: entry must raise ``OpenHandsUnavailableError`` with
    no recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(server_url=None), bus, _RUN_ID)

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_managed_port_timeout_terminates_then_raises(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a port that never opens terminates the server then raises.

    Scenario: managed mode spawns but the readiness probe always reports closed
    with a 1s timeout.

    Boundaries: a failed readiness must reap the child before surfacing the error.

    On failure, first check: exactly one terminate and at least one wait must run,
    the return code must be set, and no connect/disconnect event should be emitted.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(connect_timeout_s=1), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=False)

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert fake.terminate_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode is not None
    assert capture.of(OpenHandsConnected) == []
    assert capture.of(OpenHandsDisconnected) == []


async def test_managed_exit_sigterm_without_kill(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: clean managed exit sends SIGTERM and never SIGKILL.

    Scenario: the fake process exits on terminate; managed mode enters and exits.

    Boundaries: a graceful child needs no SIGKILL.

    On failure, first check: exactly one terminate, zero kills, at least one wait,
    and one disconnect with reason ``context_exit``.
    """
    fake = _FakeProcess(terminate_exits=True)
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 0
    assert fake.wait_calls >= 1
    disconnected = capture.of(OpenHandsDisconnected)
    assert len(disconnected) == 1
    assert disconnected[0].reason == "context_exit"


async def test_managed_exit_escalates_to_sigkill(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a child ignoring SIGTERM within grace is escalated to SIGKILL.

    Scenario: the fake process never exits on terminate and the grace period is
    shortened to 0.01s; managed mode exits normally.

    Boundaries: enforces the grace-period escalation contract.

    On failure, first check: exactly one terminate and one kill, the return code
    must be ``-9``, and one disconnect must be emitted.
    """
    fake = _FakeProcess(terminate_exits=False)
    _spawn_recorder(monkeypatch, fake)
    monkeypatch.setattr(process_mod, "_TERMINATE_GRACE_S", 0.01)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode == -9
    assert len(capture.of(OpenHandsDisconnected)) == 1


async def test_managed_subscriber_raising_after_readiness_terminates_sidecar(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: a connect-publish error after readiness reaps the sidecar.

    Scenario: the port opens immediately but ``bus.publish`` raises at the connect
    event — the gap after "process live" but before entry returns.

    Boundaries: the entry-raised guard must terminate the sidecar itself since
    ``__aexit__`` only runs after a successful entry.

    On failure, first check: exactly one terminate and at least one wait must run
    and the return code must be set (no orphaned live process).
    """

    class _SubscriberError(RuntimeError):
        """Sentinel error raised when the connect event is published."""

    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()

    def _boom(event: DomainEvent):
        """Raise a sentinel error when the connect event is published."""
        raise _SubscriberError("publish blew up on connect")

    monkeypatch.setattr(bus, "publish", _boom)

    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    with pytest.raises(_SubscriberError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert fake.terminate_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode is not None


async def test_managed_entry_raised_after_start_stops_stderr_forwarder(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: an entry failure after start also stops the forwarder.

    Scenario: the port never opens so entry raises after the forwarder started.

    Boundaries: proves the entry-failure path cancels+awaits the forwarder
    alongside the always-terminate invariant.

    On failure, first check: the forwarder must be done and cancelled, exactly one
    terminate must have run, and no connect event should be emitted.
    """
    fake = _FakeProcess(stderr_lines=[b"boot\n"])
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(connect_timeout_s=1), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=False)

    with pytest.raises(OpenHandsUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    task = proc._stderr_task
    assert task is not None
    assert task.done()
    assert task.cancelled()
    assert fake.terminate_calls == 1
    assert capture.of(OpenHandsConnected) == []


async def test_managed_stderr_drained_line_by_line_at_debug(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: managed stderr is drained line-by-line at DEBUG only (C13).

    Scenario: the fake process scripts two stderr lines; a DEBUG sink captures the
    forwarded lines while managed mode drains them.

    Boundaries: forwarded diagnostics stay at DEBUG and carry only the rstripped
    text.

    On failure, first check: both lines must appear rstripped in captured DEBUG
    output.
    """
    fake = _FakeProcess(stderr_lines=[b"first diagnostic\n", b"second diagnostic\n"])
    _spawn_recorder(monkeypatch, fake)

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="DEBUG")

    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    try:
        async with proc:
            await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)
    finally:
        logger.remove(sink_id)

    joined = "".join(captured)
    assert "first diagnostic" in joined
    assert "second diagnostic" in joined


async def test_managed_exit_cancels_and_awaits_stderr_forwarder(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: exit cancels and awaits the stderr forwarder with no leak.

    Scenario: the child keeps stderr open so the forwarder is still pending at
    exit.

    Boundaries: proves clean task teardown — no leaked ``CancelledError``.

    On failure, first check: the forwarder must be pending inside the context and
    both done and cancelled after exit.
    """
    fake = _FakeProcess(stderr_lines=[b"line\n"])
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)
        task = proc._stderr_task
        assert task is not None
        assert not task.done()

    assert task.done()
    assert task.cancelled()


async def test_external_mode_never_starts_stderr_forwarder():
    """[Unit] process: external mode starts no forwarder and stop is a safe no-op.

    Scenario: external mode enters and exits; the forwarder handle is inspected.

    Boundaries: proves the forwarder is a managed-only concern.

    On failure, first check: ``_stderr_task`` must stay ``None`` and
    ``_stop_stderr_forwarder`` must not raise.
    """
    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        assert proc._stderr_task is None

    assert proc._stderr_task is None
    await proc._stop_stderr_forwarder()
    assert proc._stderr_task is None


async def test_terminate_managed_idempotent_when_never_started():
    """[Unit] process: terminating with no owned process is a safe no-op.

    Scenario: ``_terminate_managed`` is called on a managed process that never
    entered.

    Boundaries: exercises the no-owned-process guard directly.

    On failure, first check: the call must not raise and ``_process`` must remain
    ``None``.
    """
    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)

    await proc._terminate_managed()

    assert proc._process is None


async def test_probe_port_true_when_a_listener_accepts():
    """[Unit] process: the real TCP probe returns True against a live listener.

    Scenario: a loopback server is started on an ephemeral port and
    ``_probe_port`` targets it.

    Boundaries: exercises the real ``_probe_port`` against a real socket.

    On failure, first check: the probe must return ``True`` while a listener
    accepts on the bound port.
    """

    async def _handle(_: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Accept and immediately close the probe connection."""
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert await OpenHandsProcess._probe_port("127.0.0.1", port) is True
    finally:
        server.close()
        await server.wait_closed()


async def test_probe_port_false_when_nothing_listens():
    """[Unit] process: the real TCP probe returns False for a refused port.

    Scenario: a loopback server is started then torn down, freeing its port.

    Boundaries: exercises the real ``_probe_port`` against a closed port.

    On failure, first check: the probe must return ``False`` when nothing listens.
    """

    async def _noop(_: asyncio.StreamReader, __: asyncio.StreamWriter):
        """Never invoked; the listener is torn down before any probe."""
        pass  # pragma: no cover - never invoked; the listener is torn down first

    server = await asyncio.start_server(_noop, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    assert await OpenHandsProcess._probe_port("127.0.0.1", port) is False


def test_module_has_no_forbidden_spawn_primitives():
    """[Unit] process: the module never uses shell spawn, raw Popen, or sleep.

    Scenario: the module source is read and scanned for forbidden primitives.

    Boundaries: a static source scan, not a runtime behaviour test.

    On failure, first check: the source must contain none of ``subprocess.Popen``,
    ``create_subprocess_shell``, ``shell=True``, ``import time``, or
    ``time.sleep(``.
    """
    source = Path(process_mod.__file__).read_text(encoding="utf-8")
    assert "subprocess.Popen" not in source
    assert "create_subprocess_shell" not in source
    assert "shell=True" not in source
    assert "import time" not in source
    assert "time.sleep(" not in source


async def test_managed_stderr_passed_as_bound_argument_not_fstring(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: managed stderr is a bound argument, never an f-string (C13).

    Scenario: the fake process scripts a stderr line carrying a unique marker;
    ``logger.debug`` is recorded while managed mode drains it.

    Boundaries: proves the untrusted line reaches loguru as a bound *argument*
    (so ``SensitiveFilter`` can redact it and no format directive can be
    injected), not concatenated into the format template.

    On failure, first check: the marker must appear only in the recorded call's
    positional *args*, and the template must carry a ``{}`` placeholder rather
    than the inlined marker.
    """
    marker = "STDERR-MARKER-c3"
    fake = _FakeProcess(stderr_lines=[marker.encode() + b"\n"])
    _spawn_recorder(monkeypatch, fake)

    calls: list[tuple] = []

    def _debug(template: object, *args: object, **kwargs: object):
        """Record each ``logger.debug`` (template, args) invocation."""
        calls.append((template, args))

    monkeypatch.setattr(process_mod.logger, "debug", _debug)

    bus, _ = _bus_with_capture()
    proc = OpenHandsProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    stderr_calls = [(template, args) for template, args in calls if "stderr" in str(template)]
    assert stderr_calls, "expected a forwarded stderr debug record"
    template, args = stderr_calls[0]
    # The untrusted line is a bound argument, not baked into the template.
    assert marker in str(args[-1])
    assert marker not in str(template)
    assert "{}" in str(template)
