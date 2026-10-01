"""Typed async client for the OpenHands REST/WS sidecar (contract C3, C8).

This is the **sole** module in the codebase permitted to import the OpenHands
HTTP/WS client library (``socketio`` — python-socketio's async client), exactly
as ``aegis_swr/openclaude/grpc/client.py`` is the only ``grpc`` importer. Every
caller outside this file interacts through the typed :class:`AgentEvent`
projection and the :class:`EventKind` enum, so no raw library object ever leaks
past this boundary. The REST surface uses ``httpx`` (a general, already-declared
project dependency), kept confined to this file for symmetry.

**Dependency reality (2026, this environment).** ``socketio`` is *not installed*
and is deliberately *not* added as a dependency by Task 07.0. The import is
guarded so importing this module never fails: the production Socket.IO path is
inert until the library is present, and every unit test drives the injection
seam (:meth:`OpenHandsClient.from_session`) with fakes — no test imports
``socketio``, opens a socket, or contacts a live sidecar. The REST/WS wire shapes
(``POST /api/conversations``, the Socket.IO ``oh_event`` / ``oh_user_action``
messages, and the raw event dict projected by :meth:`OpenHandsClient._to_event`)
follow the researched V1-server shape recorded in the task spec and are
**assumed-pending-integration-test**: Task 11.0's live integration test is the
first to exercise them against a real OpenHands server.
"""

from __future__ import annotations

import asyncio
import contextlib
import enum
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import httpx
from loguru import logger

from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError

try:
    import socketio  # type: ignore[import-not-found]  # the ONLY module permitted to import the OpenHands HTTP/WS client lib (C3)
except ImportError:  # pragma: no cover - the OpenHands client lib is optional/absent in this env
    socketio = None

#: Server→client Socket.IO message carrying one Action/Observation event.
_OH_EVENT = "oh_event"
#: Client→server Socket.IO message carrying the delegated task (never a URL/argv).
_OH_USER_ACTION = "oh_user_action"

#: Transport error types translated into :class:`OpenHandsUnavailableError`. A
#: dropped connection (``OSError``/``ConnectionError``) and a per-request
#: deadline (``asyncio.TimeoutError`` from :func:`asyncio.wait_for`) are the two
#: retriable transport failures; ``httpx.HTTPError`` covers the REST surface.
#: ``socketio``'s own error classes are appended when the library is present so
#: no raw library exception escapes this file (C3).
_TRANSPORT_ERROR_TYPES: tuple[type[BaseException], ...] = (
    OSError,
    asyncio.TimeoutError,
    httpx.HTTPError,
)
if socketio is not None:  # pragma: no cover - the OpenHands client lib is absent in this env
    _TRANSPORT_ERROR_TYPES = _TRANSPORT_ERROR_TYPES + (
        socketio.exceptions.ConnectionError,
        socketio.exceptions.SocketIOError,
    )


class EventKind(enum.Enum):
    """Kind of a single event projected from the OpenHands ``oh_event`` stream.

    A domain enum mirroring the OpenHands event taxonomy so no caller outside
    this file compares against a raw library event object (preserves C3). The
    OpenHands stream is a chronological log of immutable Action / Observation
    events; this enum collapses it to the shapes the tool (Task 08.0) needs, with
    two terminal kinds (:attr:`FINISHED`, :attr:`ERROR`).

    :cvar MESSAGE: An assistant text message chunk (accumulated into the answer).
    :cvar ACTION: The agent invoked a tool inside the sandbox.
    :cvar OBSERVATION: A tool returned its result to the agent.
    :cvar PERMISSION: The agent requested a non-allowlisted / confirmation-gated
        action.
    :cvar FINISHED: Terminal — the agent reached a finished/awaiting-input state.
    :cvar ERROR: Terminal — the agent or runtime reported a logical error.
    """

    MESSAGE = "message"
    ACTION = "action"
    OBSERVATION = "observation"
    PERMISSION = "permission"
    FINISHED = "finished"
    ERROR = "error"


