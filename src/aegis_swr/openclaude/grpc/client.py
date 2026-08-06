"""Typed async gRPC client for the OpenClaude sidecar.

This is the sole module in the codebase permitted to ``import grpc`` or the
generated ``_pb2`` / ``_pb2_grpc`` stubs (contract C3). Every caller outside
this file interacts through the typed :class:`AgentFrame` projection and the
:class:`FrameKind` enum, so no generated protobuf object ever leaks past this
boundary.
"""

from __future__ import annotations

import asyncio
import enum
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import grpc  # the ONLY module permitted to import grpc (C3)
from loguru import logger

from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.exceptions import OpenClaudeUnavailableError
from aegis_swr.openclaude.grpc.proto import openclaude_pb2, openclaude_pb2_grpc


class FrameKind(enum.Enum):
    """Domain mirror of the proto ``FrameType`` enum (C2).

    Keeping a domain enum means no caller imports the generated stub to compare
    frame types, preserving the C3 isolation boundary. The proto zero-value
    ``FRAME_TYPE_UNSPECIFIED`` is deliberately absent: a received unspecified
    frame is a protocol violation, not a valid :class:`FrameKind`.

    :cvar TEXT_CHUNK: Incremental response text.
    :cvar TOOL_CALL: Tool invocation; ``content`` holds args JSON.
    :cvar TOOL_RESULT: Tool output.
    :cvar PERMISSION_REQ: Awaiting-approval command.
    :cvar DONE: Terminal frame; ``content`` holds the full response text.
    :cvar ERROR: Terminal error frame; ``content`` holds the error message.
    """

    TEXT_CHUNK = 1
    TOOL_CALL = 2
    TOOL_RESULT = 3
    PERMISSION_REQ = 4
    DONE = 5
    ERROR = 6


@dataclass(frozen=True)
class AgentFrame:
    """A single parsed frame from the ``Query`` response stream (C2).

    A typed, ``grpc``-free projection of ``openclaude_pb2.AgentMessage`` so
    callers outside this file never touch a generated protobuf object.

    :ivar frame_type: The frame's :class:`FrameKind` (text, tool call, tool
        result, permission request, done, or error).
    :ivar content: Interpretation depends on ``frame_type`` (C2): text chunk,
        tool-call args JSON, tool output, awaiting-approval command, full
        response on ``DONE``, or error message on ``ERROR``.
    :ivar tool: Tool name for tool/permission frames; ``None`` otherwise.
    """

    frame_type: FrameKind
    content: str
    tool: Optional[str]


# Projection of the generated proto ``FrameType`` ints onto the domain enum.
# ``FRAME_TYPE_UNSPECIFIED`` (0) is intentionally excluded so the reverse
# lookup treats it as a protocol violation (see ``_to_frame``).
_FRAME_TYPE_TO_KIND: dict[int, FrameKind] = {
    openclaude_pb2.TEXT_CHUNK: FrameKind.TEXT_CHUNK,
    openclaude_pb2.TOOL_CALL: FrameKind.TOOL_CALL,
    openclaude_pb2.TOOL_RESULT: FrameKind.TOOL_RESULT,
    openclaude_pb2.PERMISSION_REQ: FrameKind.PERMISSION_REQ,
    openclaude_pb2.DONE: FrameKind.DONE,
    openclaude_pb2.ERROR: FrameKind.ERROR,
}

_TERMINAL_KINDS: frozenset[FrameKind] = frozenset({FrameKind.DONE, FrameKind.ERROR})

# Inert readiness probe: a fixed constant string with no directives. Whether it
# actually avoids triggering a tool or charging the token budget is a
# server-side (sidecar) guarantee the client cannot enforce; the client only
# guarantees the prompt it sends is this inert constant (see subtask 04).
_HEALTH_PROBE_PROMPT = "ping"

# gRPC status codes for which a transport failure is worth retrying: the server
# is down / the port is not open yet (``UNAVAILABLE``) or the request outran its
# deadline (``DEADLINE_EXCEEDED``). Any other code is treated as non-retriable.
_RETRIABLE_STATUS_CODES: frozenset[grpc.StatusCode] = frozenset(
    {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED}
)


