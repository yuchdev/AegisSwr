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

    def __init__(self, *, healthy: bool = True, raises: Optional[BaseException] = None) -> None:
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

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
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


async def test_grpc_url_before_entry_raises_runtime_error() -> None:
    """Reading ``.grpc_url`` before ``__aenter__`` raises ``RuntimeError``."""
    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(RuntimeError):
        _ = proc.grpc_url


async def test_reachable_endpoint_emits_single_connected_and_exposes_url() -> None:
    """A reachable endpoint yields one ``OpenClaudeConnected`` and a readable url."""
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


async def test_unreachable_endpoint_raises_and_emits_no_connected() -> None:
    """A False health check raises ``OpenClaudeUnavailableError`` and emits no connect."""
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=False))

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []
    # __aexit__ is not driven by ``async with`` when __aenter__ raises.
    assert capture.of(OpenClaudeDisconnected) == []


async def test_health_check_raising_unavailable_propagates_and_emits_no_connected() -> None:
    """A health check that raises ``OpenClaudeUnavailableError`` propagates unchanged."""
    bus, capture = _bus_with_capture()
    boom = OpenClaudeUnavailableError("refused", grpc_url=_GRPC_URL, status_code="UNAVAILABLE")
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(raises=boom))

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []


async def test_unset_grpc_url_raises_unavailable() -> None:
    """An unconfigured ``grpc_url`` raises ``OpenClaudeUnavailableError`` at entry."""
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(grpc_url=None), bus, _RUN_ID, client=_MockClient())

    with pytest.raises(OpenClaudeUnavailableError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert capture.of(OpenClaudeConnected) == []


async def test_external_mode_never_spawns_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """External mode never calls ``asyncio.create_subprocess_exec``."""
    bus, _ = _bus_with_capture()
    client = _MockClient(healthy=True)

    calls: list[tuple] = []

    async def _spy(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))  # pragma: no cover - must never run

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy)

    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=client)
    async with proc:
        pass

    assert calls == []
    assert client.health_calls == 1


async def test_exit_emits_single_disconnected() -> None:
    """``__aexit__`` emits exactly one ``OpenClaudeDisconnected`` on clean exit."""
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


async def test_exit_is_idempotent_on_repeated_call() -> None:
    """A second ``__aexit__`` does not double-emit ``OpenClaudeDisconnected``."""
    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_settings(), bus, _RUN_ID, client=_MockClient(healthy=True))

    async with proc:
        pass
    # Simulate a re-entrant / double exit.
    result = await proc.__aexit__(None, None, None)

    assert result is None
    assert len(capture.of(OpenClaudeDisconnected)) == 1


async def test_exception_in_body_still_emits_disconnected_and_propagates() -> None:
    """An exception inside the body still emits one disconnect and propagates."""
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
) -> None:
    """The injected mock client is used verbatim; no real client is constructed."""
    import aegis_swr.openclaude.process as process_mod

    def _boom(*args: object, **kwargs: object) -> None:
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
) -> None:
    """With no injected client, one is constructed from settings at entry."""
    import aegis_swr.openclaude.process as process_mod

    built: list[OpenClaudeSettings] = []

    def _factory(settings: OpenClaudeSettings) -> _MockClient:
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


async def test_events_carry_only_ids_and_status_strings() -> None:
    """Emitted events carry only ids/config/status strings, no payload text (C9)."""
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

    def __init__(self, lines: Optional[list[bytes]] = None) -> None:
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
    ) -> None:
        self.returncode: Optional[int] = None
        self._terminate_exits = terminate_exits
        self._exit_code = exit_code
        self._exited = asyncio.Event()
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0
        self.stdout = None
        self.stderr = _FakeStreamReader(stderr_lines)

    def terminate(self) -> None:
        """Record a SIGTERM; reap the process when ``terminate_exits`` is set."""
        self.terminate_calls += 1
        if self._terminate_exits:
            self.returncode = self._exit_code
            self._exited.set()

    def kill(self) -> None:
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
        calls.append((args, kwargs))
        return fake

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spawn)
    return calls


