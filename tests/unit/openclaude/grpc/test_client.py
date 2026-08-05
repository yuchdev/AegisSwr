"""Unit tests for :mod:`aegis_swr.openclaude.grpc.client`.

These tests drive a scripted frame sequence through a mock async channel via
:meth:`OpenClaudeGrpcClient.from_channel`, so no live OpenClaude process is
required. Fake frames are plain :class:`types.SimpleNamespace` objects mirroring
the generated ``AgentMessage`` shape (``type`` / ``content`` / ``tool``), which
keeps the test suite decoupled from the generated protobuf stubs.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import grpc
import pytest
from loguru import logger

from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.exceptions import OpenClaudeUnavailableError
from aegis_swr.openclaude.grpc import client as client_mod
from aegis_swr.openclaude.grpc.client import AgentFrame, FrameKind, OpenClaudeGrpcClient

# Proto FrameType ints (mirrored from openclaude.proto); kept local so tests do
# not import the generated stub.
_TEXT_CHUNK = 1
_TOOL_CALL = 2
_DONE = 5
_ERROR = 6
_UNSPECIFIED = 0


def _msg(frame_type: int, content: str = "", tool: str = "") -> SimpleNamespace:
    """Build a fake ``AgentMessage``-shaped frame."""
    return SimpleNamespace(type=frame_type, content=content, tool=tool)


class _FakeStreamCall:
    """Async iterator over a scripted frame sequence (mimics a gRPC stream call)."""

    def __init__(self, frames: list[SimpleNamespace]) -> None:
        """Store an iterator over the scripted *frames*."""
        self._it = iter(frames)

    def __aiter__(self) -> _FakeStreamCall:
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Yield the next scripted frame or raise ``StopAsyncIteration`` at the end."""
        try:
            return next(self._it)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeMultiCallable:
    """Callable returned by ``channel.unary_stream``; yields a scripted call."""

    def __init__(self, frames: list[SimpleNamespace]) -> None:
        """Store the scripted *frames* and initialise the recorded timeout."""
        self._frames = frames
        self.timeout: Optional[float] = None

    def __call__(self, request: object, timeout: Optional[float] = None) -> _FakeStreamCall:
        """Record the per-call *timeout* and return a scripted stream call."""
        self.timeout = timeout
        return _FakeStreamCall(self._frames)


class _FakeChannel:
    """Minimal async gRPC channel double supporting ``unary_stream`` and ``close``."""

    def __init__(self, frames: Optional[list[SimpleNamespace]] = None) -> None:
        """Store the scripted *frames* and initialise the close counter."""
        self._frames = frames or []
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> _FakeMultiCallable:
        """Return a multicallable that yields the scripted frames."""
        return _FakeMultiCallable(self._frames)

    async def close(self, grace: Optional[float] = None) -> None:
        """Record a channel close call."""
        self.close_calls += 1


def _rpc_error(code: grpc.StatusCode) -> grpc.aio.AioRpcError:
    """Build a real :class:`grpc.aio.AioRpcError` carrying ``code``.

    A genuine instance (not a stand-in) is required so ``except
    grpc.aio.AioRpcError`` in the client actually catches it.
    """
    return grpc.aio.AioRpcError(code, grpc.aio.Metadata(), grpc.aio.Metadata())


class _RaisingStreamCall:
    """Async iterator whose first ``__anext__`` raises a gRPC status error."""

    def __init__(self, error: grpc.aio.AioRpcError) -> None:
        """Store the *error* to raise on first iteration."""
        self._error = error

    def __aiter__(self) -> _RaisingStreamCall:
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Raise the stored gRPC status error immediately."""
        raise self._error


class _RaisingChannel:
    """Channel double whose stream fails immediately with a gRPC status error."""

    def __init__(self, error: grpc.aio.AioRpcError) -> None:
        """Store the *error* raised by the stream and initialise the close counter."""
        self._error = error
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        """Return a callable that produces an immediately-raising stream call."""

        def _call(request: object, timeout: Optional[float] = None) -> _RaisingStreamCall:
            """Return a stream call that raises the stored gRPC error."""
            return _RaisingStreamCall(self._error)

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
        """Record a channel close call."""
        self.close_calls += 1


class _SlowStreamCall:
    """Async iterator that never yields, forcing an ``asyncio.wait_for`` timeout."""

    def __aiter__(self) -> _SlowStreamCall:
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Sleep effectively forever so the caller's ``wait_for`` times out."""
        await asyncio.sleep(3600)
        raise StopAsyncIteration


