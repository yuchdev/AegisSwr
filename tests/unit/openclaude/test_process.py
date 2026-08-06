"""Unit tests for :mod:`aegis_swr.openclaude.process` (external mode).

These tests drive :class:`OpenClaudeProcess` in its default external mode
(``auto_start=False``) with an injected mock :class:`OpenClaudeGrpcClient`
exposing an async ``health_check`` and a real :class:`EventBus` with a capturing
subscriber, so no live OpenClaude process or gRPC channel is required.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Optional

import pytest

import aegis_swr.openclaude.process as process_mod
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.config import OpenClaudeConfigError, OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis_swr.openclaude.exceptions import OpenClaudeUnavailableError
from aegis_swr.openclaude.process import OpenClaudeProcess

_GRPC_URL = "localhost:50051"
_RUN_ID = "run-abc123"


class _MockClient:
    """Mock gRPC client exposing only the async ``health_check`` seam.

    Records how many times ``health_check`` was invoked so tests can assert the
    injected instance was used verbatim (no real client was constructed).
    """

    def __init__(self, *, healthy: bool = True, raises: Optional[BaseException] = None):
        """Store the scripted health verdict and optional error to raise.

        :param healthy: value returned by ``health_check`` when it does not raise.
        :param raises: when set, ``health_check`` raises this instead of returning.
        """
        self._healthy = healthy
        self._raises = raises
        self.health_calls = 0

    async def health_check(self) -> bool:
        """Return the scripted health verdict or raise the scripted error."""
        self.health_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._healthy


def _settings(*, grpc_url: Optional[str] = _GRPC_URL, auto_start: bool = False) -> OpenClaudeSettings:
    """Build settings for external mode without reading the environment."""
    return OpenClaudeSettings(grpc_url=grpc_url, auto_start=auto_start)


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


async def test_grpc_url_before_entry_raises_runtime_error():
    """[Unit] process: reading ``grpc_url`` before entry raises ``RuntimeError``.

    Scenario: a process is constructed but ``__aenter__`` has not run; the
    ``grpc_url`` property is read.

    Boundaries: only the property guard is exercised; no client, spawn, or bus
    publish occurs.

    On failure, first check: the ``grpc_url`` property must reject reads before
    the endpoint is resolved at entry.
    """
    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(RuntimeError):
        _ = proc.grpc_url


async def test_reachable_endpoint_emits_single_connected_and_exposes_url():
    """[Unit] process: a reachable endpoint emits one connect and exposes the url.

    Scenario: external mode enters with a healthy mock client; the connect event
    and ``grpc_url`` are inspected inside the context.

    Boundaries: the injected client's ``health_check`` is the only external seam;
    the bus is real.

    On failure, first check: exactly one ``OpenClaudeConnected`` with mode
    ``external`` and matching run id/url should be published on entry.
    """
    bus, capture = _bus_with_capture()
    client = _MockClient(healthy=True)
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=client)

    async with proc as entered:
        assert entered is proc
        assert proc.grpc_url == _GRPC_URL
        connected = capture.of(OpenClaudeConnected)
        assert len(connected) == 1
        event = connected[0]
        assert isinstance(event, OpenClaudeConnected)
        assert event.run_id == _RUN_ID
        assert event.grpc_url == _GRPC_URL
        assert event.mode == "external"

    assert client.health_calls == 1


async def test_unreachable_endpoint_raises_and_emits_no_connected():
    """[Unit] process: an unhealthy endpoint raises and emits no connect event.

    Scenario: the mock client reports ``healthy=False``; entry is attempted.

    Boundaries: only ``health_check`` verdict drives the outcome; no spawn path.

    On failure, first check: entry must raise ``OpenClaudeUnavailableError`` and
    publish neither connect nor disconnect (``__aexit__`` never runs).
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=False))

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []
    # __aexit__ is not driven by ``async with`` when __aenter__ raises.
    assert capture.of(OpenClaudeDisconnected) == []


async def test_health_check_raising_unavailable_propagates_and_emits_no_connected():
    """[Unit] process: a health check raising unavailable propagates unchanged.

    Scenario: ``health_check`` raises ``OpenClaudeUnavailableError``; entry is
    attempted.

    Boundaries: only the client seam raises; the error is not wrapped or masked.

    On failure, first check: the original error must propagate and no connect
    event should be published.
    """
    bus, capture = _bus_with_capture()
    boom = OpenClaudeUnavailableError("refused", grpc_url=_GRPC_URL, status_code="UNAVAILABLE")
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(raises=boom))

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []


async def test_unset_grpc_url_raises_unavailable():
    """[Unit] process: an unset ``grpc_url`` raises unavailable at entry.

    Scenario: external-mode settings carry ``grpc_url=None``; entry is attempted.

    Boundaries: the endpoint-resolution guard is exercised before any health check.

    On failure, first check: a missing endpoint must raise
    ``OpenClaudeUnavailableError`` and publish no connect event.
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(grpc_url=None), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []


async def test_external_mode_never_spawns_subprocess(monkeypatch: pytest.MonkeyPatch):
    """[Unit] process: external mode never spawns a subprocess.

    Scenario: ``asyncio.create_subprocess_exec`` is spied; external mode enters
    and exits cleanly.

    Boundaries: the spawn primitive is monkeypatched; the injected client's
    ``health_check`` is the only real work.

    On failure, first check: external mode must record zero spawn calls and
    exactly one health check.
    """
    bus, _ = _bus_with_capture()
    client = _MockClient(healthy=True)

    calls: list[tuple] = []

    async def _spy(*args: object, **kwargs: object):
        """Record a spawn attempt; external mode must never invoke this."""
        calls.append((args, kwargs))  # pragma: no cover - must never run

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy)

    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=client)
    async with proc:
        pass

    assert calls == []
    assert client.health_calls == 1


async def test_exit_emits_single_disconnected():
    """[Unit] process: clean ``__aexit__`` emits exactly one disconnect.

    Scenario: external mode enters and exits normally; disconnect events are
    inspected.

    Boundaries: only the exit path is under test; the client is healthy.

    On failure, first check: exactly one ``OpenClaudeDisconnected`` with reason
    ``context_exit`` and the correct run id should be emitted.
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass

    disconnected = capture.of(OpenClaudeDisconnected)
    assert len(disconnected) == 1
    event = disconnected[0]
    assert isinstance(event, OpenClaudeDisconnected)
    assert event.run_id == _RUN_ID
    assert event.reason == "context_exit"