def _patch_probe(monkeypatch: pytest.MonkeyPatch, proc: OpenClaudeProcess, *, opens: bool) -> None:
    """Replace *proc*'s TCP readiness probe with a scripted verdict."""

    async def _probe(host: str, port: int) -> bool:
        return opens

    monkeypatch.setattr(proc, "_probe_port", _probe)


async def test_managed_mode_spawns_once_with_joined_allowlist_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Managed entry spawns exactly once with the joined single-token flags."""
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
) -> None:
    """The spawned process handle is retained (stderr forwarding, subtask 04)."""
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
) -> None:
    """A hostile ``bash_allowlist`` value aborts entry before any spawn (C7)."""
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(bash_allowlist=["rg", hostile]), bus, _RUN_ID)

    with pytest.raises(OpenClaudeConfigError):
        async with proc:
            pass  # pragma: no cover - entry raises before the body runs

    assert calls == []
    assert capture.of(OpenClaudeConnected) == []


def test_validate_argv_token_rejects_hostile_values_for_both_fields() -> None:
    """The argv boundary helper fails closed for both allowlist fields."""
    for field in ("allowed_tools", "bash_allowlist"):
        for bad in ("--flag", "a,b", "k=v", "has space", "", "ctrl\x00"):
            with pytest.raises(OpenClaudeConfigError):
                OpenClaudeProcess._validate_argv_token(bad, field=field)
    assert OpenClaudeProcess._validate_argv_token("rg", field="bash_allowlist") == "rg"


def test_validate_argv_token_rejects_trailing_newline_but_accepts_plain() -> None:
    """A trailing newline is rejected by the ``\\A``/``\\Z`` anchors (regression).

    In non-MULTILINE mode ``$`` matches just before a trailing ``\\n``, so a
    value like ``"rg\\n"`` would wrongly pass a ``^...$`` pattern and leak a
    control char into the child argv. The ``\\A``/``\\Z`` anchors reject it.
    """
    with pytest.raises(OpenClaudeConfigError):
        OpenClaudeProcess._validate_argv_token("rg\n", field="bash_allowlist")
    assert OpenClaudeProcess._validate_argv_token("rg", field="bash_allowlist") == "rg"


async def test_managed_bash_allowlist_trailing_newline_fails_closed_no_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``bash_allowlist`` value with a trailing newline aborts entry, no spawn."""
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
) -> None:
    """A non-loopback ``grpc_url`` host is refused before spawning (C7)."""
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
) -> None:
    """A ``grpc_url`` without an explicit port is refused before spawning."""
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
) -> None:
    """A path-form ``process_binary`` that is relative is rejected (C1)."""
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
) -> None:
    """Managed mode with no ``grpc_url`` has no address to bind and never spawns."""
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
) -> None:
    """An absolute ``process_binary`` that does not exist is rejected (C1)."""
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