class _SlowChannel:
    """Channel double whose stream hangs indefinitely."""

    def __init__(self) -> None:
        """Initialise the close counter."""
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        """Return a callable that produces a never-yielding stream call."""

        def _call(request: object, timeout: Optional[float] = None) -> _SlowStreamCall:
            """Return a stream call that never yields."""
            return _SlowStreamCall()

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
        """Record a channel close call."""
        self.close_calls += 1


class _RuntimeErrorStreamCall:
    """Async iterator whose first ``__anext__`` raises a non-gRPC exception."""

    def __aiter__(self) -> _RuntimeErrorStreamCall:
        """Return self as the async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Raise a non-gRPC ``RuntimeError`` immediately."""
        raise RuntimeError("unexpected stream failure")


class _RuntimeErrorChannel:
    """Channel double whose stream fails with an unexpected (non-gRPC) error."""

    def __init__(self) -> None:
        """Initialise the close counter."""
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        """Return a callable that produces a stream call raising a non-gRPC error."""

        def _call(request: object, timeout: Optional[float] = None) -> _RuntimeErrorStreamCall:
            """Return a stream call that raises ``RuntimeError``."""
            return _RuntimeErrorStreamCall()

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
        """Record a channel close call."""
        self.close_calls += 1


def _capture_debug_logs() -> tuple[list[str], int]:
    """Attach a DEBUG-level loguru sink capturing rendered messages."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="DEBUG", format="{message}")
    return records, sink_id


def _capture_warning_logs() -> tuple[list[str], int]:
    """Attach a WARNING-level loguru sink capturing rendered messages."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="WARNING", format="{message}")
    return records, sink_id


def _settings(**overrides: object) -> OpenClaudeSettings:
    """Build settings with a valid ``grpc_url`` plus any overrides."""
    base: dict[str, object] = {"grpc_url": "localhost:50051"}
    base.update(overrides)
    return OpenClaudeSettings(**base)


async def _drain(client: OpenClaudeGrpcClient) -> list[AgentFrame]:
    """Collect all frames yielded by a ``query`` call."""
    return [frame async for frame in client.query("prompt", run_id="run-1")]


async def test_multi_frame_stream_ends_in_done() -> None:
    """[Unit] client: a text stream ending in DONE yields every frame in order.

    Scenario: two text chunks followed by a DONE frame are drained via ``query``.

    Boundaries: uses a fake channel and scripted frames; no live gRPC stream.

    On failure, first check: the frame-type sequence must be TEXT_CHUNK,
    TEXT_CHUNK, DONE and the final content must be the accumulated text.
    """
    channel = _FakeChannel(
        [
            _msg(_TEXT_CHUNK, content="hello "),
            _msg(_TEXT_CHUNK, content="world"),
            _msg(_DONE, content="hello world"),
        ]
    )
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert [f.frame_type for f in frames] == [
        FrameKind.TEXT_CHUNK,
        FrameKind.TEXT_CHUNK,
        FrameKind.DONE,
    ]
    assert frames[-1].content == "hello world"


async def test_stream_ends_in_error_frame() -> None:
    """[Unit] client: a stream ending in an ERROR frame yields it last.

    Scenario: a text chunk followed by an ERROR frame is drained via ``query``.

    Boundaries: an ERROR *frame* is a normal terminal, distinct from a gRPC
    status error.

    On failure, first check: the final frame must be an ERROR carrying its
    content.
    """
    channel = _FakeChannel(
        [
            _msg(_TEXT_CHUNK, content="partial"),
            _msg(_ERROR, content="boom"),
        ]
    )
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert frames[-1].frame_type is FrameKind.ERROR
    assert frames[-1].content == "boom"


async def test_query_stops_after_first_terminal_frame() -> None:
    """[Unit] client: frames after the first terminal DONE are not yielded.

    Scenario: a DONE frame is followed by a stray text chunk in the script.

    Boundaries: proves the query loop stops on the first terminal frame.

    On failure, first check: exactly one frame (the DONE) must be yielded and the
    trailing chunk must be dropped.
    """
    channel = _FakeChannel(
        [
            _msg(_DONE, content="done"),
            _msg(_TEXT_CHUNK, content="leaked"),
        ]
    )
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert len(frames) == 1
    assert frames[0].frame_type is FrameKind.DONE


