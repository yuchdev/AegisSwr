"""Unit tests for :class:`aegis_swr.openhands.tool.OpenHandsTool`.

Every test drives a scripted ``oh_event`` sequence through the
:meth:`aegis_swr.openhands.client.OpenHandsClient.from_session` injection seam
with fakes — no test opens a socket, starts Docker, or imports the OpenHands
client library. Events are asserted through a recording :class:`EventBus`
subscribed at :class:`~aegis_swr.core.events.DomainEvent` so every
``openhands.*`` emission is captured.

The suite exercises every branch of :meth:`OpenHandsTool.delegate` (the
100%-branch bar the sibling ``OpenClaudeTool`` / ``ClaudeCodeTool`` suites hold):
the budget pre-check, the dry-run short-circuit and its precedence, the C9
token-source matrix (server-reported usage vs boundary estimate), truncation,
every typed failure arm (permission denied, ``ERROR`` event, retriable /
non-retriable transport, outer timeout, defensive ``internal_error``),
``CancelledError`` propagation, and the C13 no-payload-in-logs-or-events
guarantee.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import uuid4

import pytest
from loguru import logger

from aegis_swr.code_intel.backend import CodeIntelBackend, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openhands import tool as tool_module
from aegis_swr.openhands.client import AgentEvent, EventKind, OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsCompleted,
    OpenHandsError,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
)
from aegis_swr.openhands.exceptions import OpenHandsUnavailableError
from aegis_swr.openhands.tool import OpenHandsTool

_SERVER_URL = "http://localhost:3000"


def _settings(*, server_url: Optional[str] = _SERVER_URL, **overrides: Any) -> OpenHandsSettings:
    """Build OpenHands settings without reading the environment."""
    return OpenHandsSettings(server_url=server_url, **overrides)


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
    """Fake async REST session recording POST/close calls and scripting responses.

    Models only the surface :class:`OpenHandsClient` uses under ``run`` /
    ``close``: ``post`` (create conversation) and ``aclose``. ``post`` may be
    scripted to raise instead of returning a response, letting a test drive the
    client's ``run`` into a chosen failure without a socket.
    """

    def __init__(
        self,
        *,
        post_response: Optional[_FakeResponse] = None,
        post_raises: Optional[BaseException] = None,
    ):
        """Configure the scripted create-conversation response or error."""
        self._post_response = post_response
        self._post_raises = post_raises
        self.post_calls: list[tuple[str, Any]] = []
        self.aclose_calls = 0

    async def post(self, url: str, json: Any = None, timeout: Any = None) -> _FakeResponse:
        """Record the POST, then raise or return the scripted response."""
        self.post_calls.append((url, json))
        if self._post_raises is not None:
            raise self._post_raises
        assert self._post_response is not None
        return self._post_response

    async def aclose(self):
        """Record a REST-session close."""
        self.aclose_calls += 1


class _FakeSio:
    """Fake async Socket.IO client delivering scripted ``oh_event`` payloads.

    Registers the client's ``oh_event`` handler via :meth:`on`, and on
    :meth:`emit` (the ``oh_user_action`` dispatch) feeds each scripted raw event
    to that handler in order — modelling the server streaming events back.
    """

    def __init__(self, events: Optional[list[dict[str, Any]]] = None):
        """Queue scripted *events* for replay on the first emit."""
        self._events = list(events or [])
        self._handler: Any = None
        self.connect_urls: list[str] = []
        self.emit_calls: list[tuple[str, Any]] = []
        self.disconnect_calls = 0

    def on(self, event: str, handler: Any):
        """Register the server→client *event* *handler* (``oh_event``)."""
        if event == "oh_event":
            self._handler = handler

    async def connect(self, url: str):
        """Record the stream URL."""
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


class _Harness:
    """A tool wired over injected fakes plus a recording EventBus."""

    def __init__(
        self,
        tool: OpenHandsTool,
        sio: _FakeSio,
        http: _FakeHttp,
        budget: CallBudget,
        records: list[DomainEvent],
    ):
        """Bundle the collaborators a test asserts against."""
        self.tool = tool
        self.sio = sio
        self.http = http
        self.budget = budget
        self.records = records

    def events_of(self, cls: type[DomainEvent]) -> list[DomainEvent]:
        """Return every recorded event that is an instance of *cls*."""
        return [event for event in self.records if isinstance(event, cls)]


def _make(
    *,
    events: Optional[list[dict[str, Any]]] = None,
    post_response: Optional[_FakeResponse] = None,
    post_raises: Optional[BaseException] = None,
    settings: Optional[OpenHandsSettings] = None,
    budget: Optional[CallBudget] = None,
) -> _Harness:
    """Build an :class:`OpenHandsTool` over injected fakes with a recording bus."""
    resolved_settings = settings if settings is not None else _settings()
    if post_response is None and post_raises is None:
        post_response = _FakeResponse(201, {"conversation_id": "conv-1"})
    sio = _FakeSio(events)
    http = _FakeHttp(post_response=post_response, post_raises=post_raises)
    client = OpenHandsClient.from_session(sio, http, resolved_settings)
    resolved_budget = budget if budget is not None else CallBudget(max_tokens=100_000)
    records: list[DomainEvent] = []
    bus = EventBus()
    bus.subscribe(DomainEvent, records.append)
    tool = OpenHandsTool(client, resolved_settings, bus, resolved_budget)
    return _Harness(tool, sio, http, resolved_budget, records)


def _ctx(*, dry_run: bool = False) -> CodeTaskContext:
    """Build a per-call context with a fresh run id."""
    return CodeTaskContext(run_id=uuid4(), dry_run=dry_run)


def _capture_debug_logs() -> tuple[list[str], int]:
    """Attach a loguru DEBUG sink capturing rendered messages; return (records, id)."""
    records: list[str] = []
    sink_id = logger.add(records.append, level="DEBUG", format="{message}")
    return records, sink_id


# --- construction / protocol conformance ------------------------------------


def test_is_code_intel_backend_and_metadata():
    """[Unit] tool: OpenHandsTool is a CodeIntelBackend advertising the sandbox.

    Scenario: a tool is constructed over injected fakes.

    Boundaries: construction must open no connection and touch no budget.

    On failure, first check: the instance must be a ``CodeIntelBackend``, expose
    ``name == "openhands"`` and a Docker-sandbox description, and issue zero
    client calls at construction time.
    """
    harness = _make()
    assert isinstance(harness.tool, CodeIntelBackend)
    assert OpenHandsTool.name == "openhands"
    assert "Docker sandbox" in harness.tool.description
    assert harness.http.post_calls == []
    assert harness.sio.emit_calls == []
    assert harness.budget.spent == 0


# --- gates: budget pre-check and dry-run ------------------------------------


async def test_insufficient_budget_returns_non_retriable_and_no_stream_call():
    """[Unit] tool: an insufficient budget fails non-retriably with zero stream calls.

    Scenario: the budget cannot afford ``max_response_tokens // 4`` and delegate
    is invoked with a finished event scripted (which must never be reached).

    Boundaries: the pre-check must run before any connection is opened.

    On failure, first check: the result must be a non-retriable
    ``insufficient_budget`` failure, ``client.run`` must never be called (no POST,
    no emit, no close), and the budget must stay unspent.
    """
    harness = _make(
        events=[{"kind": "finished", "content": "unreached"}],
        budget=CallBudget(max_tokens=10),
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["ok"] is False
    assert result.metadata["error"] == "insufficient_budget"
    assert result.metadata["retriable"] is False
    assert result.token_estimate == 0
    assert harness.http.post_calls == []
    assert harness.sio.emit_calls == []
    assert harness.http.aclose_calls == 0
    assert harness.budget.spent == 0
    assert harness.records == []


async def test_dry_run_short_circuits_with_zero_stream_calls():
    """[Unit] tool: ctx.dry_run returns [dry-run]/0 tokens and never calls the client.

    Scenario: an ample budget with ``dry_run=True`` and a finished event scripted.

    Boundaries: the dry-run must suppress every REST/WS call, asserted via the
    fake call counters (not merely the content string).

    On failure, first check: the result must be ``content == "[dry-run]"`` with
    ``token_estimate == 0``, and every client call counter must be zero.
    """
    harness = _make(events=[{"kind": "finished", "content": "unreached"}])

    result = await harness.tool.delegate("task", _ctx(dry_run=True))

    assert result.content == "[dry-run]"
    assert result.token_estimate == 0
    assert result.metadata["ok"] is True
    assert harness.http.post_calls == []
    assert harness.sio.emit_calls == []
    assert harness.http.aclose_calls == 0
    assert harness.sio.disconnect_calls == 0
    assert harness.budget.spent == 0
    assert harness.records == []


async def test_precheck_precedes_dry_run():
    """[Unit] tool: the budget pre-check runs before the dry-run branch.

    Scenario: an over-budget account combined with ``dry_run=True``.

    Boundaries: pre-check precedence is load-bearing (an over-budget dry-run must
    still surface the budget failure).

    On failure, first check: the result must be the non-retriable
    ``insufficient_budget`` failure, not the ``[dry-run]`` success.
    """
    harness = _make(budget=CallBudget(max_tokens=10))

    result = await harness.tool.delegate("task", _ctx(dry_run=True))

    assert result.metadata["error"] == "insufficient_budget"
    assert result.content == ""


# --- C9 token-source matrix -------------------------------------------------


async def test_finish_with_server_usage_charges_real_usage():
    """[Unit] tool: a FINISHED event with server usage sets token_estimate to it.

    Scenario: a message and a finished event carrying ``token_usage=100`` are
    scripted.

    Boundaries: C9 dual-source — server-reported usage is preferred when present.

    On failure, first check: ``token_estimate`` must equal 100, the budget must be
    charged exactly 100 after the stream, and exactly one ``OpenHandsCompleted``
    with ``usage_reported=True`` must be emitted; the client must be closed.
    """
    harness = _make(
        events=[
            {"kind": "message", "content": "hi "},
            {"kind": "finished", "content": "answer", "token_usage": 100},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["ok"] is True
    assert result.content == "hi answer"
    assert result.token_estimate == 100
    assert harness.budget.spent == 100
    completed = harness.events_of(OpenHandsCompleted)
    assert len(completed) == 1
    assert completed[0].usage_reported is True
    assert completed[0].token_estimate == 100
    assert completed[0].truncated is False
    assert harness.http.aclose_calls == 1
    assert harness.sio.disconnect_calls == 1


async def test_finish_without_server_usage_uses_boundary_estimate():
    """[Unit] tool: a FINISHED event without usage falls back to the boundary estimate.

    Scenario: a message ``"aaaaaaaa"`` (8 chars) with a finished event carrying no
    ``token_usage`` and empty content (the falsy-content branch).

    Boundaries: C9 fallback — ``max(1, len(content) // 4)`` on the truncated text.

    On failure, first check: ``token_estimate`` must equal ``8 // 4 == 2``, the
    budget must be charged 2, and ``OpenHandsCompleted.usage_reported`` must be
    ``False``.
    """
    harness = _make(
        events=[
            {"kind": "message", "content": "aaaaaaaa"},
            {"kind": "finished", "content": ""},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.content == "aaaaaaaa"
    assert result.token_estimate == 2
    assert harness.budget.spent == 2
    completed = harness.events_of(OpenHandsCompleted)
    assert len(completed) == 1
    assert completed[0].usage_reported is False
    assert completed[0].token_estimate == 2


async def test_boundary_estimate_never_below_one():
    """[Unit] tool: an empty answer with no usage still charges the ``max(1, …)`` floor.

    Scenario: a lone finished event with empty content and no ``token_usage``.

    Boundaries: the ``max(1, len(content) // 4)`` floor for a zero-length answer.

    On failure, first check: ``token_estimate`` must be ``1`` and the budget must
    be charged exactly 1.
    """
    harness = _make(events=[{"kind": "finished", "content": ""}])

    result = await harness.tool.delegate("task", _ctx())

    assert result.content == ""
    assert result.token_estimate == 1
    assert harness.budget.spent == 1


# --- truncation -------------------------------------------------------------


async def test_truncation_flags_result_and_completed_event():
    """[Unit] tool: content beyond the cap is truncated and flagged on both surfaces.

    Scenario: ``max_response_tokens=256`` (clamp 1024 chars) with a finished
    answer of 1100 characters and no server usage.

    Boundaries: truncation clamps to ``max_response_tokens * 4`` and the boundary
    estimate is computed on the *truncated* text.

    On failure, first check: the result must be truncated to 1024 chars with
    ``truncated=True``, ``token_estimate == 256``, and the emitted
    ``OpenHandsCompleted`` must also carry ``truncated=True``.
    """
    harness = _make(
        events=[{"kind": "finished", "content": "a" * 1100}],
        settings=_settings(max_response_tokens=256),
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.truncated is True
    assert len(result.content) == 1024
    assert result.token_estimate == 256
    assert harness.budget.spent == 256
    completed = harness.events_of(OpenHandsCompleted)
    assert completed[0].truncated is True


# --- action / observation emission and arg counting -------------------------


async def test_action_and_observation_events_emitted_with_counts():
    """[Unit] tool: ACTION/OBSERVATION frames emit audit events carrying counts only.

    Scenario: one action (JSON-object summary), one observation (10-char summary),
    and a finished event are scripted.

    Boundaries: C10 — audit events carry the type name, an argument count, and an
    output size; never the raw payload.

    On failure, first check: exactly one ``OpenHandsAction(action="read",
    arg_count=1)`` and one ``OpenHandsObservation(observation="read", ok=True,
    content_size=10)`` must be emitted, and the success metadata must record the
    per-kind counts.
    """
    harness = _make(
        events=[
            {"kind": "action", "tool": "read", "content": '{"path": "x"}'},
            {"kind": "observation", "tool": "read", "content": "0123456789"},
            {"kind": "finished", "content": "done", "token_usage": 5},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    actions = harness.events_of(OpenHandsAction)
    observations = harness.events_of(OpenHandsObservation)
    assert len(actions) == 1
    assert actions[0].action == "read"
    assert actions[0].arg_count == 1
    assert len(observations) == 1
    assert observations[0].observation == "read"
    assert observations[0].ok is True
    assert observations[0].content_size == 10
    assert result.metadata["action_count"] == 1
    assert result.metadata["observation_count"] == 1
    assert result.metadata["event_count"] == 3


async def test_arg_count_zero_for_non_json_and_scalar_json():
    """[Unit] tool: a non-JSON and a scalar-JSON action summary both count zero args.

    Scenario: two action events — a plain non-JSON summary and a JSON scalar —
    followed by a finished event.

    Boundaries: exercises both the parse-failure and the non-container branches of
    ``_arg_count`` so no payload is ever inspected beyond a top-level count.

    On failure, first check: both emitted ``OpenHandsAction`` events must report
    ``arg_count == 0``.
    """
    harness = _make(
        events=[
            {"kind": "action", "tool": "grep", "content": "a plain summary"},
            {"kind": "action", "tool": "glob", "content": "5"},
            {"kind": "finished", "content": "", "token_usage": 1},
        ]
    )

    await harness.tool.delegate("task", _ctx())

    actions = harness.events_of(OpenHandsAction)
    assert [a.arg_count for a in actions] == [0, 0]


# --- permission gate --------------------------------------------------------


async def test_permission_allowlisted_action_continues():
    """[Unit] tool: a PERMISSION request for an allowlisted tool is auto-approved.

    Scenario: a permission event for ``read`` (in the default allowlist) followed
    by a finished event.

    Boundaries: the defense-in-depth gate allows allowlisted tools and lets the
    stream complete normally.

    On failure, first check: the delegation must succeed, publish no
    ``OpenHandsPermissionDenied``, and charge the budget.
    """
    harness = _make(
        events=[
            {"kind": "permission", "tool": "read"},
            {"kind": "finished", "content": "ok", "token_usage": 7},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["ok"] is True
    assert harness.events_of(OpenHandsPermissionDenied) == []
    assert harness.budget.spent == 7


async def test_permission_denied_non_retriable_charges_zero():
    """[Unit] tool: a PERMISSION request for a non-allowlisted tool denies non-retriably.

    Scenario: a permission event for ``run`` (not in the default read-only
    allowlist) followed by a finished event (which must never be reached).

    Boundaries: C8 defense-in-depth — a non-allowlisted action halts read-only.

    On failure, first check: the result must be a non-retriable
    ``permission_denied`` failure charging zero tokens, exactly one
    ``OpenHandsPermissionDenied(action="run", denied_binary="run")`` must be
    emitted, no ``OpenHandsCompleted`` must fire, and the client must be closed.
    """
    harness = _make(
        events=[
            {"kind": "permission", "tool": "run"},
            {"kind": "finished", "content": "unreached", "token_usage": 99},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "permission_denied"
    assert result.metadata["retriable"] is False
    assert result.token_estimate == 0
    assert harness.budget.spent == 0
    denied = harness.events_of(OpenHandsPermissionDenied)
    assert len(denied) == 1
    assert denied[0].action == "run"
    assert denied[0].denied_binary == "run"
    assert harness.events_of(OpenHandsCompleted) == []
    assert harness.http.aclose_calls == 1


# --- ERROR event ------------------------------------------------------------


async def test_error_event_returns_non_retriable_and_emits_stream_error():
    """[Unit] tool: a terminal ERROR event fails non-retriably with zero tokens.

    Scenario: a message then a terminal error event.

    Boundaries: an ``ERROR`` event surfaces ``OpenHandsError`` carrying only a
    classification, code, and the live event count — never the raw error text.

    On failure, first check: the result must be a non-retriable ``stream_error``
    failure, one ``OpenHandsError(error_type="stream_error", code="error_event",
    event_count=2)`` must be emitted, and the budget must stay unspent.
    """
    harness = _make(
        events=[
            {"kind": "message", "content": "looking"},
            {"kind": "error", "content": "boom internal detail"},
        ]
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "stream_error"
    assert result.metadata["retriable"] is False
    assert harness.budget.spent == 0
    errors = harness.events_of(OpenHandsError)
    assert len(errors) == 1
    assert errors[0].error_type == "stream_error"
    assert errors[0].code == "error_event"
    assert errors[0].event_count == 2
    assert harness.events_of(OpenHandsCompleted) == []


# --- transport failures -----------------------------------------------------


async def test_transport_unavailable_retriable():
    """[Unit] tool: a retriable OpenHandsUnavailableError yields a retriable failure.

    Scenario: the create-conversation POST raises
    ``OpenHandsUnavailableError(retriable=True, status_code="503")``.

    Boundaries: retriability is read from the exception attribute, never a
    transport status enum (C3).

    On failure, first check: the result must be a retriable ``transport_error``
    failure charging zero tokens, and one ``OpenHandsError(error_type="transport",
    code="503")`` must be emitted; the client must be closed.
    """
    harness = _make(
        post_raises=OpenHandsUnavailableError("boom", retriable=True, status_code="503"),
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "transport_error"
    assert result.metadata["retriable"] is True
    assert harness.budget.spent == 0
    errors = harness.events_of(OpenHandsError)
    assert len(errors) == 1
    assert errors[0].error_type == "transport"
    assert errors[0].code == "503"
    assert harness.http.aclose_calls == 1


async def test_transport_unavailable_non_retriable():
    """[Unit] tool: a non-retriable OpenHandsUnavailableError yields a non-retriable failure.

    Scenario: the POST raises ``OpenHandsUnavailableError(retriable=False,
    status_code="500")``.

    Boundaries: the tool mirrors the exception's ``retriable`` flag onto the
    failure result.

    On failure, first check: the result must be a non-retriable ``transport_error``
    failure and the emitted ``OpenHandsError`` code must be ``"500"``.
    """
    harness = _make(
        post_raises=OpenHandsUnavailableError("nope", retriable=False, status_code="500"),
    )

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "transport_error"
    assert result.metadata["retriable"] is False
    assert harness.events_of(OpenHandsError)[0].code == "500"


async def test_transport_unavailable_without_status_uses_fallback_code():
    """[Unit] tool: a status-less transport error emits the UNAVAILABLE fallback code.

    Scenario: the POST raises ``OpenHandsUnavailableError(retriable=True)`` with no
    ``status_code``.

    Boundaries: exercises the ``exc.status_code or "UNAVAILABLE"`` fallback arm.

    On failure, first check: the emitted ``OpenHandsError.code`` must be
    ``"UNAVAILABLE"``.
    """
    harness = _make(post_raises=OpenHandsUnavailableError("boom", retriable=True))

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "transport_error"
    assert harness.events_of(OpenHandsError)[0].code == "UNAVAILABLE"


# --- outer timeout ----------------------------------------------------------


async def test_outer_timeout_returns_retriable(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: the outer asyncio.wait_for deadline yields a retriable timeout.

    Scenario: ``asyncio.wait_for`` (as referenced by the tool module) is patched
    to close the pending coroutine and raise ``asyncio.TimeoutError``, modelling
    the whole stream exceeding ``request_timeout_s``.

    Boundaries: still drives the from_session client; only the deadline is forced.

    On failure, first check: the result must be a retriable ``timeout`` failure
    charging zero tokens, one ``OpenHandsError(error_type="timeout",
    code="DEADLINE_EXCEEDED")`` must be emitted, and the client must be closed.
    """

    async def _fake_wait_for(coro: Any, timeout: Any) -> Any:
        """Discard the pending coroutine and raise a deadline error."""
        coro.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(tool_module.asyncio, "wait_for", _fake_wait_for)
    harness = _make(events=[{"kind": "finished", "content": "unreached"}])

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "timeout"
    assert result.metadata["retriable"] is True
    assert harness.budget.spent == 0
    errors = harness.events_of(OpenHandsError)
    assert len(errors) == 1
    assert errors[0].error_type == "timeout"
    assert errors[0].code == "DEADLINE_EXCEEDED"
    assert harness.http.aclose_calls == 1


# --- defensive internal-error arm and cancellation --------------------------


async def test_unexpected_exception_maps_to_internal_error():
    """[Unit] tool: an unexpected exception is trapped as a non-retriable internal_error.

    Scenario: the create-conversation POST raises a bare ``RuntimeError`` — not a
    typed transport/permission error — from inside ``client.run``.

    Boundaries: the defensive final ``except Exception`` arm guarantees no
    exception escapes ``delegate`` (C13).

    On failure, first check: the result must be a non-retriable ``internal_error``
    failure charging zero tokens, one ``OpenHandsError(error_type="internal_error",
    code="internal_error")`` must be emitted, and the client must be closed.
    """
    harness = _make(post_raises=RuntimeError("unexpected"))

    result = await harness.tool.delegate("task", _ctx())

    assert result.metadata["error"] == "internal_error"
    assert result.metadata["retriable"] is False
    assert harness.budget.spent == 0
    errors = harness.events_of(OpenHandsError)
    assert len(errors) == 1
    assert errors[0].error_type == "internal_error"
    assert errors[0].code == "internal_error"
    assert harness.http.aclose_calls == 1


async def test_cancelled_error_propagates(monkeypatch: pytest.MonkeyPatch):
    """[Unit] tool: asyncio.CancelledError propagates and is never swallowed.

    Scenario: ``asyncio.wait_for`` is patched to raise ``asyncio.CancelledError``
    (a ``BaseException``).

    Boundaries: cooperative cancellation must not be trapped by the defensive
    ``except Exception`` arm; the client is still closed on the way out (RAII).

    On failure, first check: ``delegate`` must re-raise ``CancelledError`` and the
    client must have been closed.
    """

    async def _fake_wait_for(coro: Any, timeout: Any) -> Any:
        """Discard the pending coroutine and raise cancellation."""
        coro.close()
        raise asyncio.CancelledError

    monkeypatch.setattr(tool_module.asyncio, "wait_for", _fake_wait_for)
    harness = _make(events=[{"kind": "finished", "content": "x"}])

    with pytest.raises(asyncio.CancelledError):
        await harness.tool.delegate("task", _ctx())

    assert harness.http.aclose_calls == 1


# --- C13: no payload in logs or events --------------------------------------


async def test_no_payload_text_in_logs_or_events():
    """[Unit] tool: no task/observation/server_url text reaches a log sink or event.

    Scenario: a full stream carrying a recognisable ``SEKRET`` marker in the task,
    every event's content, and the server_url host is delegated while a DEBUG log
    sink is attached.

    Boundaries: C13 — emissions and logs carry names, sizes, and counts only.

    On failure, first check: the marker must appear in no captured log record and
    in the string form of no published event (the answer content on the result is
    permitted; the events are not).
    """
    marker = "SEKRET-PAYLOAD-9f3a"
    host_marker = "sekret-host-42"
    settings = _settings(server_url=f"http://{host_marker}:3000")
    events = [
        {"kind": "message", "content": marker},
        {"kind": "action", "tool": "read", "content": f'{{"q": "{marker}"}}'},
        {"kind": "observation", "tool": "read", "content": marker},
        {"kind": "finished", "content": marker, "token_usage": 3},
    ]
    harness = _make(events=events, settings=settings)
    records, sink_id = _capture_debug_logs()
    try:
        result = await harness.tool.delegate(f"investigate {marker}", _ctx())
    finally:
        logger.remove(sink_id)

    assert result.metadata["ok"] is True
    joined_logs = "\n".join(records)
    assert marker not in joined_logs
    assert host_marker not in joined_logs
    for event in harness.records:
        rendered = str(event)
        assert marker not in rendered
        assert host_marker not in rendered


# --- defensive: a stream that ends without a terminal event -----------------


class _ExhaustingClient:
    """A minimal fake client whose stream ends WITHOUT a terminal event.

    The real :class:`OpenHandsClient` always yields a terminal ``FINISHED`` /
    ``ERROR`` event before its ``run`` generator ends (or raises on a per-event
    timeout), so the :meth:`OpenHandsClient.from_session` seam **cannot** produce
    a naturally-exhausted stream. This fake — which opens no socket and imports no
    library, honouring the same no-transport discipline as the seam — drives the
    tool's defensive fall-through to :meth:`OpenHandsTool._on_finish` when the
    stream ends unterminated, the one branch the seam leaves unreachable.

    :ivar close_calls: Number of times :meth:`close` was awaited (RAII check).
    """

    def __init__(self, events: list[AgentEvent]):
        """Queue *events* to replay, then end the generator normally."""
        self._events = events
        self.close_calls = 0

    async def run(self, task: str, run_id: str):
        """Yield each queued :class:`AgentEvent`, then exhaust without a terminal."""
        for event in self._events:
            yield event

    async def close(self):
        """Record an idempotent close."""
        self.close_calls += 1


async def test_unterminated_stream_falls_through_to_on_finish():
    """[Unit] tool: a stream ending without a terminal event still finalises cleanly.

    Scenario: a fake client yields one ``MESSAGE`` event and then exhausts its
    generator with no ``FINISHED`` / ``ERROR`` event (a shape the real client's
    contract forbids, so it is driven through a bare fake rather than the
    from_session seam).

    Boundaries: exercises the defensive natural-exhaustion fall-through of
    ``_consume_stream``; the boundary token estimate is used because no server
    usage was reported.

    On failure, first check: the delegation must succeed with the accumulated
    text, charge the boundary estimate, emit one ``OpenHandsCompleted``, and close
    the client.
    """
    client = _ExhaustingClient([AgentEvent(kind=EventKind.MESSAGE, content="hi", tool=None, token_usage=None)])
    budget = CallBudget(max_tokens=100_000)
    records: list[DomainEvent] = []
    bus = EventBus()
    bus.subscribe(DomainEvent, records.append)
    tool = OpenHandsTool(client, _settings(), bus, budget)

    result = await tool.delegate("task", _ctx())

    assert result.metadata["ok"] is True
    assert result.content == "hi"
    assert result.token_estimate == 1  # max(1, len("hi") // 4)
    assert budget.spent == 1
    completed = [event for event in records if isinstance(event, OpenHandsCompleted)]
    assert len(completed) == 1
    assert completed[0].usage_reported is False
    assert client.close_calls == 1