async def test_probe_port_true_when_a_listener_accepts() -> None:
    """The real TCP probe returns ``True`` against a live loopback listener."""

    async def _handle(_: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.close()

    server = await asyncio.start_server(_handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert await OpenClaudeProcess._probe_port("127.0.0.1", port) is True
    finally:
        server.close()
        await server.wait_closed()


async def test_probe_port_false_when_nothing_listens() -> None:
    """The real TCP probe returns ``False`` for a refused loopback port."""

    async def _noop(_: asyncio.StreamReader, __: asyncio.StreamWriter) -> None:
        pass  # pragma: no cover - never invoked; the listener is torn down first

    server = await asyncio.start_server(_noop, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    assert await OpenClaudeProcess._probe_port("127.0.0.1", port) is False


async def test_managed_port_timeout_terminates_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A port that never opens raises but terminates the sidecar first (C6)."""
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
) -> None:
    """Clean exit sends SIGTERM, the process exits in grace, no SIGKILL (C6)."""
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
) -> None:
    """A process that ignores SIGTERM within grace is escalated to SIGKILL."""
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

    def __init__(self) -> None:
        super().__init__(terminate_exits=False)

    def kill(self) -> None:
        """Simulate the child already gone, then raise ``ProcessLookupError``."""
        self.kill_calls += 1
        # The child was reaped by a SIGCHLD; wait() can complete, but kill()
        # itself now finds no such process.
        self.returncode = -9
        self._exited.set()
        raise ProcessLookupError("No such process")


async def test_managed_exit_kill_process_lookup_error_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``kill()`` raising ``ProcessLookupError`` is tolerated; process still reaped."""
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
) -> None:
    """Managed exit emits exactly one disconnect, and only after teardown."""
    order: list[str] = []

    fake = _FakeProcess()
    original_terminate = fake.terminate

    def _tracking_terminate() -> None:
        order.append("terminate")
        original_terminate()

    fake.terminate = _tracking_terminate  # type: ignore[method-assign]
    _spawn_recorder(monkeypatch, fake)

    bus = EventBus()

    def _record_disconnect(_: DomainEvent) -> None:
        order.append("disconnect")

    bus.subscribe(OpenClaudeDisconnected, _record_disconnect)

    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        pass

    assert order == ["terminate", "disconnect"]


async def test_terminate_managed_idempotent_when_never_started() -> None:
    """Terminating with no owned process is a safe no-op."""
    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)

    await proc._terminate_managed()  # no process started - must not raise

    assert proc._process is None


async def test_terminate_managed_idempotent_on_repeated_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second terminate on an already-reaped process does nothing further."""
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
) -> None:
    """A connect-event subscriber raising after readiness reaps the sidecar (C6).

    Readiness is reached (fake port opens immediately) but a bus subscriber
    raises when :class:`OpenClaudeConnected` is published - the cooperative gap
    after "process is live" but before ``__aenter__`` returns ``self``. Since
    ``__aexit__`` only runs when ``__aenter__`` returned, the entry-raised guard
    must terminate the sidecar itself before the exception leaves ``__aenter__``.
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
    def _boom(event: DomainEvent) -> None:
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
) -> None:
    """Cancellation in the connect emit after readiness still reaps the sidecar.

    Reuses the fake-process harness but the connect-event subscriber raises
    :class:`asyncio.CancelledError`, modelling a cancellation arriving in the
    cooperative gap after readiness. The ``except BaseException`` guard covers
    it, so the sidecar is terminated and the cancellation propagates.
    """
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    bus = EventBus()

    def _cancel(_: DomainEvent) -> None:
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
) -> None:
    """A ``localhost:0`` wildcard resolves once to one concrete port every consumer shares.

    Asserts the resolved port (n != 0) is identical across the child's
    ``--grpc-address=`` bind flag, the caller-visible ``grpc_url`` property, the
    emitted connect event, and the readiness-probe target - proving a single
    source of truth (no per-consumer re-resolution to a different free port).
    """
    fake = _FakeProcess()
    calls = _spawn_recorder(monkeypatch, fake)

    bus, capture = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(grpc_url="localhost:0"), bus, _RUN_ID)

    probed: list[tuple[str, int]] = []

    async def _probe(host: str, port: int) -> bool:
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
) -> None:
    """A concrete ``localhost:50051`` is used verbatim; no free-port probe is opened."""
    fake = _FakeProcess()
    _spawn_recorder(monkeypatch, fake)

    picks: list[str] = []

    def _spy(host: str) -> int:
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
) -> None:
    """The probe socket is bound then closed within the ``with`` (no descriptor leak)."""
    real_socket = socket.socket
    created: list[_TrackingSocket] = []

    class _TrackingSocket:
        """Wrap a real socket to record that ``__exit__`` (close) actually ran."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            self._sock = real_socket(*args, **kwargs)  # type: ignore[arg-type]
            self.closed_via_exit = False
            created.append(self)

        def __enter__(self) -> _TrackingSocket:
            self._sock.__enter__()
            return self

        def __exit__(self, *exc: object) -> None:
            self.closed_via_exit = True
            self._sock.__exit__(*exc)  # type: ignore[arg-type]

        def bind(self, address: tuple[str, int]) -> None:
            self._sock.bind(address)

        def getsockname(self) -> tuple[str, int]:
            return self._sock.getsockname()

    monkeypatch.setattr(socket, "socket", _TrackingSocket)

    port = OpenClaudeProcess._pick_free_port("127.0.0.1")

    assert isinstance(port, int)
    assert port > 0
    assert len(created) == 1
    assert created[0].closed_via_exit is True


async def test_external_mode_port_zero_not_rewritten_surfaces_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External mode never rewrites a ``:0`` misconfiguration; it surfaces via health check."""
    picks: list[str] = []

    def _spy(host: str) -> int:
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