async def test_empty_tool_string_projects_to_none() -> None:
    """[Unit] client: an empty proto ``tool`` string projects to ``None``.

    Scenario: a TOOL_CALL frame carries an empty ``tool`` string, followed by DONE.

    Boundaries: exercises the proto-to-domain field projection only.

    On failure, first check: the tool-call frame's ``tool`` attribute must be
    ``None``, not an empty string.
    """
    channel = _FakeChannel(
        [
            _msg(_TOOL_CALL, content="{}", tool=""),
            _msg(_DONE, content=""),
        ]
    )
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert frames[0].frame_type is FrameKind.TOOL_CALL
    assert frames[0].tool is None


async def test_populated_tool_string_preserved() -> None:
    """[Unit] client: a non-empty proto ``tool`` string is preserved.

    Scenario: a TOOL_CALL frame carries ``tool="Read"``, followed by DONE.

    Boundaries: exercises the proto-to-domain field projection only.

    On failure, first check: the tool-call frame's ``tool`` must equal ``Read``.
    """
    channel = _FakeChannel(
        [
            _msg(_TOOL_CALL, content="{}", tool="Read"),
            _msg(_DONE, content=""),
        ]
    )
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert frames[0].tool == "Read"


async def test_unspecified_frame_type_is_terminal_error() -> None:
    """[Unit] client: a FRAME_TYPE_UNSPECIFIED frame raises rather than dropping.

    Scenario: a single unspecified-type frame is drained via ``query``.

    Boundaries: proves protocol violations are treated as transport failures.

    On failure, first check: draining must raise ``OpenClaudeUnavailableError``.
    """
    channel = _FakeChannel([_msg(_UNSPECIFIED, content="junk")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError):
        await _drain(client)


async def test_stream_without_terminal_frame_raises() -> None:
    """[Unit] client: a stream ending without DONE/ERROR is a transport failure.

    Scenario: a lone text chunk with no terminal frame is drained via ``query``.

    Boundaries: proves an incomplete stream is not silently accepted.

    On failure, first check: draining must raise ``OpenClaudeUnavailableError``.
    """
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="only")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError):
        await _drain(client)


