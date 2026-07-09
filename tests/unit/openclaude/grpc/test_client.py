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
        self._it = iter(frames)

    def __aiter__(self) -> _FakeStreamCall:
        return self

    async def __anext__(self) -> SimpleNamespace:
        try:
            return next(self._it)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeMultiCallable:
    """Callable returned by ``channel.unary_stream``; yields a scripted call."""

    def __init__(self, frames: list[SimpleNamespace]) -> None:
        self._frames = frames
        self.timeout: Optional[float] = None

    def __call__(self, request: object, timeout: Optional[float] = None) -> _FakeStreamCall:
        self.timeout = timeout
        return _FakeStreamCall(self._frames)


class _FakeChannel:
    """Minimal async gRPC channel double supporting ``unary_stream`` and ``close``."""

    def __init__(self, frames: Optional[list[SimpleNamespace]] = None) -> None:
        self._frames = frames or []
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> _FakeMultiCallable:
        return _FakeMultiCallable(self._frames)

    async def close(self, grace: Optional[float] = None) -> None:
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
        self._error = error

    def __aiter__(self) -> _RaisingStreamCall:
        return self

    async def __anext__(self) -> SimpleNamespace:
        raise self._error


class _RaisingChannel:
    """Channel double whose stream fails immediately with a gRPC status error."""

    def __init__(self, error: grpc.aio.AioRpcError) -> None:
        self._error = error
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        def _call(request: object, timeout: Optional[float] = None) -> _RaisingStreamCall:
            return _RaisingStreamCall(self._error)

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
        self.close_calls += 1


class _SlowStreamCall:
    """Async iterator that never yields, forcing an ``asyncio.wait_for`` timeout."""

    def __aiter__(self) -> _SlowStreamCall:
        return self

    async def __anext__(self) -> SimpleNamespace:
        await asyncio.sleep(3600)
        raise StopAsyncIteration


class _SlowChannel:
    """Channel double whose stream hangs indefinitely."""

    def __init__(self) -> None:
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        def _call(request: object, timeout: Optional[float] = None) -> _SlowStreamCall:
            return _SlowStreamCall()

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
        self.close_calls += 1


class _RuntimeErrorStreamCall:
    """Async iterator whose first ``__anext__`` raises a non-gRPC exception."""

    def __aiter__(self) -> _RuntimeErrorStreamCall:
        return self

    async def __anext__(self) -> SimpleNamespace:
        raise RuntimeError("unexpected stream failure")


class _RuntimeErrorChannel:
    """Channel double whose stream fails with an unexpected (non-gRPC) error."""

    def __init__(self) -> None:
        self.close_calls = 0

    def unary_stream(self, *args: object, **kwargs: object) -> object:
        def _call(request: object, timeout: Optional[float] = None) -> _RuntimeErrorStreamCall:
            return _RuntimeErrorStreamCall()

        return _call

    async def close(self, grace: Optional[float] = None) -> None:
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
    """A text stream terminated by DONE yields every frame in order."""
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
    """A stream terminated by an ERROR frame yields it as the final frame."""
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
    """Frames after the first terminal DONE are not yielded."""
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
    """An empty proto ``tool`` string becomes ``None`` on the frame."""
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
    """A non-empty proto ``tool`` string is preserved on the frame."""
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
    """A FRAME_TYPE_UNSPECIFIED frame raises rather than being dropped."""
    channel = _FakeChannel([_msg(_UNSPECIFIED, content="junk")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError):
        await _drain(client)


async def test_stream_without_terminal_frame_raises() -> None:
    """A stream that ends without DONE/ERROR is a transport failure."""
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="only")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError):
        await _drain(client)


async def test_close_idempotent_and_closes_channel() -> None:
    """close() shuts the channel once and is safe to call twice."""
    channel = _FakeChannel([_msg(_DONE, content="")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    await client.close()
    await client.close()

    assert channel.close_calls == 1


async def test_close_safe_when_channel_never_opened() -> None:
    """close() is a no-op when no channel was ever created."""
    client = OpenClaudeGrpcClient(_settings())

    await client.close()  # must not raise

    assert client._channel is None


def test_init_does_not_open_channel() -> None:
    """Constructing from settings creates neither channel nor stub."""
    client = OpenClaudeGrpcClient(_settings())

    assert client._channel is None
    assert client._stub is None


def test_from_channel_bypasses_lazy_creation() -> None:
    """from_channel binds the injected channel and builds the stub eagerly."""
    channel = _FakeChannel()
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert client._channel is channel
    assert client._stub is not None


def test_ensure_channel_uses_insecure_when_tls_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_ensure_channel selects an insecure channel when use_tls is False."""
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
    """_ensure_channel selects a secure channel when use_tls is True."""
    insecure = MagicMock(return_value=_FakeChannel())
    secure = MagicMock(return_value=_FakeChannel())
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", insecure)
    monkeypatch.setattr(client_mod.grpc.aio, "secure_channel", secure)

    client = OpenClaudeGrpcClient(_settings(use_tls=True))
    client._ensure_channel()

    secure.assert_called_once()
    insecure.assert_not_called()


def test_ensure_channel_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated _ensure_channel calls reuse the same channel and stub."""
    insecure = MagicMock(return_value=_FakeChannel())
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", insecure)

    client = OpenClaudeGrpcClient(_settings())
    first = client._ensure_channel()
    second = client._ensure_channel()

    assert first is second
    insecure.assert_called_once()


async def test_context_manager_closes_channel() -> None:
    """The async context manager closes the channel on exit."""
    channel = _FakeChannel([_msg(_DONE, content="")])

    async with OpenClaudeGrpcClient.from_channel(channel, _settings()) as client:
        assert isinstance(client, OpenClaudeGrpcClient)

    assert channel.close_calls == 1


# --- subtask 04: health_check(), timeouts, and status translation -----------


async def test_health_check_true_on_terminal_done() -> None:
    """health_check() returns True when the probe stream ends in DONE."""
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="pong"), _msg(_DONE, content="pong")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is True


async def test_health_check_false_on_unavailable() -> None:
    """health_check() returns False (never raises) on UNAVAILABLE."""
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.UNAVAILABLE))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_deadline_exceeded() -> None:
    """health_check() returns False (never raises) on DEADLINE_EXCEEDED."""
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.DEADLINE_EXCEEDED))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_timeout() -> None:
    """A stream that never answers within connect_timeout_s yields False."""
    client = OpenClaudeGrpcClient.from_channel(_SlowChannel(), _settings())
    # Shrink the connect deadline so the wait_for cancellation is near-instant.
    object.__setattr__(client._settings, "connect_timeout_s", 0.05)

    assert await client.health_check() is False