@dataclass(frozen=True)
class AgentEvent:
    """A single parsed event from the OpenHands ``oh_event`` stream (C8).

    A typed, library-free projection of one OpenHands Action / Observation event
    so callers outside this file never touch a raw library object. This is the
    **transport-layer** projection and is deliberately distinct from the
    ``openhands.*`` :class:`~aegis_swr.core.events.DomainEvent` taxonomy (Task
    09.0), which the tool derives *from* these values for the ``EventBus``.

    :ivar kind: The event's :class:`EventKind`.
    :ivar content: Interpretation depends on ``kind``: assistant text for
        ``MESSAGE``; a payload-free summary for ``ACTION`` / ``OBSERVATION``; the
        full accumulated answer on ``FINISHED``; the error message on ``ERROR``.
        Never logged raw (C13).
    :ivar tool: Tool name for ``ACTION`` / ``OBSERVATION`` / ``PERMISSION``
        events; ``None`` otherwise.
    :ivar token_usage: Server-reported token total when the terminal event
        carries usage, else ``None`` (the tool falls back to the boundary
        estimate — C9).
    """

    kind: EventKind
    content: str
    tool: Optional[str]
    token_usage: Optional[int]


#: Projection of the raw OpenHands ``oh_event`` ``kind`` discriminator onto the
#: domain :class:`EventKind`. The raw string set is the researched V1-server
#: taxonomy (assumed-pending-integration-test, Task 11.0); an unmapped kind is a
#: protocol violation surfaced as a terminal :attr:`EventKind.ERROR` (never
#: silently dropped), mirroring OpenClaude's ``FRAME_TYPE_UNSPECIFIED`` handling.
_RAW_KIND_TO_EVENT_KIND: dict[str, EventKind] = {
    "message": EventKind.MESSAGE,
    "action": EventKind.ACTION,
    "observation": EventKind.OBSERVATION,
    "permission": EventKind.PERMISSION,
    "finished": EventKind.FINISHED,
    "error": EventKind.ERROR,
}

#: Terminal kinds after which :meth:`OpenHandsClient.run` stops iterating.
_TERMINAL_KINDS: frozenset[EventKind] = frozenset({EventKind.FINISHED, EventKind.ERROR})