async def test_close_idempotent_and_closes_channel() -> None:
    """[Unit] client: ``close()`` shuts the channel once and is safe to repeat.

    Scenario: ``close`` is called twice on a client bound to a fake channel.

    Boundaries: exercises close idempotency only.

    On failure, first check: the channel's close count must be exactly one.
    """
    channel = _FakeChannel([_msg(_DONE, content="")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    await client.close()
    await client.close()

    assert channel.close_calls == 1


async def test_close_safe_when_channel_never_opened() -> None:
    """[Unit] client: ``close()`` is a no-op when no channel was created.

    Scenario: ``close`` is called on a cold client constructed from settings.

    Boundaries: proves the lazy-channel guard tolerates close before open.

    On failure, first check: the call must not raise and ``_channel`` must stay
    ``None``.
    """
    client = OpenClaudeGrpcClient(_settings())

    await client.close()  # must not raise

    assert client._channel is None


def test_init_does_not_open_channel() -> None:
    """[Unit] client: constructing from settings creates neither channel nor stub.

    Scenario: a client is built from settings with no injected channel.

    Boundaries: proves construction is side-effect free (lazy channel creation).

    On failure, first check: both ``_channel`` and ``_stub`` must be ``None`` right
    after construction.
    """
    client = OpenClaudeGrpcClient(_settings())

    assert client._channel is None
    assert client._stub is None


def test_from_channel_bypasses_lazy_creation() -> None:
    """[Unit] client: ``from_channel`` binds the channel and builds the stub eagerly.

    Scenario: a client is built via ``from_channel`` with a fake channel.

    Boundaries: proves the injection path bypasses lazy creation.

    On failure, first check: ``_channel`` must be the injected channel and
    ``_stub`` must be non-``None``.
    """
    channel = _FakeChannel()
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert client._channel is channel
    assert client._stub is not None


def test_ensure_channel_uses_insecure_when_tls_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Unit] client: ``_ensure_channel`` picks insecure when ``use_tls`` is False.

    Scenario: both channel constructors are mocked and ``_ensure_channel`` runs
    with ``use_tls=False``.

    Boundaries: exercises the TLS branch selection only.

    On failure, first check: the insecure constructor must be called once and the
    secure one never.
    """
    insecure = MagicMock(return_value=_FakeChannel())
    secure = MagicMock(return_value=_FakeChannel())
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", insecure)
    monkeypatch.setattr(client_mod.grpc.aio, "secure_channel", secure)

    client = OpenClaudeGrpcClient(_settings(use_tls=False))
    client._ensure_channel()

    insecure.assert_called_once()
    secure.assert_not_called()


def test_ensure_channel_uses_secure_when_tls_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Unit] client: ``_ensure_channel`` picks secure when ``use_tls`` is True.

    Scenario: both channel constructors are mocked and ``_ensure_channel`` runs
    with ``use_tls=True``.

    Boundaries: exercises the TLS branch selection only.

    On failure, first check: the secure constructor must be called once and the
    insecure one never.
    """
    insecure = MagicMock(return_value=_FakeChannel())
    secure = MagicMock(return_value=_FakeChannel())
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", insecure)
    monkeypatch.setattr(client_mod.grpc.aio, "secure_channel", secure)

    client = OpenClaudeGrpcClient(_settings(use_tls=True))
    client._ensure_channel()

    secure.assert_called_once()
    insecure.assert_not_called()


def test_ensure_channel_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """[Unit] client: repeated ``_ensure_channel`` calls reuse channel and stub.

    Scenario: the insecure constructor is mocked and ``_ensure_channel`` is called
    twice.

    Boundaries: exercises channel caching only.

    On failure, first check: both calls must return the same object and the
    constructor must run once.
    """
    insecure = MagicMock(return_value=_FakeChannel())
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", insecure)

    client = OpenClaudeGrpcClient(_settings())
    first = client._ensure_channel()
    second = client._ensure_channel()

    assert first is second
    insecure.assert_called_once()


async def test_context_manager_closes_channel() -> None:
    """[Unit] client: the async context manager closes the channel on exit.

    Scenario: a client is used as an ``async with`` context and then inspected.

    Boundaries: exercises the ``__aexit__`` close path only.

    On failure, first check: the channel's close count must be exactly one after
    the context exits.
    """
    channel = _FakeChannel([_msg(_DONE, content="")])

    async with OpenClaudeGrpcClient.from_channel(channel, _settings()) as client:
        assert isinstance(client, OpenClaudeGrpcClient)

    assert channel.close_calls == 1


# --- subtask 04: health_check(), timeouts, and status translation -----------


async def test_health_check_true_on_terminal_done() -> None:
    """[Unit] client: ``health_check`` returns True when the probe ends in DONE.

    Scenario: a probe stream yields a text chunk then a DONE frame.

    Boundaries: exercises the health probe's success path.

    On failure, first check: ``health_check`` must return ``True``.
    """
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="pong"), _msg(_DONE, content="pong")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is True


async def test_health_check_false_on_unavailable() -> None:
    """[Unit] client: ``health_check`` returns False (never raises) on UNAVAILABLE.

    Scenario: the probe stream raises a gRPC UNAVAILABLE status error.

    Boundaries: proves transient status errors are swallowed into a False verdict.

    On failure, first check: ``health_check`` must return ``False`` and not raise.
    """
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.UNAVAILABLE))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_deadline_exceeded() -> None:
    """[Unit] client: ``health_check`` returns False on DEADLINE_EXCEEDED.

    Scenario: the probe stream raises a gRPC DEADLINE_EXCEEDED status error.

    Boundaries: proves deadline errors are swallowed into a False verdict.

    On failure, first check: ``health_check`` must return ``False`` and not raise.
    """
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_timeout() -> None:
    """[Unit] client: a probe that never answers within the deadline yields False.

    Scenario: a slow channel never yields; the connect timeout is shrunk to 0.05s.

    Boundaries: exercises the ``wait_for`` timeout path of the health probe.

    On failure, first check: ``health_check`` must return ``False`` after the
    shortened deadline elapses.
    """
    client = OpenClaudeGrpcClient.from_channel(_SlowChannel(), _settings())
    # Shrink the connect deadline so the wait_for cancellation is near-instant.
    object.__setattr__(client._settings, "connect_timeout_s", 0.05)

    assert await client.health_check() is False