def _is_loopback_host(grpc_url: str) -> bool:
    """Return whether ``grpc_url``'s host resolves to the local loopback.

    Task 01.0's validator guarantees a bare ``host[:port]`` (no scheme, no IPv6
    literal), so the host is everything before an optional ``:port``. Loopback
    means the host is ``localhost``, ``127.0.0.1``, or any ``127.*`` address.

    :param grpc_url: A validated bare ``host[:port]`` endpoint.
    :return: ``True`` if the host is loopback; ``False`` otherwise.
    """
    host = grpc_url.split(":", 1)[0]
    return host in {"localhost", "127.0.0.1"} or host.startswith("127.")


class OpenClaudeGrpcClient:
    """Typed, mock-friendly async client for the OpenClaude gRPC sidecar.

    The only object in the codebase that speaks gRPC. It hides the generated
    stubs behind typed methods that yield :class:`AgentFrame` values, translates
    gRPC status errors into domain exceptions, and never logs raw prompt or
    response text (C9).

    :ivar _settings: Connection and timeout configuration (C1).
    :ivar _channel: The gRPC channel; ``None`` until first use (lazy open).
    :ivar _stub: The generated ``AgentService`` stub; ``None`` until first use.
    """

    def __init__(self, settings: OpenClaudeSettings):
        """Construct a client from settings without opening a channel.

        :param settings: OpenClaude configuration; ``settings.grpc_url`` must be
            non-``None`` (a ``None`` URL means the backend is not registered and
            no client should be built - guarded upstream at ``app.py``).
        """
        self._settings = settings
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[openclaude_pb2_grpc.AgentServiceStub] = None

    @classmethod
    def from_channel(
        cls,
        channel: grpc.aio.Channel,
        settings: OpenClaudeSettings,
    ) -> OpenClaudeGrpcClient:
        """Build a client around a pre-existing channel (test seam).

        Injects a mock or in-process channel so unit tests can script a frame
        sequence without a live OpenClaude process. The channel is treated as
        already-open; lazy creation is bypassed.

        :param channel: An open (possibly mock) async gRPC channel.
        :param settings: OpenClaude configuration (timeouts, allowlists).
        :return: A client bound to ``channel``.
        """
        client = cls(settings)
        client._channel = channel
        client._stub = openclaude_pb2_grpc.AgentServiceStub(channel)
        return client

    def _ensure_channel(self) -> grpc.aio.Channel:
        """Lazily create the channel and stub on first use.

        Chooses a secure channel when ``settings.use_tls`` is set and an
        insecure channel otherwise (Task 01.0 guarantees ``grpc_url`` is a bare
        ``host[:port]`` with no scheme, so no scheme parsing occurs here).
        Idempotent: repeated calls return the same channel.

        :return: The live async gRPC channel.
        """
        if self._channel is not None:
            return self._channel

        target = self._settings.grpc_url
        if self._settings.use_tls:
            logger.debug("Opening secure OpenClaude gRPC channel to {}", target)
            channel = grpc.aio.secure_channel(target, grpc.ssl_channel_credentials())
        else:
            if not _is_loopback_host(target):
                # Prompts may embed incident payload/PII; over a non-loopback
                # insecure channel they travel in cleartext. Warn (never reject):
                # a trusted-network deployment is legitimate, so the exposure is
                # a conscious operator choice. Names only the non-secret endpoint.
                logger.warning(
                    "OpenClaude gRPC channel to remote host {} is plaintext (use_tls=False); "
                    "prompts will be sent in cleartext - enable TLS for a remote sidecar",
                    target,
                )
            logger.debug("Opening insecure OpenClaude gRPC channel to {}", target)
            channel = grpc.aio.insecure_channel(target)

        self._channel = channel
        self._stub = openclaude_pb2_grpc.AgentServiceStub(channel)
        return channel

    def _to_frame(self, msg: openclaude_pb2.AgentMessage) -> AgentFrame:
        """Project a generated ``AgentMessage`` onto an immutable :class:`AgentFrame`.

        Pure projection: the generated object is never mutated. An empty proto
        ``tool`` string becomes ``None`` (proto3 strings carry no presence). A
        ``FRAME_TYPE_UNSPECIFIED`` type is a protocol violation and is surfaced
        as a terminal stream error rather than silently dropped.

        :param msg: A single streamed ``AgentMessage`` frame.
        :return: The typed, ``grpc``-free frame projection.
        :raises OpenClaudeUnavailableError: on an unspecified/unknown frame type.
        """
        kind = _FRAME_TYPE_TO_KIND.get(msg.type)
        if kind is None:
            logger.debug("OpenClaude stream sent an unspecified/unknown frame type")
            raise OpenClaudeUnavailableError("OpenClaude stream sent an unspecified frame type (protocol violation)")
        return AgentFrame(frame_type=kind, content=msg.content, tool=msg.tool or None)

    async def query(
        self,
        prompt: str,
        run_id: str,
    ) -> AsyncIterator[AgentFrame]:
        """Delegate one task and yield parsed response frames (C2).

        Opens the channel on first call, issues the server-streaming ``Query``
        RPC under ``settings.request_timeout_s``, and yields one
        :class:`AgentFrame` per streamed ``AgentMessage`` until a terminal
        ``DONE`` or ``ERROR`` frame. The detailed gRPC status translation and
        timeout handling are defined in subtask 04.

        A caller that breaks out of this async generator early (before a
        terminal frame) leaves the underlying server-streaming RPC open. Call
        :meth:`close` - or use this client as an async context manager - to
        cancel the channel and avoid an abandoned stream.

        :param prompt: The open-ended task string handed to OpenClaude's loop.
        :param run_id: Run correlation id echoed on emitted EventBus events.
        :return: An async iterator of parsed frames.
        :raises OpenClaudeUnavailableError: when the stream fails at the
            transport level or ends without a terminal frame (see subtask 04).
        """
        self._ensure_channel()
        request = openclaude_pb2.PromptRequest(prompt=prompt, run_id=run_id)

        logger.debug("Issuing OpenClaude Query RPC")
        call = self._stub.Query(request, timeout=self._request_deadline())

        terminal_seen = False
        try:
            async for msg in call:
                frame = self._to_frame(msg)
                yield frame
                if frame.frame_type in _TERMINAL_KINDS:
                    terminal_seen = True
                    return
        except grpc.aio.AioRpcError as exc:
            logger.debug("OpenClaude Query RPC failed with gRPC status {}", exc.code())
            raise self._translate_status(exc) from exc

        if not terminal_seen:
            logger.debug("OpenClaude stream ended without a terminal DONE/ERROR frame")
            raise OpenClaudeUnavailableError("OpenClaude stream ended without a terminal frame")

    def _request_deadline(self) -> float:
        """Per-request gRPC deadline in seconds from ``settings.request_timeout_s``.

        :return: The stream deadline passed as ``timeout=`` to the RPC.
        """
        return self._settings.request_timeout_s

    @staticmethod
    def _translate_status(error: grpc.aio.AioRpcError) -> OpenClaudeUnavailableError:
        """Map a gRPC status error onto a domain exception.

        ``UNAVAILABLE`` and ``DEADLINE_EXCEEDED`` map to
        :class:`OpenClaudeUnavailableError` flagged retriable (a transient
        transport failure). Every other status code maps to the same type
        flagged non-retriable, so no bare ``grpc`` exception escapes this file
        (C3). The returned exception carries only the gRPC status code name -
        never the response payload (C9).

        :param error: The gRPC status error raised by the stream.
        :return: An :class:`OpenClaudeUnavailableError` carrying the status code
            name and a retriable flag (never the response payload).
        """
        code = error.code()
        retriable = code in _RETRIABLE_STATUS_CODES
        return OpenClaudeUnavailableError(
            "OpenClaude gRPC stream failed at the transport level",
            retriable=retriable,
            status_code=code.name,
        )

    async def _probe(self) -> bool:
        """Consume a single health-probe stream, returning whether it succeeded.

        Issues the inert ``_HEALTH_PROBE_PROMPT`` query bounded by
        ``connect_timeout_s`` at the transport level and returns ``True`` only on
        a terminal ``DONE`` frame. A terminal ``ERROR`` frame, an
        unspecified/unknown frame type (protocol violation), or a stream that
        ends without a terminal frame yields ``False``. Never logs the probe
        response text (C9).

        :return: ``True`` on a terminal ``DONE``; ``False`` otherwise.
        """
        self._ensure_channel()
        request = openclaude_pb2.PromptRequest(prompt=_HEALTH_PROBE_PROMPT, run_id="health-check")
        call = self._stub.Query(request, timeout=self._settings.connect_timeout_s)

        async for msg in call:
            kind = _FRAME_TYPE_TO_KIND.get(msg.type)
            if kind is FrameKind.DONE:
                return True
            if kind is FrameKind.ERROR:
                logger.debug("OpenClaude health check received a terminal ERROR frame")
                return False
            if kind is None:
                logger.debug("OpenClaude health check received an unspecified frame (protocol violation)")
                return False

        logger.debug("OpenClaude health check stream ended without a terminal DONE/ERROR frame")
        return False

    async def health_check(self) -> bool:
        """Probe the sidecar; return whether it answered within the timeout.

        Issues a minimal ``Query`` probe and consumes the stream up to
        ``settings.connect_timeout_s`` - the coroutine is bounded by
        :func:`asyncio.wait_for` and the transport by the gRPC call ``timeout=``.
        Returns ``True`` only if a terminal ``DONE`` frame is observed inside
        that window. Any transport failure, timeout, ``ERROR`` frame, or protocol
        violation yields ``False``.

        This method **never raises** - it is the readiness predicate used by the
        process lifecycle manager (Task 03.0) and must be safe to poll. Any
        unexpected error (including a failure inside ``_ensure_channel`` on a
        cold client or a synchronous ``grpc.RpcError``) is caught and mapped to
        ``False`` by a typed ``except Exception`` backstop; ``BaseException``
        (e.g. ``asyncio.CancelledError``) still propagates so cooperative
        cancellation is preserved. Failure reasons are logged at ``DEBUG`` using
        only the exception class / gRPC status code, never the probe response
        text (C9).

        :return: ``True`` if a terminal ``DONE`` arrived within
            ``connect_timeout_s``; ``False`` otherwise.
        """
        try:
            return await asyncio.wait_for(self._probe(), timeout=self._settings.connect_timeout_s)
        except asyncio.TimeoutError:
            logger.debug(
                "OpenClaude health check timed out after {}s",
                self._settings.connect_timeout_s,
            )
            return False
        except grpc.aio.AioRpcError as exc:
            logger.debug("OpenClaude health check failed with gRPC status {}", exc.code())
            return False
        except Exception as exc:  # safety net - health_check() must never raise
            logger.debug("OpenClaude health check raised unexpected {}", type(exc).__name__)
            return False

    async def close(self):
        """Shut the channel down, releasing all gRPC resources.

        Idempotent; safe to call when the channel was never opened. Emits no
        raw payload text to any log sink.
        """
        if self._channel is None:
            return
        logger.debug("Closing OpenClaude gRPC channel")
        await self._channel.close()
        self._channel = None
        self._stub = None

    async def __aenter__(self) -> OpenClaudeGrpcClient:
        """Enter the async context, returning this client unchanged.

        The channel is still opened lazily on first :meth:`query`; entering the
        context does not eagerly dial the sidecar.

        :return: This client.
        """
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[object],
    ):
        """Exit the async context, closing the channel so it cannot leak.

        :param exc_type: Exception type raised in the ``async with`` body, if any.
        :param exc: Exception instance raised in the body, if any.
        :param tb: Traceback for the raised exception, if any.
        """
        await self.close()