async def test_exit_is_idempotent_on_repeated_call():
    """[Unit] process: a repeated ``__aexit__`` does not double-emit disconnect.

    Scenario: after a normal exit, ``__aexit__`` is invoked a second time
    directly.

    Boundaries: exercises the exit-idempotency guard only.

    On failure, first check: the second exit must return ``None`` and leave the
    disconnect count at one.
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass
    # Simulate a re-entrant / double exit.
    result = await proc.__aexit__(None, None, None)

    assert result is None
    assert len(capture.of(OpenClaudeDisconnected)) == 1


async def test_exception_in_body_still_emits_disconnected_and_propagates():
    """[Unit] process: a body exception still emits one disconnect and propagates.

    Scenario: an error is raised inside the ``async with`` body after a
    successful connect.

    Boundaries: only exit-on-error handling is exercised; the client is healthy.

    On failure, first check: the body error must propagate while exactly one
    connect and one disconnect are emitted.
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    class _BodyError(RuntimeError):
        """Sentinel error raised inside the ``async with`` body."""

    with pytest.raises(_BodyError):
        async with proc:
            raise _BodyError("boom")

    assert len(capture.of(OpenClaudeConnected)) == 1
    assert len(capture.of(OpenClaudeDisconnected)) == 1


async def test_injected_client_used_verbatim_no_real_client(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: an injected client is used verbatim; no real client built.

    Scenario: the ``OpenClaudeGrpcClient`` constructor is patched to explode;
    entry runs with an injected mock client.

    Boundaries: the constructor patch proves the real client class is never
    touched when a client is injected.

    On failure, first check: entry must not construct ``OpenClaudeGrpcClient``
    and must use the injected client's ``health_check``.
    """

    def _boom(*args: object, **kwargs: object):
        """Fail if the real client constructor is invoked while injected."""
        raise AssertionError("OpenClaudeGrpcClient must not be constructed when injected")

    monkeypatch.setattr(process_mod, "OpenClaudeGrpcClient", _boom)

    bus, _ = _bus_with_capture()
    client = _MockClient(healthy=True)
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=client)

    async with proc:
        pass

    assert client.health_calls == 1


async def test_client_built_from_settings_when_not_injected(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: with no injected client, one is built from settings.

    Scenario: the client factory is patched to record settings; entry runs with
    no injected client.

    Boundaries: the factory patch captures the exact settings object passed.

    On failure, first check: entry must construct the client from the same
    settings instance and emit one connect event.
    """
    built: list[OpenClaudeSettings] = []

    def _factory(settings: OpenClaudeSettings) -> _MockClient:
        """Record *settings* and return a healthy mock client."""
        built.append(settings)
        return _MockClient(healthy=True)

    monkeypatch.setattr(process_mod, "OpenClaudeGrpcClient", _factory)

    bus, capture = _bus_with_capture()
    settings = _settings()
    proc = OpenClaudeProcess(settings, bus, _RUN_ID)

    async with proc:
        assert proc.grpc_url == _GRPC_URL

    assert built == [settings]
    assert len(capture.of(OpenClaudeConnected)) == 1


async def test_events_carry_only_ids_and_status_strings():
    """[Unit] process: emitted events carry only ids/config/status, no payload.

    Scenario: external mode enters and exits; the field sets of the connect and
    disconnect events are inspected.

    Boundaries: enforces constraint C9 - events must not carry incident payload
    text, only correlation ids and status strings.

    On failure, first check: the connect/disconnect ``vars`` must be exactly the
    id/endpoint/mode/reason/timestamp fields, nothing more.
    """
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass

    connected = capture.of(OpenClaudeConnected)[0]
    disconnected = capture.of(OpenClaudeDisconnected)[0]
    assert isinstance(connected, OpenClaudeConnected)
    assert isinstance(disconnected, OpenClaudeDisconnected)
    # Only correlation id, endpoint (config), mode, and reason string are carried.
    assert set(vars(connected)) == {"run_id", "grpc_url", "mode", "timestamp"}
    assert set(vars(disconnected)) == {"run_id", "reason", "timestamp"}
    assert connected.mode == "external"
    assert disconnected.reason == "context_exit"


# ---------------------------------------------------------------------------
# Managed mode (auto_start=True) - subtask 02
# ---------------------------------------------------------------------------


_MANAGED_URL = "127.0.0.1:50051"


class _FakeStreamReader:
    """Fake ``asyncio.StreamReader`` yielding scripted stderr lines then EOF.

    Each :meth:`readline` returns the next queued line; once the queue drains it
    sets :attr:`exhausted` (so a test can await deterministic completion) and
    then blocks forever on an event that is never set, modelling a live child
    that keeps stderr open - so the forwarder task stays pending until it is
    cancelled on context exit. Records :attr:`readline_calls` for assertions.
    """

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
        # Block as a live child would (stderr open, no more output) so the
        # forwarder task remains pending until it is cancelled at __aexit__.
        await self._block.wait()
        return b""  # pragma: no cover - only reached if the block event is set


class _FakeProcess:
    """Fake ``asyncio.subprocess.Process`` recording teardown signal calls.

    Models the SIGTERM/SIGKILL contract: :meth:`terminate` reaps the process
    when ``terminate_exits`` is set, otherwise only :meth:`kill` does, so a test
    can exercise the grace-period escalation path deterministically. Its
    :attr:`stderr` is a :class:`_FakeStreamReader` so subtask-04 stderr
    forwarding can drain it line-by-line.
    """

    def __init__(
        self,
        *,
        terminate_exits: bool = True,
        exit_code: int = 0,
        stderr_lines: Optional[list[bytes]] = None,
    ):
        """Configure the reap-on-terminate behaviour, exit code, and stderr lines.

        :param terminate_exits: when True, ``terminate`` reaps the process.
        :param exit_code: the return code recorded on a clean terminate.
        :param stderr_lines: scripted stderr lines the fake reader yields.
        """
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


def _managed_settings(
    *,
    grpc_url: Optional[str] = _MANAGED_URL,
    bash_allowlist: Optional[list[str]] = None,
    connect_timeout_s: int = 10,
) -> OpenClaudeSettings:
    """Build ``auto_start=True`` settings without reading the environment."""
    kwargs: dict[str, object] = {
        "grpc_url": grpc_url,
        "auto_start": True,
        "connect_timeout_s": connect_timeout_s,
    }
    if bash_allowlist is not None:
        kwargs["bash_allowlist"] = bash_allowlist
    return OpenClaudeSettings(**kwargs)


def _spawn_recorder(
    monkeypatch: pytest.MonkeyPatch,
    fake: _FakeProcess,
) -> list[tuple[tuple, dict]]:
    """Monkeypatch ``asyncio.create_subprocess_exec`` to return *fake*.

    :return: A list that records ``(args, kwargs)`` of each spawn call.
    """
    calls: list[tuple[tuple, dict]] = []

    async def _spawn(*args: object, **kwargs: object) -> _FakeProcess:
        """Record the spawn ``(args, kwargs)`` and return the fake process."""
        calls.append((args, kwargs))
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


def _patch_probe(monkeypatch: pytest.MonkeyPatch, proc: OpenClaudeProcess, *, opens: bool):
    """Replace *proc*'s TCP readiness probe with a scripted verdict."""

    async def _probe(host: str, port: int) -> bool:
        """Return the scripted *opens* verdict for the readiness probe."""
        return opens

    monkeypatch.setattr(proc, "_probe_port", _probe)


async def test_managed_mode_spawns_once_with_joined_allowlist_flags(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: managed entry spawns once with joined single-token flags.

    Scenario: managed mode enters with a fake process and an always-open probe;
    the recorded spawn argv and kwargs are inspected.

    Boundaries: the spawn primitive and readiness probe are faked; argv assembly
    and the connect event are the subject.

    On failure, first check: exactly one spawn using single-token
    ``--allowed-tools=``/``--bash-allowlist=``/``--grpc-address=`` flags, DEVNULL
    stdout, PIPE stderr, and a managed connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        assert proc.grpc_url == _MANAGED_URL

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "openclaude"
    assert "--allowed-tools=Read,Grep,Glob,Bash" in args
    assert "--bash-allowlist=gtags,global,semgrep,rg,find,cat" in args
    assert f"--grpc-address={_MANAGED_URL}" in args
    # Single-token form: never the two-token "--flag value" split.
    assert "--allowed-tools" not in args
    assert "--bash-allowlist" not in args
    assert kwargs["stdout"] is asyncio.subprocess.DEVNULL
    assert kwargs["stderr"] is asyncio.subprocess.PIPE
    assert "cwd" in kwargs

    connected = capture.of(OpenClaudeConnected)
    assert len(connected) == 1
    assert connected[0].mode == "managed"
    assert connected[0].grpc_url == _MANAGED_URL


async def test_managed_process_handle_stored_for_subtask_04(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: the spawned process handle is retained for stderr forwarding.

    Scenario: managed mode enters with a fake process; the internal ``_process``
    handle and its stderr reader are inspected inside the context.

    Boundaries: only handle retention is checked; teardown is out of scope.

    On failure, first check: ``_process`` must be the exact spawned fake and its
    stderr reader must be present.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        assert proc._process is fake
        assert fake.stderr is not None


@pytest.mark.parametrize(
    "hostile",
    ["--dangerously-skip", "rg=evil", "a,b", "rm rf", "bad\ttab"],
)
async def test_managed_hostile_bash_allowlist_fails_closed_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
    hostile: str,
):
    """[Unit] process: a hostile bash-allowlist value aborts entry before spawn.

    Scenario: managed settings carry a hostile ``bash_allowlist`` token
    (flag-like, comma, equals, space, or tab); entry is attempted.

    Boundaries: enforces constraint C7 - the argv boundary must fail closed
    before ``create_subprocess_exec`` is reached.

    On failure, first check: entry must raise ``OpenClaudeConfigError`` with zero
    recorded spawns and no connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(bash_allowlist=["rg", hostile]), bus, _RUN_ID)

    with pytest.raises(OpenClaudeConfigError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []
    assert capture.of(OpenClaudeConnected) == []


def test_validate_argv_token_rejects_hostile_values_for_both_fields():
    """[Unit] process: the argv token helper fails closed for both allowlist fields.

    Scenario: ``_validate_argv_token`` is called with hostile tokens for both
    ``allowed_tools`` and ``bash_allowlist`` and with a clean token.

    Boundaries: exercises the pure validation helper directly, no process entry.

    On failure, first check: every hostile token must raise
    ``OpenClaudeConfigError`` while a plain ``rg`` passes through unchanged.
    """
    for field in ("allowed_tools", "bash_allowlist"):
        for bad in ("--flag", "a,b", "k=v", "has space", "", "ctrl\x00"):
            with pytest.raises(OpenClaudeConfigError):
                OpenClaudeProcess._validate_argv_token(bad, field=field)
    assert OpenClaudeProcess._validate_argv_token("rg", field="bash_allowlist") == "rg"


def test_validate_argv_token_rejects_trailing_newline_but_accepts_plain():
    """[Unit] process: a trailing newline is rejected by the start/end anchors.

    Scenario: ``_validate_argv_token`` is given a value with a trailing newline
    and a plain ``rg`` token.

    Boundaries: regression guard for the anchor choice - in non-MULTILINE mode a
    dollar anchor matches before a trailing newline and would leak a control char,
    so absolute string anchors are required.

    On failure, first check: the newline token must raise ``OpenClaudeConfigError``
    while the plain token passes.
    """
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeProcess._validate_argv_token("rg\n", field="bash_allowlist")
    assert OpenClaudeProcess._validate_argv_token("rg", field="bash_allowlist") == "rg"


async def test_managed_bash_allowlist_trailing_newline_fails_closed_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a newline in bash-allowlist aborts entry with no spawn.

    Scenario: managed settings carry ``bash_allowlist=["rg", "rg\\n"]``; entry is
    attempted.

    Boundaries: end-to-end proof that the token validation reaches the spawn
    guard before ``create_subprocess_exec``.

    On failure, first check: entry must raise ``OpenClaudeConfigError`` with no
    recorded spawn and no connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(bash_allowlist=["rg", "rg\n"]), bus, _RUN_ID)

    with pytest.raises(OpenClaudeConfigError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []
    assert capture.of(OpenClaudeConnected) == []


async def test_managed_non_loopback_host_raises_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a non-loopback grpc host is refused before spawning.

    Scenario: managed settings bind ``10.0.0.5:50051``; entry is attempted.

    Boundaries: enforces constraint C7 - only loopback binds are permitted for a
    managed sidecar.

    On failure, first check: entry must raise ``OpenClaudeUnavailableError`` with
    no recorded spawn and no connect event.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url="10.0.0.5:50051"), bus, _RUN_ID)

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []
    assert capture.of(OpenClaudeConnected) == []


async def test_managed_missing_port_raises_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a grpc url without an explicit port is refused before spawn.

    Scenario: managed settings bind ``127.0.0.1`` with no port; entry is
    attempted.

    Boundaries: exercises the endpoint-parsing guard before spawn.

    On failure, first check: entry must raise ``OpenClaudeUnavailableError`` with
    no recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url="127.0.0.1"), bus, _RUN_ID)

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_managed_relative_binary_path_raises_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a relative path-form process binary is rejected.

    Scenario: managed settings set ``process_binary="./openclaude"``; entry is
    attempted.

    Boundaries: enforces constraint C1 - a path-form binary must be absolute.

    On failure, first check: entry must raise ``OpenClaudeConfigError`` with no
    recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    settings = OpenClaudeSettings(grpc_url=_MANAGED_URL, auto_start=True, process_binary="./openclaude")
    proc = OpenClaudeProcess(settings, bus, _RUN_ID)

    with pytest.raises(OpenClaudeConfigError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_managed_unset_grpc_url_raises_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: managed mode with no grpc url has no address and never spawns.

    Scenario: managed settings carry ``grpc_url=None``; entry is attempted.

    Boundaries: exercises the address-required guard for managed mode.

    On failure, first check: entry must raise ``OpenClaudeUnavailableError`` with
    no recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url=None), bus, _RUN_ID)

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_managed_absolute_missing_binary_raises_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: an absolute but missing process binary is rejected.

    Scenario: managed settings point ``process_binary`` at a non-existent
    absolute path; entry is attempted.

    Boundaries: enforces constraint C1 - a path-form binary must exist on disk.

    On failure, first check: entry must raise ``OpenClaudeConfigError`` with no
    recorded spawn.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    settings = OpenClaudeSettings(
        grpc_url=_MANAGED_URL,
        auto_start=True,
        process_binary="/nonexistent/path/to/openclaude",
    )
    proc = OpenClaudeProcess(settings, bus, _RUN_ID)

    with pytest.raises(OpenClaudeConfigError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []


async def test_probe_port_true_when_a_listener_accepts():
    """[Unit] process: the real TCP probe returns True against a live listener.

    Scenario: a loopback server is started on an ephemeral port and
    ``_probe_port`` targets it.

    Boundaries: exercises the real ``_probe_port`` against a real socket; no
    monkeypatching.

    On failure, first check: the probe must return ``True`` while a listener
    accepts connections on the bound port.
    """

    async def _handle(_: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Accept and immediately close the probe connection."""
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert await OpenClaudeProcess._probe_port("127.0.0.1", port) is True
    finally:
        server.close()
        await server.wait_closed()


async def test_probe_port_false_when_nothing_listens():
    """[Unit] process: the real TCP probe returns False for a refused port.

    Scenario: a loopback server is started then torn down, freeing its port,
    which ``_probe_port`` then targets.

    Boundaries: exercises the real ``_probe_port`` against a closed port.

    On failure, first check: the probe must return ``False`` when nothing listens
    on the target port.
    """

    async def _noop(_: asyncio.StreamReader, __: asyncio.StreamWriter):
        """Never invoked; the listener is torn down before any probe."""
        pass  # pragma: no cover - never invoked; the listener is torn down first

    server = await asyncio.start_server(_noop, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    assert await OpenClaudeProcess._probe_port("127.0.0.1", port) is False


async def test_managed_port_timeout_terminates_then_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a port that never opens terminates the sidecar then raises.

    Scenario: managed mode spawns but the readiness probe always reports closed
    with a 1s timeout.

    Boundaries: enforces constraint C6 - a failed readiness must reap the child
    before surfacing the error.

    On failure, first check: exactly one terminate and at least one wait must run,
    the return code must be set, and no connect/disconnect event should be emitted.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(connect_timeout_s=1), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=False)

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert fake.terminate_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode is not None
    assert capture.of(OpenClaudeConnected) == []
    # __aexit__ is not driven when __aenter__ raises; terminate ran exactly once.
    assert capture.of(OpenClaudeDisconnected) == []


async def test_managed_exit_sigterm_without_kill(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: clean managed exit sends SIGTERM and never SIGKILL.

    Scenario: the fake process exits on terminate; managed mode enters and exits
    normally.

    Boundaries: enforces constraint C6 - a graceful child needs no SIGKILL.

    On failure, first check: exactly one terminate, zero kills, at least one wait,
    and one disconnect with reason ``context_exit``.
    """
    fake = _FakeProcess(terminate_exits=True)
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 0
    assert fake.wait_calls >= 1
    disconnected = capture.of(OpenClaudeDisconnected)
    assert len(disconnected) == 1
    assert disconnected[0].reason == "context_exit"


async def test_managed_exit_escalates_to_sigkill(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a child ignoring SIGTERM within grace is escalated to SIGKILL.

    Scenario: the fake process never exits on terminate and the grace period is
    shortened to 0.01s; managed mode exits normally.

    Boundaries: enforces the grace-period escalation contract of C6.

    On failure, first check: exactly one terminate and one kill, the return code
    must be ``-9``, and one disconnect must be emitted.
    """
    fake = _FakeProcess(terminate_exits=False)
    _spawn_recorder(monkeypatch, fake)
    monkeypatch.setattr(process_mod, "_TERMINATE_GRACE_S", 0.01)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode == -9
    assert len(capture.of(OpenClaudeDisconnected)) == 1


class _KillRaisesProcess(_FakeProcess):
    """Fake process whose ``kill`` raises ``ProcessLookupError`` (already reaped).

    Models a SIGCHLD landing between the ``returncode is None`` check and
    ``kill()``: the child has already exited (so ``wait`` can still reap it) but
    the ``kill()`` syscall now reports the pid is gone. Never exits on SIGTERM so
    the grace-period escalation path is always taken.
    """

    def __init__(self):
        """Initialise a fake that never reaps on terminate."""
        super().__init__(terminate_exits=False)

    def kill(self):
        """Simulate the child already gone, then raise ``ProcessLookupError``."""
        self.kill_calls += 1
        # The child was reaped by a SIGCHLD; wait() can complete, but kill()
        # itself now finds no such process.
        self.returncode = -9
        self._exited.set()
        raise ProcessLookupError("No such process")


async def test_managed_exit_kill_process_lookup_error_tolerated(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a kill raising ProcessLookupError is tolerated on exit.

    Scenario: the fake ``kill`` raises ``ProcessLookupError`` (child already
    reaped) with a shortened grace period; managed mode exits normally.

    Boundaries: proves the escalation path tolerates a race where the child dies
    just before ``kill()``.

    On failure, first check: no exception should escape the context manager, one
    terminate and one kill must run, and one disconnect must be emitted.
    """
    fake = _KillRaisesProcess()
    _spawn_recorder(monkeypatch, fake)
    monkeypatch.setattr(process_mod, "_TERMINATE_GRACE_S", 0.01)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    # No exception escapes the context manager despite kill() raising.
    async with proc:
        pass

    assert fake.terminate_calls == 1
    assert fake.kill_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode is not None
    assert len(capture.of(OpenClaudeDisconnected)) == 1


async def test_managed_exit_emits_single_disconnected_after_terminate(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: managed exit emits one disconnect, only after teardown.

    Scenario: ``terminate`` is wrapped to record its ordering relative to the
    disconnect subscriber; managed mode exits normally.

    Boundaries: proves teardown ordering - the child is reaped before the
    disconnect event is published.

    On failure, first check: the recorded order must be exactly
    ``["terminate", "disconnect"]``.
    """
    order: list[str] = []

    fake = _FakeProcess()
    original_terminate = fake.terminate

    def _tracking_terminate():
        """Record the terminate call then delegate to the original."""
        order.append("terminate")
        original_terminate()

    fake.terminate = _tracking_terminate  # type: ignore[method-assign]
    _spawn_recorder(monkeypatch, fake)

    bus = EventBus()

    def _record_disconnect(_: DomainEvent):
        """Record that a disconnect event was published."""
        order.append("disconnect")

    bus.subscribe(OpenClaudeDisconnected, _record_disconnect)

    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert order == ["terminate", "disconnect"]


async def test_terminate_managed_idempotent_when_never_started():
    """[Unit] process: terminating with no owned process is a safe no-op.

    Scenario: ``_terminate_managed`` is called on a managed process that never
    entered.

    Boundaries: exercises the no-owned-process guard directly.

    On failure, first check: the call must not raise and ``_process`` must remain
    ``None``.
    """
    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)

    await proc._terminate_managed()  # no process started - must not raise

    assert proc._process is None


async def test_terminate_managed_idempotent_on_repeated_call(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a second terminate on a reaped process does nothing further.

    Scenario: managed mode enters and exits, then ``_terminate_managed`` is
    invoked again.

    Boundaries: exercises terminate idempotency after a normal exit.

    On failure, first check: the terminate count must not increase on the second
    call.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    calls_after_exit = fake.terminate_calls
    await proc._terminate_managed()

    assert fake.terminate_calls == calls_after_exit


async def test_managed_subscriber_raising_after_readiness_terminates_sidecar(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a connect-publish error after readiness reaps the sidecar.

    Scenario: the port opens immediately but ``bus.publish`` is patched to raise
    at the connect event - the gap after "process live" but before entry returns.

    Boundaries: enforces constraint C6 - the entry-raised guard must terminate
    the sidecar itself since ``__aexit__`` only runs after a successful entry.

    On failure, first check: exactly one terminate and at least one wait must run
    and the return code must be set (no orphaned live process).
    """

    class _SubscriberError(RuntimeError):
        """Sentinel error raised when the connect event is published."""

    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()

    # Fail exactly at the connect-event publish, in the cooperative gap after
    # readiness. Monkeypatch publish (rather than a plain subscriber) because
    # EventBus.publish deliberately swallows subscriber ``Exception``s; the
    # failure we model here is one that reaches __aenter__.
    def _boom(event: DomainEvent):
        """Raise a sentinel error when the connect event is published."""
        raise _SubscriberError("publish blew up on connect")

    monkeypatch.setattr(bus, "publish", _boom)

    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    with pytest.raises(_SubscriberError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    # (b) sidecar reaped: terminate() and wait() were driven exactly once.
    assert fake.terminate_calls == 1
    assert fake.wait_calls >= 1
    # (c) no orphaned live process remains.
    assert fake.returncode is not None


async def test_managed_cancellation_after_readiness_terminates_sidecar(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: cancellation in the connect emit still reaps the sidecar.

    Scenario: the port opens immediately but the connect subscriber raises
    ``asyncio.CancelledError`` - a cancellation in the cooperative gap after
    readiness.

    Boundaries: proves the ``except BaseException`` guard covers cancellation, not
    just ordinary errors.

    On failure, first check: cancellation must propagate while exactly one
    terminate, at least one wait, and a set return code confirm the sidecar was
    reaped.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus = EventBus()

    def _cancel(_: DomainEvent):
        """Raise ``CancelledError`` when the connect event is published."""
        raise asyncio.CancelledError()

    bus.subscribe(OpenClaudeConnected, _cancel)

    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    with pytest.raises(asyncio.CancelledError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert fake.terminate_calls == 1
    assert fake.wait_calls >= 1
    assert fake.returncode is not None


# ---------------------------------------------------------------------------
# Port-0 free-port selection (managed mode only) - subtask 03
# ---------------------------------------------------------------------------


async def test_managed_port_zero_resolves_concrete_single_source_of_truth(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a ``:0`` wildcard resolves once to one shared concrete port.

    Scenario: managed mode binds ``localhost:0``; the resolved port is compared
    across the bind flag, the ``grpc_url`` property, the connect event, and the
    probe target.

    Boundaries: proves a single source of truth - no per-consumer re-resolution
    to a different free port.

    On failure, first check: the resolved port must be non-zero and identical in
    the ``--grpc-address=`` flag, ``grpc_url``, connect event, and every probe.
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url="localhost:0"), bus, _RUN_ID)

    probed: list[tuple[str, int]] = []

    async def _probe(host: str, port: int) -> bool:
        """Record the probe target and report the port open."""
        probed.append((host, port))
        return True

    monkeypatch.setattr(proc, "_probe_port", _probe)

    async with proc:
        url = proc.grpc_url

    host, _, port_text = url.partition(":")
    assert host == "localhost"
    port = int(port_text)
    assert port != 0

    # The child bind flag carries the SAME concrete port (resolved before spawn).
    args, _ = calls[0]
    assert f"--grpc-address=localhost:{port}" in args
    # The readiness probe targeted the SAME concrete port.
    assert probed and all(target == ("localhost", port) for target in probed)
    # The connect event carries the SAME resolved endpoint.
    assert capture.of(OpenClaudeConnected)[0].grpc_url == url


async def test_managed_concrete_port_passes_through_no_free_port_probe(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a concrete port is used verbatim with no free-port probe.

    Scenario: managed mode binds ``127.0.0.1:50051`` while ``_pick_free_port`` is
    spied to fail if called.

    Boundaries: proves free-port selection is skipped when a concrete port is
    already configured.

    On failure, first check: ``grpc_url`` must equal the configured endpoint and
    ``_pick_free_port`` must never be invoked.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    picks: list[str] = []

    def _spy(host: str) -> int:
        """Record a free-port pick; must never run for a concrete port."""
        picks.append(host)  # pragma: no cover - must never run for a concrete port
        return 1

    monkeypatch.setattr(OpenClaudeProcess, "_pick_free_port", staticmethod(_spy))

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url=_MANAGED_URL), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        assert proc.grpc_url == _MANAGED_URL

    assert picks == []


def test_pick_free_port_returns_usable_port_and_closes_socket(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: the free-port probe binds then closes its socket.

    Scenario: ``socket.socket`` is wrapped by a tracker; ``_pick_free_port`` is
    called for loopback.

    Boundaries: proves no file-descriptor leak - the probe socket is closed via
    the ``with`` block's ``__exit__``.

    On failure, first check: the returned port must be a positive int and the one
    created tracking socket must have closed via ``__exit__``.
    """
    real_socket = socket.socket
    created: list[_TrackingSocket] = []

    class _TrackingSocket:
        """Wrap a real socket to record that ``__exit__`` (close) actually ran."""

        def __init__(self, *args: object, **kwargs: object):
            """Create the wrapped real socket and register this tracker."""
            self._sock = real_socket(*args, **kwargs)  # type: ignore[arg-type]
            self.closed_via_exit = False
            created.append(self)

        def __enter__(self) -> _TrackingSocket:
            """Enter the wrapped socket's context and return this tracker."""
            self._sock.__enter__()
            return self

        def __exit__(self, *exc: object):
            """Record that close ran and delegate to the wrapped socket."""
            self.closed_via_exit = True
            self._sock.__exit__(*exc)  # type: ignore[arg-type]

        def bind(self, address: tuple[str, int]):
            """Bind the wrapped socket to *address*."""
            self._sock.bind(address)

        def getsockname(self) -> tuple[str, int]:
            """Return the wrapped socket's bound address."""
            return self._sock.getsockname()

    monkeypatch.setattr(socket, "socket", _TrackingSocket)

    port = OpenClaudeProcess._pick_free_port("127.0.0.1")

    assert isinstance(port, int)
    assert port > 0
    assert len(created) == 1
    assert created[0].closed_via_exit is True


async def test_external_mode_port_zero_not_rewritten_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: external mode never rewrites ``:0`` and surfaces unavailable.

    Scenario: external mode is configured with ``localhost:0`` and an unhealthy
    client while ``_pick_free_port`` is spied.

    Boundaries: proves free-port rewriting is a managed-only concern; external
    mode leaves the misconfiguration to fail via the health check.

    On failure, first check: entry must raise ``OpenClaudeUnavailableError``,
    ``_pick_free_port`` must never run, and no connect event should be emitted.
    """
    picks: list[str] = []

    def _spy(host: str) -> int:
        """Record a free-port pick; external mode must never pick a port."""
        picks.append(host)  # pragma: no cover - external mode must never pick a port
        return 1

    monkeypatch.setattr(OpenClaudeProcess, "_pick_free_port", staticmethod(_spy))

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(
        _settings(grpc_url="localhost:0"),
        bus,
        _RUN_ID,
        client=_MockClient(healthy=False),
    )

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert picks == []
    assert capture.of(OpenClaudeConnected) == []


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


# ---------------------------------------------------------------------------
# stderr forwarding (managed mode only) - subtask 04
# ---------------------------------------------------------------------------


class _LogRecorder:
    """Record ``logger.debug``/``info``/``warning`` calls in place of the sink.

    Each recorder method stores the positional args it was called with so a test
    can assert *which level* a forwarded stderr line was emitted at (DEBUG only)
    without adding a real loguru sink.
    """

    def __init__(self):
        """Initialise empty per-level recorded-call lists."""
        self.debug: list[tuple] = []
        self.info: list[tuple] = []
        self.warning: list[tuple] = []

    def record_debug(self, *args: object, **kwargs: object):
        """Record a ``logger.debug`` call."""
        self.debug.append(args)

    def record_info(self, *args: object, **kwargs: object):
        """Record a ``logger.info`` call."""
        self.info.append(args)

    def record_warning(self, *args: object, **kwargs: object):
        """Record a ``logger.warning`` call."""
        self.warning.append(args)


def _forwarded_lines(recorder: _LogRecorder) -> list[object]:
    """Extract the forwarded stderr texts (trailing arg) from DEBUG records."""
    return [args[-1] for args in recorder.debug if args and "stderr" in str(args[0])]


def _text_appears(calls: list[tuple], text: str) -> bool:
    """Return whether *text* appears in any recorded call's arguments."""
    return any(text in str(arg) for args in calls for arg in args)


async def test_managed_stderr_drained_line_by_line_at_debug_not_info_or_warning(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: managed stderr is drained line-by-line at DEBUG only.

    Scenario: the fake process scripts two stderr lines; the logger levels are
    recorded while managed mode drains them.

    Boundaries: enforces constraint C9 - forwarded diagnostics stay at DEBUG and
    never persist at INFO/WARNING.

    On failure, first check: both lines must appear rstripped at DEBUG and never
    at INFO or WARNING.
    """
    fake = _FakeProcess(stderr_lines=[b"first diagnostic\n", b"second diagnostic\n"])
    _spawn_recorder(monkeypatch, fake)

    rec = _LogRecorder()
    monkeypatch.setattr(process_mod.logger, "debug", rec.record_debug)
    monkeypatch.setattr(process_mod.logger, "info", rec.record_info)
    monkeypatch.setattr(process_mod.logger, "warning", rec.record_warning)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert _forwarded_lines(rec) == ["first diagnostic", "second diagnostic"]
    # The lines were rstripped and never emitted at a level that persists.
    assert not _text_appears(rec.info, "diagnostic")
    assert not _text_appears(rec.warning, "diagnostic")


async def test_managed_stderr_only_stderr_read_stdout_has_no_reader(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: only stderr is drained; stdout is DEVNULL with no reader.

    Scenario: the fake process scripts one stderr line; the spawn kwargs and the
    readers are inspected after draining.

    Boundaries: proves stdout is discarded (DEVNULL) and never read.

    On failure, first check: stderr must be read at least twice, stdout must have
    no reader, and spawn kwargs must be DEVNULL stdout / PIPE stderr.
    """
    fake = _FakeProcess(stderr_lines=[b"diag\n"])
    calls = _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    # stderr was read (line + the EOF-drain attempt); stdout carries no reader.
    assert fake.stderr.readline_calls >= 2
    assert fake.stdout is None
    _, kwargs = calls[0]
    assert kwargs["stdout"] is asyncio.subprocess.DEVNULL
    assert kwargs["stderr"] is asyncio.subprocess.PIPE


async def test_managed_exit_cancels_and_awaits_stderr_forwarder(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: exit cancels and awaits the stderr forwarder with no leak.

    Scenario: the child keeps stderr open so the forwarder is still pending at
    exit; the task state is inspected before and after ``__aexit__``.

    Boundaries: proves clean task teardown - no leaked or escaping
    ``CancelledError``.

    On failure, first check: the forwarder must be pending inside the context and
    both done and cancelled after exit.
    """
    fake = _FakeProcess(stderr_lines=[b"line\n"])
    _spawn_recorder(monkeypatch, fake)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)
        task = proc._stderr_task
        assert task is not None
        # The child keeps stderr open, so the forwarder is still pending here.
        assert not task.done()

    # No CancelledError escaped the ``async with``; the task was cancelled+awaited.
    assert task.done()
    assert task.cancelled()


async def test_managed_entry_raised_after_start_stops_stderr_forwarder(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: an entry failure after start also stops the forwarder.

    Scenario: the port never opens so entry raises after the forwarder started;
    the task state and terminate count are inspected.

    Boundaries: proves the entry-failure path cancels+awaits the forwarder
    alongside the always-terminate invariant.

    On failure, first check: the forwarder must be done and cancelled, exactly one
    terminate must have run, and no connect event should be emitted.
    """
    fake = _FakeProcess(stderr_lines=[b"boot\n"])
    _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(connect_timeout_s=1), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=False)

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    task = proc._stderr_task
    assert task is not None
    assert task.done()
    assert task.cancelled()
    # The always-terminate invariant still ran alongside the forwarder stop.
    assert fake.terminate_calls == 1
    assert capture.of(OpenClaudeConnected) == []


async def test_external_mode_never_starts_stderr_forwarder():
    """[Unit] process: external mode starts no forwarder and stop is a safe no-op.

    Scenario: external mode enters and exits; the forwarder handle is inspected
    and the stop helper is called with no task.

    Boundaries: proves the forwarder is a managed-only concern.

    On failure, first check: ``_stderr_task`` must stay ``None`` throughout and
    ``_stop_stderr_forwarder`` must not raise.
    """
    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        assert proc._stderr_task is None

    assert proc._stderr_task is None
    # Calling the stop helper with no task must not raise.
    await proc._stop_stderr_forwarder()
    assert proc._stderr_task is None


async def test_managed_stderr_per_line_error_does_not_propagate_keeps_draining(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a per-line log error is swallowed narrowly, draining continues.

    Scenario: ``logger.debug`` raises on the first scripted line but not the
    second; managed mode drains both.

    Boundaries: proves the narrow per-line try/except (X002-compliant) keeps the
    forwarder loop alive.

    On failure, first check: the sequence must be the ``bad`` text, the caught
    ``ValueError``, then the ``good`` text - three recorded items.
    """
    fake = _FakeProcess(stderr_lines=[b"bad\n", b"good\n"])
    _spawn_recorder(monkeypatch, fake)

    seen: list[object] = []

    def _debug(template: object, *args: object, **kwargs: object):
        """Record forwarded stderr text and raise once on the ``bad`` line."""
        if "stderr" in str(template):
            text = args[-1]
            seen.append(text)
            if text == "bad":
                raise ValueError("boom formatting the first line")

    monkeypatch.setattr(process_mod.logger, "debug", _debug)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    # The ValueError raised while logging "bad" is caught inside the loop.
    # The except-block diagnostic log also fires (its template contains "stderr"),
    # so the exception object appears between the bad and good entries.
    # The loop keeps draining and the context exits cleanly.
    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert seen[0] == "bad"
    assert isinstance(seen[1], ValueError)
    assert seen[2] == "good"
    assert len(seen) == 3


class _OverrunOnceStreamReader(_FakeStreamReader):
    """Stream reader whose first ``readline`` raises ``LimitOverrunError``.

    Models a future ``readuntil()``-style read that surfaces an over-long line
    as :class:`asyncio.LimitOverrunError` (whose MRO is
    ``LimitOverrunError -> Exception`` - NOT a ``ValueError`` subclass). After
    the single raise it yields its scripted lines, then EOF-drains and blocks
    like :class:`_FakeStreamReader`, so a test can assert the forwarder keeps
    draining subsequent lines and never propagates the error.
    """

    def __init__(self, lines: Optional[list[bytes]] = None):
        """Queue *lines* and arm the one-shot overrun flag."""
        super().__init__(lines)
        self._raised = False

    async def readline(self) -> bytes:
        """Raise ``LimitOverrunError`` once, then behave like the base reader."""
        self.readline_calls += 1
        if not self._raised:
            self._raised = True
            raise asyncio.LimitOverrunError("stderr line exceeded the buffer limit", 0)
        if self._lines:
            return self._lines.pop(0)
        self.exhausted.set()
        await self._block.wait()
        return b""  # pragma: no cover - only reached if the block event is set


async def test_managed_stderr_limit_overrun_error_does_not_propagate_keeps_draining(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: a readline LimitOverrunError is swallowed, draining continues.

    Scenario: the stderr reader raises ``asyncio.LimitOverrunError`` once, then
    yields a line; managed mode drains it.

    Boundaries: defends the explicit ``LimitOverrunError`` branch (not a
    ``ValueError`` subclass) added for a future ``readuntil()`` switch.

    On failure, first check: the error must not escape the context and the line
    after the overrun must still be forwarded.
    """
    fake = _FakeProcess()
    fake.stderr = _OverrunOnceStreamReader([b"after overrun\n"])
    _spawn_recorder(monkeypatch, fake)

    rec = _LogRecorder()
    monkeypatch.setattr(process_mod.logger, "debug", rec.record_debug)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert "after overrun" in _forwarded_lines(rec)


async def test_managed_stderr_flows_through_project_logger_not_a_bespoke_sink(
    monkeypatch: pytest.MonkeyPatch,
):
    """[Unit] process: forwarded stderr flows through the project logger, not a sink.

    Scenario: ``logger.debug`` is recorded and ``logger.add`` is patched to fail
    if called; managed mode drains one stderr line.

    Boundaries: enforces constraint C9 - forwarding must reuse the
    SensitiveFilter-covered logger and never add a bespoke sink.

    On failure, first check: the line must appear via ``logger.debug`` and
    ``logger.add`` must never be invoked.
    """
    fake = _FakeProcess(stderr_lines=[b"diagnostic line\n"])
    _spawn_recorder(monkeypatch, fake)

    rec = _LogRecorder()
    monkeypatch.setattr(process_mod.logger, "debug", rec.record_debug)

    def _no_add(*args: object, **kwargs: object):
        """Fail if stderr forwarding tries to add a bespoke/unfiltered sink."""
        raise AssertionError("stderr forwarding must not add a bespoke/unfiltered sink")

    monkeypatch.setattr(process_mod.logger, "add", _no_add)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert "diagnostic line" in _forwarded_lines(rec)