async def test_health_check_false_on_terminal_error_frame() -> None:
    """[Unit] client: a terminal ERROR frame during a probe yields False.

    Scenario: the probe stream ends in an ERROR frame rather than DONE.

    Boundaries: proves an ERROR terminal is treated as an unhealthy verdict.

    On failure, first check: ``health_check`` must return ``False``, not ``True``.
    """
    channel = _FakeChannel([_msg(_ERROR, content="boom")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_unspecified_frame() -> None:
    """[Unit] client: a protocol-violating unspecified frame during a probe yields False.

    Scenario: the probe stream yields a single unspecified-type frame.

    Boundaries: proves a protocol violation during a probe is a False verdict, not
    a raise.

    On failure, first check: ``health_check`` must return ``False``.
    """
    channel = _FakeChannel([_msg(_UNSPECIFIED, content="junk")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_stream_without_terminal_frame() -> None:
    """[Unit] client: a probe stream ending without DONE/ERROR yields False.

    Scenario: the probe stream yields only a partial text chunk.

    Boundaries: proves an incomplete probe stream is an unhealthy verdict.

    On failure, first check: ``health_check`` must return ``False``.
    """
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="partial")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


@pytest.mark.parametrize(
    "code",
    [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED],
)
async def test_query_raises_retriable_on_transient_status(code: grpc.StatusCode) -> None:
    """[Unit] client: ``query`` maps transient status to a retriable domain error.

    Scenario: the stream raises UNAVAILABLE or DEADLINE_EXCEEDED while draining.

    Boundaries: exercises the gRPC-status-to-domain-error translation.

    On failure, first check: the raised ``OpenClaudeUnavailableError`` must have
    ``retriable is True`` and carry the status code name.
    """
    channel = _RaisingChannel(_rpc_error(code))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.retriable is True
    assert excinfo.value.status_code == code.name


async def test_query_raises_non_retriable_on_other_status() -> None:
    """[Unit] client: a non-transient status maps to a non-retriable domain error.

    Scenario: the stream raises PERMISSION_DENIED while draining.

    Boundaries: exercises the non-transient branch of status translation.

    On failure, first check: the raised error must have ``retriable is False`` and
    carry the PERMISSION_DENIED status name.
    """
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.PERMISSION_DENIED))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.retriable is False
    assert excinfo.value.status_code == grpc.StatusCode.PERMISSION_DENIED.name


async def test_terminal_error_frame_is_yielded_not_raised() -> None:
    """[Unit] client: an ERROR *frame* is surfaced as an AgentFrame, not raised.

    Scenario: a text chunk followed by an ERROR frame is drained via ``query``.

    Boundaries: regression guard distinguishing an ERROR frame from a gRPC status
    error.

    On failure, first check: the final frame must be an ERROR ``AgentFrame``
    instance, and draining must not raise.
    """
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="partial"), _msg(_ERROR, content="boom")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert frames[-1].frame_type is FrameKind.ERROR
    assert isinstance(frames[-1], AgentFrame)


def test_request_deadline_uses_request_timeout_s() -> None:
    """[Unit] client: ``_request_deadline`` returns ``request_timeout_s`` verbatim.

    Scenario: a client is built with distinct connect and request timeouts.

    Boundaries: exercises the deadline accessor only.

    On failure, first check: ``_request_deadline`` must equal the settings'
    ``request_timeout_s`` (42), not the connect timeout.
    """
    settings = _settings(connect_timeout_s=10, request_timeout_s=42)
    client = OpenClaudeGrpcClient(settings)

    assert client._request_deadline() == settings.request_timeout_s == 42


async def test_query_passes_request_deadline_to_rpc() -> None:
    """[Unit] client: ``query`` passes the per-request deadline to the RPC timeout.

    Scenario: a client with ``request_timeout_s=77`` drains a DONE-only stream.

    Boundaries: proves the request deadline reaches the streaming RPC's timeout.

    On failure, first check: the stub's recorded ``Query.timeout`` must equal 77.
    """
    settings = _settings(connect_timeout_s=10, request_timeout_s=77)
    channel = _FakeChannel([_msg(_DONE, content="")])
    client = OpenClaudeGrpcClient.from_channel(channel, settings)

    await _drain(client)

    # The real stub stored the fake multicallable returned by unary_stream.
    assert client._stub.Query.timeout == 77