class OpenHandsClient:
    """Typed, mock-friendly async client for the OpenHands REST/WS sidecar.

    The only object in the codebase that speaks the OpenHands HTTP/WS protocol.
    It hides the REST session and the Socket.IO connection behind typed methods
    that yield :class:`AgentEvent` values, translates transport errors into
    domain exceptions, and never logs raw task or response text (C13).

    :ivar _settings: Connection and timeout configuration (C8).
    :ivar _sio: The async Socket.IO client; ``None`` until first use (lazy open).
    :ivar _http: The async REST session; ``None`` until first use.
    :ivar _conversation_id: The active conversation id, or ``None`` before
        :meth:`run` opens one.
    :ivar _ready: Whether the sessions are already open (set by
        :meth:`from_session`), so :meth:`_ensure_client` is a no-op.
    """

    def __init__(self, settings: OpenHandsSettings):
        """Construct a client from settings without opening any connection.

        :param settings: OpenHands configuration; ``settings.server_url`` must be
            non-``None`` (a ``None`` URL means the backend is not registered and
            no client should be built — guarded upstream in the composition root,
            Task 10.0).
        """
        self._settings = settings
        self._sio: Any = None
        self._http: Any = None
        self._conversation_id: Optional[str] = None
        self._ready = False

    @classmethod
    def from_session(
        cls,
        sio: Any,
        http: Any,
        settings: OpenHandsSettings,
    ) -> OpenHandsClient:
        """Build a client around pre-existing REST/WS sessions (test seam).

        Injects a mock Socket.IO client and a mock HTTP session so unit tests can
        script an ``oh_event`` sequence without a live OpenHands process. The
        sessions are treated as already-open; lazy creation is bypassed.

        :param sio: An async Socket.IO client (real or mock).
        :param http: An async HTTP session (real or mock) for the REST surface.
        :param settings: OpenHands configuration (URL, timeouts, allowlist).
        :return: A client bound to the injected sessions.
        """
        client = cls(settings)
        client._sio = sio
        client._http = http
        client._ready = True
        return client

    async def _ensure_client(self):
        """Lazily create the REST session and Socket.IO client on first use.

        Idempotent: repeated calls reuse the already-created sessions. Never
        opens a socket in :meth:`__init__` (that stores settings only). When the
        OpenHands client library is absent this raises
        :class:`OpenHandsUnavailableError` rather than an import error, so a
        missing dependency surfaces as an unavailable backend (C3/C4).

        :raises OpenHandsUnavailableError: If the OpenHands client library is not
            installed in this environment.
        """
        if self._ready:
            return
        # Production path — requires the real OpenHands client library, which is
        # absent in this environment, so it is inert under unit tests (which use
        # ``from_session``). Exercised first by Task 11.0's integration test.
        if socketio is None:  # pragma: no cover - guarded; unit tests use from_session
            raise OpenHandsUnavailableError(
                "the OpenHands client library (socketio) is not installed",
                server_url=self._settings.server_url,
                retriable=False,
            )
        self._http = httpx.AsyncClient()  # pragma: no cover - real transport, integration only
        self._sio = socketio.AsyncClient()  # pragma: no cover - real transport, integration only
        self._ready = True  # pragma: no cover - real transport, integration only

    def _base_url(self) -> str:
        """Return the configured server base URL without a trailing slash.

        :raises OpenHandsUnavailableError: If ``settings.server_url`` is unset.
        :return: The base ``http(s)://host[:port]`` endpoint to dial.
        """
        server_url = self._settings.server_url
        if server_url is None:
            raise OpenHandsUnavailableError(
                "OpenHands server_url is not configured; the backend is not registered",
                retriable=False,
            )
        return server_url.rstrip("/")

    async def _create_conversation(self, run_id: str) -> str:
        """Create an OpenHands conversation over REST and return its id.

        Issues ``POST /api/conversations`` under ``settings.connect_timeout_s``,
        selecting the sandboxed runtime per ``settings`` (C8). The task text is
        **not** sent here (it is dispatched as an ``oh_user_action`` in
        :meth:`run`); nothing payload-bearing is logged.

        :param run_id: Run correlation id echoed on emitted EventBus events.
        :return: The server-assigned conversation id.
        :raises OpenHandsUnavailableError: If the REST call returns a non-2xx
            status or the response omits a conversation id.
        """
        response = await self._http.post(
            f"{self._base_url()}/api/conversations",
            json={"runtime": self._settings.runtime_mode},
            timeout=self._settings.connect_timeout_s,
        )
        status = int(response.status_code)
        if not 200 <= status < 300:
            raise OpenHandsUnavailableError(
                "OpenHands rejected the create-conversation request",
                server_url=self._base_url(),
                retriable=True,
                status_code=str(status),
            )
        body = response.json()
        conversation_id = body.get("conversation_id") if isinstance(body, dict) else None
        if not isinstance(conversation_id, str) or not conversation_id:
            raise OpenHandsUnavailableError(
                "OpenHands create-conversation response carried no conversation id",
                server_url=self._base_url(),
                retriable=True,
            )
        return conversation_id

    def _stream_url(self, conversation_id: str) -> str:
        """Build the Socket.IO stream URL carrying only the conversation id (C13).

        The conversation id (never the task text) travels in the query string.

        :param conversation_id: The server-assigned conversation id.
        :return: The base URL with the conversation id query parameter appended.
        """
        return f"{self._base_url()}/socket.io/?conversation_id={conversation_id}"

    async def run(
        self,
        task: str,
        run_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """Delegate one task and yield parsed Action/Observation events (C8).

        Creates a conversation, connects the Socket.IO stream at
        ``/socket.io/?conversation_id=<id>``, sends *task* as an
        ``oh_user_action`` (never in a URL or argv), and yields one
        :class:`AgentEvent` per received ``oh_event`` until a terminal
        ``FINISHED`` / ``ERROR`` kind. The whole exchange is bounded by
        ``settings.request_timeout_s``.

        :param task: The open-ended code-navigation task handed to OpenHands.
        :param run_id: Run correlation id echoed on emitted EventBus events.
        :return: An async iterator of parsed events.
        :raises OpenHandsUnavailableError: On connection loss, timeout, or any
            transport error (no raw library exception escapes — C3).
        """
        await self._ensure_client()
        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def _on_event(data: Any):
            """Enqueue one raw ``oh_event`` payload for the run loop to project."""
            await queue.put(data)

        logger.debug("Opening OpenHands conversation stream for run {}", run_id)
        try:
            conversation_id = await self._create_conversation(run_id)
            self._conversation_id = conversation_id
            self._sio.on(_OH_EVENT, _on_event)
            await self._sio.connect(self._stream_url(conversation_id))
            # Task text travels ONLY in the action body, never a URL/query/argv (C13).
            await self._sio.emit(_OH_USER_ACTION, {"task": task, "run_id": run_id})
            while True:
                raw = await asyncio.wait_for(queue.get(), timeout=self._settings.request_timeout_s)
                event = self._to_event(raw)
                yield event
                if event.kind in _TERMINAL_KINDS:
                    return
        except _TRANSPORT_ERROR_TYPES as err:
            logger.debug("OpenHands stream failed at the transport level: {}", type(err).__name__)
            raise OpenHandsUnavailableError(
                "OpenHands REST/WS stream failed at the transport level",
                server_url=self._base_url(),
                retriable=True,
            ) from err

    def _to_event(self, raw: Any) -> AgentEvent:
        """Project one raw ``oh_event`` payload onto an immutable :class:`AgentEvent`.

        Pure mapping: the raw object is never mutated and only a payload-free
        summary (kind, tool name, token total) plus assistant/error text is
        copied. A raw event whose ``kind`` cannot be mapped is a protocol
        violation surfaced as a terminal :attr:`EventKind.ERROR` event rather
        than silently dropped (same discipline as OpenClaude's unspecified
        frame). The raw event shape is assumed-pending-integration-test.

        :param raw: One raw ``oh_event`` payload (expected to be a mapping).
        :return: The typed, library-free event projection.
        """
        kind_str = raw.get("kind") if isinstance(raw, dict) else None
        kind = _RAW_KIND_TO_EVENT_KIND.get(kind_str) if isinstance(kind_str, str) else None
        if kind is None:
            logger.debug("OpenHands stream sent an unmappable event kind (protocol violation)")
            return AgentEvent(
                kind=EventKind.ERROR,
                content="OpenHands stream sent an unmappable event kind",
                tool=None,
                token_usage=None,
            )
        content = raw.get("content", "")
        tool = raw.get("tool") or None
        token_usage = self._coerce_token_usage(raw.get("token_usage")) if kind in _TERMINAL_KINDS else None
        return AgentEvent(
            kind=kind,
            content=str(content) if content is not None else "",
            tool=tool if isinstance(tool, str) else None,
            token_usage=token_usage,
        )

    @staticmethod
    def _coerce_token_usage(value: Any) -> Optional[int]:
        """Coerce a server-reported token total to a non-negative ``int`` (C9).

        :param value: The raw ``token_usage`` value from a terminal event.
        :return: The integer token total, or ``None`` when absent/non-numeric so
            the tool falls back to the boundary estimate.
        """
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None

    async def health_check(self) -> bool:
        """Probe server reachability; return ``False`` (never raise) on failure.

        Issues a lightweight REST status probe (no conversation, no task, no
        token budget touched) and consumes the response up to
        ``settings.connect_timeout_s``. Returns ``True`` only if the server
        answered healthy inside that window. Any transport failure, timeout, or
        non-healthy status yields ``False``. This method **never raises** — it is
        the readiness predicate the process lifecycle manager (subtask 02) polls.

        A broad ``except Exception`` backstop guarantees the never-raise contract
        (an unexpected error inside a cold ``_ensure_client`` or the transport is
        mapped to ``False``); ``BaseException`` (e.g. ``asyncio.CancelledError``)
        still propagates so cooperative cancellation is preserved. This file is
        listed in ``[tool.flakeforge].exclude`` so the X002 rule permits
        the backstop, exactly as ``openclaude/grpc/client.py`` is.

        :return: ``True`` if the server answered healthy within
            ``connect_timeout_s``; ``False`` otherwise.
        """
        try:
            return await asyncio.wait_for(self._probe(), timeout=self._settings.connect_timeout_s)
        except asyncio.TimeoutError:
            logger.debug("OpenHands health check timed out after {}s", self._settings.connect_timeout_s)
            return False
        except Exception as exc:  # safety net — health_check() must never raise
            logger.debug("OpenHands health check failed with {}", type(exc).__name__)
            return False

    async def _probe(self) -> bool:
        """Issue one REST status probe, returning whether the server is healthy.

        Bounded at the transport level by ``settings.connect_timeout_s`` and
        never logs the response body (C13).

        :return: ``True`` on a 2xx status; ``False`` on any non-healthy status.
        """
        await self._ensure_client()
        response = await self._http.get(
            f"{self._base_url()}/health",
            timeout=self._settings.connect_timeout_s,
        )
        status = int(response.status_code)
        return 200 <= status < 300

    async def close(self):
        """Close the Socket.IO connection and REST session, releasing resources.

        Idempotent; safe to call when neither was ever opened. Disconnects any
        active conversation stream and emits no raw payload text to any log sink.
        """
        sio = self._sio
        http = self._http
        if sio is not None:
            with contextlib.suppress(*_TRANSPORT_ERROR_TYPES):
                await sio.disconnect()
        if http is not None:
            with contextlib.suppress(*_TRANSPORT_ERROR_TYPES):
                await http.aclose()
        self._sio = None
        self._http = None
        self._conversation_id = None
        self._ready = False
