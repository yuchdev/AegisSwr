# 01 - `OpenHandsClient` (sole client-library importer)

**Parent task:** 07.0 OpenHands Client & Process Lifecycle
**State:** ✅ Complete
**Depends on:** 06.0 (imports `OpenHandsSettings` from `aegis_swr.openhands.config`)
**Blocks:** 02 (Process Lifecycle health-checks via this client), 08.0 (`OpenHandsTool` delegates through this client)

## Objective

Implement `aegis_swr/openhands/client.py` — `OpenHandsClient`, the **only** file
in the entire codebase permitted to import the OpenHands HTTP/WS client library
(contract C3, exactly analogous to `openclaude/grpc/client.py` being the sole
`grpc` importer). The client owns the REST session and the Socket.IO event
connection, lazily created on first use; it creates an OpenHands conversation,
sends the delegated task, subscribes to the server's `oh_event` stream, and
exposes `run(task, run_id)` as an async generator that yields typed, library-free
`AgentEvent` projections of the Action/Observation stream until the terminal
agent state. It is constructed either from `OpenHandsSettings` (production) or
from an injected session via `from_session(...)` (tests), so unit tests script an
`oh_event` sequence through a mock session with no live OpenHands sidecar.
`health_check()` and the transport-error-to-exception translation are specified
here too — `health_check()` returns a plain `bool` and never raises; `run()`
raises `OpenHandsUnavailableError` on any transport failure so no raw
library exception escapes this file (C3).