async def test_health_check_logs_no_probe_or_response_text() -> None:
    """[Unit] client: no probe prompt or response text reaches a DEBUG sink.

    Scenario: a UNAVAILABLE probe runs with a DEBUG log sink attached; the
    captured records are scanned.

    Boundaries: enforces constraint C9 - only the status code name may appear, not
    the probe prompt or response payload.

    On failure, first check: the records must exclude the probe prompt and
    ``pong`` and include only the ``UNAVAILABLE`` status name.
    """
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.UNAVAILABLE))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    records, sink_id = _capture_debug_logs()
    try:
        assert await client.health_check() is False
    finally:
        logger.remove(sink_id)

    joined = "\n".join(records)
    assert client_mod._HEALTH_PROBE_PROMPT not in joined
    assert "pong" not in joined
    # The status code name is the only permitted diagnostic detail.
    assert any("UNAVAILABLE" in line for line in records)


async def test_health_check_false_on_unexpected_probe_exception() -> None:
    """[Unit] client: ``health_check`` swallows an unexpected probe error.

    Scenario: the probe stream raises a non-gRPC ``RuntimeError``.

    Boundaries: proves even unexpected errors do not escape ``health_check``.

    On failure, first check: ``health_check`` must return ``False`` without
    propagating the ``RuntimeError``.
    """
    channel = _RuntimeErrorChannel()
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    # Must not propagate the RuntimeError raised by the stream.
    assert await client.health_check() is False


async def test_health_check_false_when_cold_channel_creation_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Unit] client: a cold client whose channel creation raises yields False.

    Scenario: the insecure channel constructor is patched to raise; a cold client
    runs ``health_check``.

    Boundaries: proves failures during lazy channel creation are swallowed.

    On failure, first check: ``health_check`` must return ``False`` and not
    propagate the channel-creation error.
    """

    def _boom(*args: object, **kwargs: object) -> object:
        """Raise to simulate a failing cold channel creation."""
        raise RuntimeError("channel creation failed")

    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", _boom)

    client = OpenClaudeGrpcClient(_settings(use_tls=False))

    assert await client.health_check() is False


def test_ensure_channel_warns_on_plaintext_to_remote_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Unit] client: a non-loopback insecure endpoint emits a cleartext WARNING.

    Scenario: an insecure client bound to a remote host runs ``_ensure_channel``
    with a WARNING sink attached.

    Boundaries: enforces the cleartext-warning policy without leaking payload.

    On failure, first check: the warning must name the endpoint and mention
    ``cleartext`` while excluding the probe prompt and any ``prompt=`` payload.
    """
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", MagicMock(return_value=_FakeChannel()))

    client = OpenClaudeGrpcClient(_settings(grpc_url="remote.example.com:50051", use_tls=False))

    records, sink_id = _capture_warning_logs()
    try:
        client._ensure_channel()
    finally:
        logger.remove(sink_id)

    joined = "\n".join(records)
    assert "remote.example.com:50051" in joined
    assert "cleartext" in joined
    # Only the non-secret endpoint may appear; never the probe prompt/payload.
    assert client_mod._HEALTH_PROBE_PROMPT not in joined
    assert "prompt=" not in joined


@pytest.mark.parametrize("host", ["localhost:50051", "127.0.0.1:50051", "127.0.0.5:50051"])
def test_ensure_channel_no_plaintext_warning_for_loopback(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Unit] client: a loopback insecure endpoint emits no cleartext WARNING.

    Scenario: an insecure client bound to a loopback host runs ``_ensure_channel``
    with a WARNING sink attached.

    Boundaries: proves the cleartext warning is suppressed for loopback targets.

    On failure, first check: no captured record may mention ``cleartext``.
    """
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", MagicMock(return_value=_FakeChannel()))

    client = OpenClaudeGrpcClient(_settings(grpc_url=host, use_tls=False))

    records, sink_id = _capture_warning_logs()
    try:
        client._ensure_channel()
    finally:
        logger.remove(sink_id)

    assert not any("cleartext" in line for line in records)