def test_module_has_no_forbidden_spawn_primitives() -> None:
    """The module never uses a shell spawn, raw Popen, or blocking sleep."""
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

    def __init__(self) -> None:
        self.debug: list[tuple] = []
        self.info: list[tuple] = []
        self.warning: list[tuple] = []

    def record_debug(self, *args: object, **kwargs: object) -> None:
        """Record a ``logger.debug`` call."""
        self.debug.append(args)

    def record_info(self, *args: object, **kwargs: object) -> None:
        """Record a ``logger.info`` call."""
        self.info.append(args)

    def record_warning(self, *args: object, **kwargs: object) -> None:
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
) -> None:
    """Managed mode drains stderr line-by-line, each logged at DEBUG only (C9)."""
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
) -> None:
    """Only stderr is drained; stdout is DEVNULL with no reader attached."""
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
) -> None:
    """On ``__aexit__`` the forwarder is cancelled and awaited; no leak, no pending."""
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
) -> None:
    """The port-never-opens entry failure path also cancels+awaits the forwarder."""
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


async def test_external_mode_never_starts_stderr_forwarder() -> None:
    """External mode starts no forwarder; ``_stop_stderr_forwarder`` no-ops safely."""
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
) -> None:
    """A per-line log error is swallowed narrowly; the loop keeps draining (X002)."""
    fake = _FakeProcess(stderr_lines=[b"bad\n", b"good\n"])
    _spawn_recorder(monkeypatch, fake)

    seen: list[object] = []

    def _debug(template: object, *args: object, **kwargs: object) -> None:
        if "stderr" in str(template):
            text = args[-1]
            seen.append(text)
            if text == "bad":
                raise ValueError("boom formatting the first line")

    monkeypatch.setattr(process_mod.logger, "debug", _debug)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    # The ValueError raised while logging "bad" is caught inside the loop and the
    # context exits cleanly - it never propagates out of the ``async with``.
    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert seen == ["bad", "good"]


class _OverrunOnceStreamReader(_FakeStreamReader):
    """Stream reader whose first ``readline`` raises ``LimitOverrunError``.

    Models a future ``readuntil()``-style read that surfaces an over-long line
    as :class:`asyncio.LimitOverrunError` (whose MRO is
    ``LimitOverrunError -> Exception`` - NOT a ``ValueError`` subclass). After
    the single raise it yields its scripted lines, then EOF-drains and blocks
    like :class:`_FakeStreamReader`, so a test can assert the forwarder keeps
    draining subsequent lines and never propagates the error.
    """

    def __init__(self, lines: Optional[list[bytes]] = None) -> None:
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
) -> None:
    """A ``LimitOverrunError`` from readline is swallowed narrowly; draining continues.

    Defends the ``asyncio.LimitOverrunError`` branch added for a future
    ``readuntil()`` switch: it is not a ``ValueError`` subclass, so it must be
    named explicitly. The error must not escape the context manager and lines
    after the over-long one must still be forwarded.
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
) -> None:
    """Forwarded lines flow through the SensitiveFilter-covered ``logger.debug`` (C9)."""
    fake = _FakeProcess(stderr_lines=[b"diagnostic line\n"])
    _spawn_recorder(monkeypatch, fake)

    rec = _LogRecorder()
    monkeypatch.setattr(process_mod.logger, "debug", rec.record_debug)

    def _no_add(*args: object, **kwargs: object) -> None:
        raise AssertionError("stderr forwarding must not add a bespoke/unfiltered sink")

    monkeypatch.setattr(process_mod.logger, "add", _no_add)

    bus, _ = _bus_with_capture()
    proc = OpenClaudeProcess(_managed_settings(), bus, _RUN_ID)
    _patch_probe(monkeypatch, proc, opens=True)

    async with proc:
        await asyncio.wait_for(fake.stderr.exhausted.wait(), timeout=1.0)

    assert "diagnostic line" in _forwarded_lines(rec)
