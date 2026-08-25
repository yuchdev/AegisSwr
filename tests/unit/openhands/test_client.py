"""Unit tests for :mod:`aegis_swr.openhands.client`.

Every test drives a scripted ``oh_event`` sequence through the
:meth:`OpenHandsClient.from_session` injection seam with fakes — no test imports
``socketio``, opens a socket, or contacts a live OpenHands sidecar. The fakes
mirror the researched V1-server shapes (``POST /api/conversations``, Socket.IO
``oh_event`` / ``oh_user_action``) recorded in the task spec.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import pytest
from loguru import logger

from aegis_swr.openhands.client import AgentEvent, EventKind, OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError

_SERVER_URL = "http://localhost:3000"
_RUN_ID = "run-openhands-1"


def _settings(*, server_url: Optional[str] = _SERVER_URL) -> OpenHandsSettings:
    """Build OpenHands settings without reading the environment."""
    return OpenHandsSettings(server_url=server_url)


class _FakeResponse:
    """Minimal stand-in for an ``httpx.Response`` (status + JSON body)."""

    def __init__(self, status_code: int, body: Any):
        """Store the scripted *status_code* and JSON *body*."""
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        """Return the scripted JSON body."""
        return self._body


class _FakeHttp:
    """Fake async REST session recording POST/GET calls and scripting responses.

    Models only the surface :class:`OpenHandsClient` uses: ``post`` (create
    conversation), ``get`` (health probe), and ``aclose``. Either verb can be
    scripted to raise a transport error instead of returning a response.
    """

    def __init__(
        self,
        *,
        post_response: Optional[_FakeResponse] = None,
        get_response: Optional[_FakeResponse] = None,
        post_raises: Optional[BaseException] = None,
        get_raises: Optional[BaseException] = None,
    ):
        """Configure the scripted responses / errors for each verb."""
        self._post_response = post_response
        self._get_response = get_response
        self._post_raises = post_raises
        self._get_raises = get_raises
        self.post_calls: list[tuple[str, Any]] = []
        self.get_calls: list[str] = []
        self.aclose_calls = 0

    async def post(self, url: str, json: Any = None, timeout: Any = None) -> _FakeResponse:
        """Record the POST, then raise or return the scripted response."""
        self.post_calls.append((url, json))
        if self._post_raises is not None:
            raise self._post_raises
        assert self._post_response is not None
        return self._post_response

    async def get(self, url: str, timeout: Any = None) -> _FakeResponse:
        """Record the GET, then raise or return the scripted response."""
        self.get_calls.append(url)
        if self._get_raises is not None:
            raise self._get_raises
        assert self._get_response is not None
        return self._get_response

    async def aclose(self):
        """Record a REST-session close."""
        self.aclose_calls += 1


class _FakeSio:
    """Fake async Socket.IO client delivering scripted ``oh_event`` payloads.

    Registers the client's ``oh_event`` handler via :meth:`on`, and on
    :meth:`emit` (the ``oh_user_action`` dispatch) feeds each scripted raw event
    to that handler in order — modelling the server streaming events back. Either
    :meth:`connect` or :meth:`emit` may be scripted to raise a transport error.
    """

    def __init__(
        self,
        events: Optional[list[dict[str, Any]]] = None,
        *,
        connect_raises: Optional[BaseException] = None,
    ):
        """Queue scripted *events* and configure an optional connect error."""
        self._events = list(events or [])
        self._connect_raises = connect_raises
        self._handler: Any = None
        self.connect_urls: list[str] = []
        self.emit_calls: list[tuple[str, Any]] = []
        self.disconnect_calls = 0

    def on(self, event: str, handler: Any):
        """Register the server→client *event* *handler* (``oh_event``)."""
        if event == "oh_event":
            self._handler = handler

    async def connect(self, url: str):
        """Record the stream URL, or raise the scripted connect error."""
        if self._connect_raises is not None:
            raise self._connect_raises
        self.connect_urls.append(url)

    async def emit(self, event: str, data: Any):
        """Record the emit and feed scripted events to the ``oh_event`` handler."""
        self.emit_calls.append((event, data))
        if self._handler is not None:
            for raw in self._events:
                await self._handler(raw)

    async def disconnect(self):
        """Record a Socket.IO disconnect."""
        self.disconnect_calls += 1


def _client(
    *,
    events: Optional[list[dict[str, Any]]] = None,
    post_response: Optional[_FakeResponse] = None,
    get_response: Optional[_FakeResponse] = None,
    post_raises: Optional[BaseException] = None,
    get_raises: Optional[BaseException] = None,
    connect_raises: Optional[BaseException] = None,
) -> tuple[OpenHandsClient, _FakeSio, _FakeHttp]:
    """Build a client over injected fakes with the given scripted behaviour."""
    if post_response is None and post_raises is None:
        post_response = _FakeResponse(201, {"conversation_id": "conv-1"})
    sio = _FakeSio(events, connect_raises=connect_raises)
    http = _FakeHttp(
        post_response=post_response,
        get_response=get_response,
        post_raises=post_raises,
        get_raises=get_raises,
    )
    client = OpenHandsClient.from_session(sio, http, _settings())
    return client, sio, http


async def _drain(client: OpenHandsClient, task: str = "navigate the repo") -> list[AgentEvent]:
    """Collect every :class:`AgentEvent` yielded by ``run`` for *task*."""
    return [event async for event in client.run(task, _RUN_ID)]


async def test_run_yields_projected_events_until_terminal():
    """[Unit] client: ``run`` yields typed events and stops after the terminal one.

    Scenario: a message, an action, and a terminal finished event are scripted;
    ``run`` is drained.

    Boundaries: only the injected fakes drive the stream; no socket is opened.

    On failure, first check: three ``AgentEvent`` values with the mapped kinds
    must be yielded and iteration must stop at ``FINISHED``.
    """
    events = [
        {"kind": "message", "content": "looking"},
        {"kind": "action", "tool": "read"},
        {"kind": "finished", "content": "done", "token_usage": 42},
    ]
    client, _, _ = _client(events=events)

    result = await _drain(client)

    assert [e.kind for e in result] == [EventKind.MESSAGE, EventKind.ACTION, EventKind.FINISHED]
    assert all(isinstance(e, AgentEvent) for e in result)
    assert result[1].tool == "read"
    assert result[2].content == "done"
    assert result[2].token_usage == 42


async def test_run_stops_after_first_terminal_event():
    """[Unit] client: ``run`` never yields past the first terminal event.

    Scenario: a finished event is followed by a trailing message event.

    Boundaries: the terminal-stop invariant is under test.

    On failure, first check: exactly one event (the terminal ``FINISHED``) must
    be yielded; the trailing event must be dropped.
    """
    events = [
        {"kind": "finished", "content": "answer"},
        {"kind": "message", "content": "should never surface"},
    ]
    client, _, _ = _client(events=events)

    result = await _drain(client)

    assert len(result) == 1
    assert result[0].kind == EventKind.FINISHED


async def test_run_sends_task_only_in_action_body_not_url_or_conversation():
    """[Unit] client: the task travels only in the ``oh_user_action`` body (C13).

    Scenario: a task with a unique marker is delegated; the create-conversation
    POST, the stream URL, and the emit body are inspected.

    Boundaries: enforces the "never argv/URL secrets" discipline.

    On failure, first check: the marker must appear only in the emit body — never
    in the POST JSON or the Socket.IO connect URL.
    """
    marker = "SECRET-TASK-MARKER-9f3"
    client, sio, http = _client(events=[{"kind": "finished", "content": "ok"}])

    await _drain(client, task=marker)

    # The task is NOT in the REST create-conversation call.
    post_url, post_json = http.post_calls[0]
    assert "/api/conversations" in post_url
    assert marker not in post_url
    assert marker not in str(post_json)
    # The task is NOT in the Socket.IO connect URL (only conversation_id is).
    assert sio.connect_urls
    assert all(marker not in url for url in sio.connect_urls)
    assert all("conversation_id=conv-1" in url for url in sio.connect_urls)
    # The task IS in the oh_user_action body only.
    event_name, body = sio.emit_calls[0]
    assert event_name == "oh_user_action"
    assert body["task"] == marker


async def test_run_terminal_error_event_is_yielded_not_raised():
    """[Unit] client: a terminal ERROR event is yielded, not turned into an error.

    Scenario: the stream opens fine but OpenHands reports a logical error event.

    Boundaries: distinguishes a logical error event from a transport failure.

    On failure, first check: a single ``AgentEvent`` of kind ``ERROR`` must be
    yielded and no ``OpenHandsUnavailableError`` raised.
    """
    client, _, _ = _client(events=[{"kind": "error", "content": "tool blew up"}])

    result = await _drain(client)

    assert len(result) == 1
    assert result[0].kind == EventKind.ERROR


async def test_run_unmappable_kind_becomes_terminal_error_event():
    """[Unit] client: an unmappable event kind surfaces as a terminal ERROR event.

    Scenario: the stream sends an event whose ``kind`` is not in the taxonomy.

    Boundaries: mirrors OpenClaude's unspecified-frame protocol-violation rule.

    On failure, first check: the unmappable event must map to a terminal
    ``EventKind.ERROR`` (never silently dropped) and stop iteration.
    """
    client, _, _ = _client(events=[{"kind": "totally-unknown", "content": "x"}])

    result = await _drain(client)

    assert len(result) == 1
    assert result[0].kind == EventKind.ERROR


async def test_run_terminal_without_usage_leaves_token_usage_none():
    """[Unit] client: a terminal event without usage leaves ``token_usage`` None.

    Scenario: a finished event carries no ``token_usage`` field.

    Boundaries: the C9 boundary-estimate fallback contract is under test.

    On failure, first check: ``token_usage`` must be ``None`` so the tool falls
    back to its own estimate.
    """
    client, _, _ = _client(events=[{"kind": "finished", "content": "answer"}])

    result = await _drain(client)

    assert result[0].token_usage is None


async def test_run_raises_unavailable_on_transport_failure():
    """[Unit] client: a transport failure raises retriable ``OpenHandsUnavailableError``.

    Scenario: the REST create-conversation POST raises ``ConnectionError``.

    Boundaries: the transport-error-to-domain-exception translation is under test.

    On failure, first check: ``run`` must raise ``OpenHandsUnavailableError`` with
    ``retriable=True`` and no raw ``ConnectionError`` escaping.
    """
    client, _, _ = _client(post_raises=ConnectionError("refused"))

    with pytest.raises(OpenHandsUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.retriable is True


async def test_run_raises_unavailable_on_socketio_connect_failure():
    """[Unit] client: a Socket.IO connect failure raises ``OpenHandsUnavailableError``.

    Scenario: the REST call succeeds but the Socket.IO connect raises
    ``ConnectionError``.

    Boundaries: proves the WS transport failure is translated too.

    On failure, first check: ``run`` must raise ``OpenHandsUnavailableError``
    rather than leak the raw error.
    """
    client, _, _ = _client(connect_raises=ConnectionError("ws refused"))

    with pytest.raises(OpenHandsUnavailableError):
        await _drain(client)


async def test_run_non_2xx_create_conversation_raises_with_status_code():
    """[Unit] client: a non-2xx create-conversation surfaces the status code.

    Scenario: ``POST /api/conversations`` returns HTTP 503.

    Boundaries: this is a distinct failure from a dropped connection.

    On failure, first check: ``run`` must raise ``OpenHandsUnavailableError``
    carrying ``status_code="503"``.
    """
    client, _, _ = _client(post_response=_FakeResponse(503, {}))

    with pytest.raises(OpenHandsUnavailableError) as excinfo:
        await _drain(client)

    assert excinfo.value.status_code == "503"


async def test_run_missing_conversation_id_raises_unavailable():
    """[Unit] client: a create-conversation response with no id raises unavailable.

    Scenario: the POST returns 201 but the body omits ``conversation_id``.

    Boundaries: the malformed-response guard is under test.

    On failure, first check: ``run`` must raise ``OpenHandsUnavailableError``.
    """
    client, _, _ = _client(post_response=_FakeResponse(201, {"unexpected": True}))

    with pytest.raises(OpenHandsUnavailableError):
        await _drain(client)


async def test_health_check_true_on_healthy_status():
    """[Unit] client: ``health_check`` returns True on a 2xx status.

    Scenario: the ``/health`` GET returns HTTP 200.

    Boundaries: only the REST probe drives the verdict.

    On failure, first check: ``health_check`` must return ``True`` and probe the
    ``/health`` endpoint.
    """
    client, _, http = _client(get_response=_FakeResponse(200, {"status": "ok"}))

    assert await client.health_check() is True
    assert any("/health" in url for url in http.get_calls)


async def test_health_check_false_on_non_healthy_status():
    """[Unit] client: ``health_check`` returns False on a non-2xx status.

    Scenario: the ``/health`` GET returns HTTP 503.

    Boundaries: a reachable-but-unhealthy server must read as unavailable.

    On failure, first check: ``health_check`` must return ``False`` without
    raising.
    """
    client, _, _ = _client(get_response=_FakeResponse(503, {}))

    assert await client.health_check() is False


async def test_health_check_false_never_raises_on_transport_failure():
    """[Unit] client: ``health_check`` returns False (never raises) on transport error.

    Scenario: the ``/health`` GET raises ``ConnectionError``.

    Boundaries: enforces the never-raise readiness-predicate contract.

    On failure, first check: ``health_check`` must swallow the error and return
    ``False``.
    """
    client, _, _ = _client(get_raises=ConnectionError("refused"))

    assert await client.health_check() is False


async def test_health_check_false_on_timeout():
    """[Unit] client: ``health_check`` returns False on a probe timeout.

    Scenario: the ``/health`` GET raises ``asyncio.TimeoutError``.

    Boundaries: exercises the explicit ``TimeoutError`` branch of the never-raise
    guard.

    On failure, first check: ``health_check`` must return ``False`` on timeout.
    """
    client, _, _ = _client(get_raises=asyncio.TimeoutError())

    assert await client.health_check() is False


async def test_close_disconnects_and_is_idempotent():
    """[Unit] client: ``close`` tears down both sessions and is idempotent.

    Scenario: a from-session client is closed twice.

    Boundaries: the RAII teardown contract is under test.

    On failure, first check: the first close must disconnect the socket and close
    the REST session; the second must be a safe no-op.
    """
    client, sio, http = _client(events=[{"kind": "finished", "content": "ok"}])

    await client.close()
    assert sio.disconnect_calls == 1
    assert http.aclose_calls == 1

    # Second close is a no-op (sessions already released).
    await client.close()
    assert sio.disconnect_calls == 1
    assert http.aclose_calls == 1


async def test_close_safe_when_nothing_opened():
    """[Unit] client: ``close`` is safe when no session was ever opened.

    Scenario: a client is built via ``__init__`` (no injected sessions) and
    closed without any ``run``/``health_check``.

    Boundaries: the never-opened branch of ``close`` is under test.

    On failure, first check: ``close`` must not raise when both sessions are
    ``None``.
    """
    client = OpenHandsClient(_settings())

    await client.close()  # must not raise


async def test_no_task_or_response_text_in_logs():
    """[Unit] client: neither task nor response text reaches any log sink (C13).

    Scenario: a task and terminal content both carry unique markers; a DEBUG sink
    captures every log line emitted during ``run``.

    Boundaries: enforces the no-payload-in-logs constraint.

    On failure, first check: neither the task marker nor the content marker may
    appear in any captured log record.
    """
    task_marker = "TASK-MARKER-a1"
    content_marker = "CONTENT-MARKER-b2"
    client, _, _ = _client(events=[{"kind": "finished", "content": content_marker}])

    captured: list[str] = []
    sink_id = logger.add(captured.append, level="DEBUG")
    try:
        await _drain(client, task=task_marker)
    finally:
        logger.remove(sink_id)

    joined = "".join(captured)
    assert task_marker not in joined
    assert content_marker not in joined