async def test_health_check_false_on_terminal_error_frame() -> None:
    """A terminal ERROR frame during a probe yields False, not True."""
    channel = _FakeChannel([_msg(_ERROR, content="boom")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_unspecified_frame() -> None:
    """A protocol-violating unspecified frame during a probe yields False."""
    channel = _FakeChannel([_msg(_UNSPECIFIED, content="junk")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


async def test_health_check_false_on_stream_without_terminal_frame() -> None:
    """A probe stream that ends without DONE/ERROR yields False."""
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="partial")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    assert await client.health_check() is False


@pytest.mark.parametrize(
    "code",
    [grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED],
)
async def test_query_raises_retriable_on_transient_status(code: grpc.StatusCode) -> None:
    """query() maps UNAVAILABLE / DEADLINE_EXCEEDED to a retriable domain error."""
    channel = _RaisingChannel(_rpc_error(code))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.retriable is True
    assert excinfo.value.status_code == code.name


async def test_query_raises_non_retriable_on_other_status() -> None:
    """A non-transient status (PERMISSION_DENIED) maps to a non-retriable error."""
    channel = _RaisingChannel(_rpc_error(grpc.StatusCode.PERMISSION_DENIED))
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    with pytest.raises(OpenClaudeUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.retriable is False
    assert excinfo.value.status_code == grpc.StatusCode.PERMISSION_DENIED.name


async def test_terminal_error_frame_is_yielded_not_raised() -> None:
    """Regression: an ERROR *frame* is surfaced as an AgentFrame, not raised."""
    channel = _FakeChannel([_msg(_TEXT_CHUNK, content="partial"), _msg(_ERROR, content="boom")])
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    frames = await _drain(client)

    assert frames[-1].frame_type is FrameKind.ERROR
    assert isinstance(frames[-1], AgentFrame)


def test_request_deadline_uses_request_timeout_s() -> None:
    """_request_deadline() returns settings.request_timeout_s verbatim."""
    settings = _settings(connect_timeout_s=10, request_timeout_s=42)
    client = OpenClaudeGrpcClient(settings)

    assert client._request_deadline() == settings.request_timeout_s == 42


async def test_query_passes_request_deadline_to_rpc() -> None:
    """query() hands the per-request deadline to the streaming RPC's timeout."""
    settings = _settings(connect_timeout_s=10, request_timeout_s=77)
    channel = _FakeChannel([_msg(_DONE, content="")])
    client = OpenClaudeGrpcClient.from_channel(channel, settings)

    await _drain(client)

    # The real stub stored the fake multicallable returned by unary_stream.
    assert client._stub.Query.timeout == 77


async def test_health_check_logs_no_probe_or_response_text() -> None:
    """No probe prompt or response text reaches any DEBUG log sink (C9)."""
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
    """health_check() swallows an unexpected probe error and returns False."""
    channel = _RuntimeErrorChannel()
    client = OpenClaudeGrpcClient.from_channel(channel, _settings())

    # Must not propagate the RuntimeError raised by the stream.
    assert await client.health_check() is False


async def test_health_check_false_when_cold_channel_creation_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cold client whose _ensure_channel() raises yields False, never raises."""

    def _boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("channel creation failed")

    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", _boom)

    client = OpenClaudeGrpcClient(_settings(use_tls=False))

    assert await client.health_check() is False


def test_ensure_channel_warns_on_plaintext_to_remote_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-loopback insecure endpoint emits a cleartext WARNING (no payload)."""
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
    """A loopback insecure endpoint does not emit the cleartext WARNING."""
    monkeypatch.setattr(client_mod.grpc.aio, "insecure_channel", MagicMock(return_value=_FakeChannel()))

    client = OpenClaudeGrpcClient(_settings(grpc_url=host, use_tls=False))

    records, sink_id = _capture_warning_logs()
    try:
        client._ensure_channel()
    finally:
        logger.remove(sink_id)

    assert not any("cleartext" in line for line in records)