> **OpenHands transport (research, 2026, V1 server).** The OpenHands server is a
> FastAPI app that creates conversations over REST (`POST /api/conversations`)
> and streams the conversation's Action/Observation events over **Socket.IO** at
> `ws://<host>/socket.io/?conversation_id=<id>`. Server→client events arrive as
> the `oh_event` message; client→server actions are sent as `oh_user_action`. The
> conversation is a typed, replayable stream of immutable Action / Observation
> events; the terminal signal is the agent reaching a finished / error /
> awaiting-input state. Concretely the "OpenHands HTTP/WS client library" is an
> async Socket.IO client (`python-socketio`'s async client) plus an async HTTP
> client for the REST surface — settle the exact dependency with `python-expert`,
> but **whatever it is, it is imported in this file only** (C3).

## File: `aegis_swr/openhands/client.py`

```python
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import socketio  # noqa: the ONLY module permitted to import the OpenHands HTTP/WS client lib (C3)

from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError


class EventKind(enum.Enum):
    """Kind of a single event projected from the OpenHands ``oh_event`` stream.

    A domain enum mirroring the OpenHands event taxonomy so no caller outside
    this file compares against a raw library event object (preserves C3). The
    OpenHands stream is a chronological log of immutable Action / Observation
    Pydantic events; this enum collapses it to the shapes the tool (Task 08.0)
    needs, with two terminal kinds (:attr:`FINISHED`, :attr:`ERROR`).

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
    """

    def __init__(self, settings: OpenHandsSettings):
        """Construct a client from settings without opening any connection.

        :param settings: OpenHands configuration; ``settings.server_url`` must be
            non-``None`` (a ``None`` URL means the backend is not registered and
            no client should be built — guarded upstream in the composition root,
            Task 10.0).
        """
        ...

    @classmethod
    def from_session(
        cls,
        sio: Any,
        http: Any,
        settings: OpenHandsSettings,
    ) -> "OpenHandsClient":
        """Build a client around pre-existing REST/WS sessions (test seam).

        Injects a mock Socket.IO client and a mock HTTP session so unit tests can
        script an ``oh_event`` sequence without a live OpenHands process. The
        sessions are treated as already-open; lazy creation is bypassed.

        :param sio: An async Socket.IO client (real or mock).
        :param http: An async HTTP session (real or mock) for the REST surface.
        :param settings: OpenHands configuration (URL, timeouts, allowlist).
        :return: A client bound to the injected sessions.
        """
        ...

    async def _ensure_client(self):
        """Lazily create the REST session and Socket.IO client on first use.

        Idempotent: repeated calls reuse the already-created sessions. Never
        opens a socket in :meth:`__init__` (that stores settings only).
        """
        ...

    async def _create_conversation(self, run_id: str) -> str:
        """Create an OpenHands conversation over REST and return its id.

        Issues ``POST /api/conversations`` under ``settings.connect_timeout_s``,
        selecting the sandboxed runtime per ``settings`` (C8). The task text is
        **not** sent here (it is dispatched as an ``oh_user_action`` in
        :meth:`run`); nothing payload-bearing is logged.

        :param run_id: Run correlation id echoed on emitted EventBus events.
        :return: The server-assigned conversation id.
        :raises OpenHandsUnavailableError: If the REST call fails or times out.
        """
        ...

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
        ...

    async def health_check(self) -> bool:
        """Probe server reachability; return ``False`` (never raise) on failure.

        Issues a lightweight REST status probe (no conversation, no task, no
        token budget touched) and consumes the response up to
        ``settings.connect_timeout_s``. Returns ``True`` only if the server
        answered healthy inside that window. Any transport failure, timeout, or
        non-healthy status yields ``False``. This method **never raises** — it is
        the readiness predicate the process lifecycle manager (subtask 02) polls.

        :return: ``True`` if the server answered healthy within
            ``connect_timeout_s``; ``False`` otherwise.
        """
        ...

    async def close(self):
        """Close the Socket.IO connection and REST session, releasing resources.

        Idempotent; safe to call when neither was ever opened. Disconnects any
        active conversation stream and emits no raw payload text to any log sink.
        """
        ...
```

## File: `aegis_swr/openhands/exceptions.py` (minimal forward-declaration)

```python
from __future__ import annotations

from typing import Optional


class OpenHandsUnavailableError(Exception):
    """Raised when the OpenHands REST/WS sidecar cannot be reached.

    **Forward-declared here** so ``client.py`` (Task 07.0) can raise it before
    Task 09.0 canonicalises the full OpenHands exception hierarchy — mirroring how
    ``openclaude/events.py`` / ``exceptions.py`` were declared ahead of their
    canonical task. Task 09.0 **must preserve** this name and the ``message`` /
    ``server_url`` / ``retriable`` shape and may only extend it, so existing
    imports and raises keep working. The message never formats task/response/
    credential text (C13).

    :param message: Human-readable, payload-free description of the failure.
    :param server_url: Server URL that could not be reached, for diagnostics;
        configuration, never incident payload. ``None`` when not yet known.
    :param retriable: Whether the caller may retry (a dropped connection /
        timeout is retriable; a config-shape failure is not).
    :ivar server_url: The unreachable endpoint, or ``None``.
    :ivar retriable: Whether the operation may be retried.
    """

    def __init__(
        self,
        message: str,
        server_url: Optional[str] = None,
        *,
        retriable: bool = True,
    ):
        """Record the endpoint and retriability on the error (payload-free)."""
        self.server_url = server_url
        self.retriable = retriable
        super().__init__(message)
```

## Implementation notes

- **Sole importer (C3).** The OpenHands HTTP/WS client library (`socketio` +
  whatever REST client is chosen) is imported **only** in this file, exactly as
  `grpc` lives only in `openclaude/grpc/client.py`. Add the `# noqa` /
  import-isolation marker the Task 11.0 isolation test / CI `grep` job keys on.
  No caller imports the library or a raw library event object — `AgentEvent` /
  `EventKind` are the only types that cross the boundary.
- **Lazy sessions.** `__init__` stores settings only; the Socket.IO client and
  REST session are created in `_ensure_client()` on the first `run()` /
  `health_check()` call. `from_session()` sets both directly and marks them ready
  so `_ensure_client()` is a no-op — this is the unit-test seam (mirrors
  `OpenClaudeGrpcClient.from_channel`).
- **Event projection is a pure mapping.** `_to_event(raw)` maps one raw
  `oh_event` payload onto an immutable `AgentEvent`, collapsing the OpenHands
  event kinds onto `EventKind` and copying only a payload-free summary
  (`tool` name, sizes) plus assistant text into `content`. `AgentEvent` is
  `frozen=True`; no library object is mutated or leaked. A raw event whose kind
  cannot be mapped is treated as a protocol violation and surfaced as a terminal
  `ERROR` `AgentEvent`, never silently dropped (same discipline as OpenClaude's
  `FRAME_TYPE_UNSPECIFIED`).
- **Terminal-event invariant.** `run()` stops iterating after the first
  `FINISHED` or `ERROR` event; a stream that drops without a terminal event is a
  transport failure surfaced via the translation below.
- **Token usage (C9).** When the terminal event carries server-reported usage,
  set `token_usage` from it; otherwise leave it `None` and let the tool (Task
  08.0) fall back to the boundary estimate `max(1, len(content) // 4)`. Exactly
  one event per run carries the token figure (C10) — the terminal one.
- **Task text is never in a URL/argv (C13).** The conversation id goes in the
  Socket.IO query string; the task text is sent only in the `oh_user_action`
  message body, never in a URL, query parameter, or process argument — the same
  "never argv/URL secrets" discipline Claude Code applies to argv (C6).
- **`health_check()` timeout.** Wrap the REST status probe in
  `asyncio.wait_for(..., timeout=settings.connect_timeout_s)` and bound the
  underlying HTTP call by the same value, so both the coroutine and the transport
  are bounded. On `asyncio.TimeoutError`, any transport error, or a non-healthy
  status, catch narrowly (no bare `except:`) and return `False`; log the failure
  reason at `DEBUG` using the status/exception class only — never the response
  body.
- **`run()` translation.** Wrap the REST call and the Socket.IO consumption in a
  narrow `try/except` over the library's connection/timeout error types; on catch
  raise `OpenHandsUnavailableError(..., retriable=True) from err`. A dropped
  connection and a `request_timeout_s` deadline are the two retriable transport
  failures. A terminal `ERROR` *event* (the stream opened fine but OpenHands
  reported a logical error) is **not** an `OpenHandsUnavailableError` — it is
  yielded to the caller as a terminal `AgentEvent` and mapped to an
  `openhands.error` event by Task 08.0. Keep the two failure modes distinct
  (mirrors OpenClaude's stream-error-frame vs gRPC-status distinction).
- **`OpenHandsUnavailableError` ownership.** Forward-declared in
  `openhands/exceptions.py` by this task (skeleton above) and imported here; Task
  09.0 canonicalises it (and adds the rest of the hierarchy) while preserving
  this shape. Do not redefine it inline in `client.py`.
- **RAII / no retry here.** The client is used inside the process lifecycle
  context (subtask 02) or wrapped by the caller; `close()` is always called on
  teardown and never leaks a connection. Any retry/backoff is a tool /
  process-lifecycle policy decision (Tasks 08.0 / subtask 02) and uses
  `asyncio.sleep`, never `time.sleep` (C13).
- **Logging.** Log only connection lifecycle and status/error classifications at
  `DEBUG`; never log `task`, `content`, tool arguments, response text, or the
  server credential. `SensitiveFilter` is on every sink but is not a substitute
  for not logging payloads at all (C13).

## First-use setup: launching an OpenHands sidecar

`OpenHandsClient` is inert without a live sidecar to dial. Before debugging this
file against a real server (as opposed to the `from_session` mock seam used by
unit tests), start OpenHands yourself in external mode. **Docker must be
available on the host** (a new Docker-on-Windows operator prerequisite for this
backend — flagged for the root `README.md` in Task 13.0):

```bash
docker run -it --rm \
  -p 3000:3000 \
  -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest \
  -v /var/run/docker.sock:/var/run/docker.sock \
  docker.all-hands.dev/all-hands-ai/openhands:latest
```

Point the client at it and sanity-check reachability before trusting this
client's own code (this isolates "is OpenHands reachable" from "is my client code
correct"):

```bash
export OPENHANDS_SERVER_URL=http://localhost:3000
curl -fsS "$OPENHANDS_SERVER_URL/health" && echo "openhands server is reachable"
```

Leave the server running in a separate terminal for the rest of this subtask's
manual testing. A connection refusal almost always means the container's
published port does not match `OPENHANDS_SERVER_URL`; a runtime/sandbox error
means Docker is unavailable or the sandbox image failed to pull.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- **This file is the only place the OpenHands HTTP/WS client library may be imported** (C3); enforced by the isolation `grep` CI check and the Task 11.0 isolation test.
- `health_check()` returns `bool` and **never raises**; `run()` raises `OpenHandsUnavailableError` on transport failure; no raw library exception escapes this file (C3).
- Async throughout; no blocking transport calls on the event loop; no `time.sleep` (`asyncio.sleep` for any backoff — C13).
- Task text is sent only in the action message body, never in a URL/query/argv.
- All public classes/methods carry RST docstrings (`:param:`/`:return:`/`:raises:`).
- No raw task/response/credential text in any log sink or exception message.
- `ruff check src/ tests/` - clean.

## Success criteria

- [ ] `aegis_swr/openhands/client.py` defines `OpenHandsClient` and the typed `AgentEvent` / `EventKind` projection; no caller imports the client library or a raw library event object.
- [ ] The OpenHands HTTP/WS client library is imported in this file only (C3 check / isolation test passes).
- [ ] No session is created in `__init__`; the REST session and Socket.IO client are created on the first `run()` / `health_check()` call.
- [ ] `from_session(sio, http, settings)` yields a working client whose `run()` streams `AgentEvent`s from a mock session with no live process.
- [ ] `run(task, run_id)` is an async generator yielding one `AgentEvent` per `oh_event`, stopping after the first `FINISHED` / `ERROR` kind.
- [ ] `run()` sends the task in the `oh_user_action` body only — the task text never appears in a URL, query string, or argv (asserted in a unit test).
- [ ] `health_check()` returns `True` on a scripted healthy status within `connect_timeout_s`, and `False` (never raises) on timeout / unreachable / non-healthy status.
- [ ] `run()` raises `OpenHandsUnavailableError` on a scripted transport failure; a terminal `ERROR` *event* is yielded, not converted to the exception.
- [ ] `close()` is idempotent and safe when nothing was ever opened.
- [ ] `OpenHandsUnavailableError` is imported from `openhands/exceptions.py` (forward-declared), not redefined in `client.py`.
- [ ] No task/response/credential text appears in any log line.
- [ ] `ruff check src/ tests/` - clean.

