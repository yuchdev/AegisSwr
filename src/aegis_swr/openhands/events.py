"""OpenHands lifecycle and Action/Observation stream events (contract C10).

The seven ``openhands.*`` events observe the OpenHands sidecar connection
lifecycle and the Docker-sandboxed Action/Observation event stream. Each
subclasses the live :class:`aegis_swr.core.events.DomainEvent` so the shipping
:class:`~aegis_swr.core.events.EventBus` (which dispatches by walking
``type(event).__mro__`` over ``DomainEvent`` subclasses) delivers them; a plain
dataclass carrying only an ``event_type`` string would be dropped to zero
subscribers. Consumers still filter on the ``event_type`` ``ClassVar`` sentinel.

No field carries incident payload, action arguments, sandbox command lines, or
unredacted observation text (C13): only ids, counts, byte sizes, boolean flags,
and short status strings. This module imports no OpenHands client library,
``grpc``, ``httpx``, or ``websockets`` (contract C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    :return: ``datetime.now`` bound to UTC (never a naive timestamp), so every
        event timestamp is unambiguous and comparable across processes.
    """
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class OpenHandsConnected(DomainEvent):
    """Emitted exactly once when the OpenHands sidecar is ready to serve (C8).

    Signals that the REST/WS sidecar is reachable and its Docker-sandboxed
    runtime is available for this run. Paired with :class:`OpenHandsDisconnected`.

    :ivar run_id: Investigation run id this session is bound to.
    :ivar server_url: Ready ``host[:port]`` endpoint the client dialled;
        configuration, never incident payload (C13).
    :ivar mode: Lifecycle mode that produced the session — ``"external"`` for a
        pre-running sidecar, ``"managed"`` for an Aegis-started process (C8).
    :ivar timestamp: Timezone-aware UTC time the connection was established.
    """

    event_type: ClassVar[str] = "openhands.connected"

    run_id: str
    server_url: str
    mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsDisconnected(DomainEvent):
    """Emitted exactly once on sidecar teardown or connection loss (C8).

    Paired with :class:`OpenHandsConnected`; emitted on context exit in both
    external and managed modes, including when entry raised after the connection
    opened.

    :ivar run_id: Investigation run id this session was bound to.
    :ivar reason: Short, payload-free reason string, e.g. ``"context_exit"`` or
        ``"connection_lost"``; never an error payload.
    :ivar timestamp: Timezone-aware UTC time the disconnect fired.
    """

    event_type: ClassVar[str] = "openhands.disconnected"

    run_id: str
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsAction(DomainEvent):
    """Emitted on each ``Action`` event from the OpenHands stream (C8, C10).

    Records that the OpenHands agent loop invoked one of its allowlisted
    sandbox actions (an OpenHands ``Action`` is the equivalent of a tool call).
    The action's argument payload is **not** carried — it may contain incident
    payload or a sandbox command line — only the action kind and an argument
    count (C13).

    :ivar run_id: Run correlation id.
    :ivar action: OpenHands action kind, e.g. ``"read"``, ``"run"``, or
        ``"edit"`` (an allowlisted status string, never free-form text).
    :ivar arg_count: Number of arguments in the action; a count, not content.
    :ivar timestamp: Timezone-aware UTC time the action event was received.
    """

    event_type: ClassVar[str] = "openhands.action"

    run_id: str
    action: str
    arg_count: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsObservation(DomainEvent):
    """Emitted on each ``Observation`` event from the OpenHands stream (C8, C10).

    Records that a sandbox action returned an observation (the equivalent of a
    tool result). The observation text is **not** carried — it may contain
    incident payload — only its size in bytes and a success flag (C13).

    :ivar run_id: Run correlation id.
    :ivar observation: OpenHands observation kind that was produced, e.g.
        ``"run"`` or ``"read"``; a status string, never content.
    :ivar ok: ``True`` if the observation reported success, ``False`` on error.
    :ivar content_size: Byte length of the observation content; a count, not
        content.
    :ivar timestamp: Timezone-aware UTC time the observation event was received.
    """

    event_type: ClassVar[str] = "openhands.observation"

    run_id: str
    observation: str
    ok: bool
    content_size: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsPermissionDenied(DomainEvent):
    """Emitted when a sandbox action requests a non-allowlisted command (C8).

    OpenHands runs non-interactively inside a Docker sandbox; an action that
    requests a binary or operation outside the configured allowlist is denied,
    this event is emitted, and the invocation halts. Only the offending binary
    name is captured — never the full command line — so no incident payload
    leaks (C13). Paired with the :class:`PermissionDeniedError` raised by
    ``tool.py``.

    :ivar run_id: Run correlation id.
    :ivar action: OpenHands action kind that issued the request, e.g. ``"run"``.
    :ivar denied_binary: The binary name that was requested but not allowlisted.
    :ivar timestamp: Timezone-aware UTC time the request was denied.
    """

    event_type: ClassVar[str] = "openhands.permission_denied"

    run_id: str
    action: str
    denied_binary: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsCompleted(DomainEvent):
    """Emitted on the terminal stream event; the only event with token data (C10).

    Carries the token figure for the whole delegated call and the number of
    stream events consumed. Per C10 the token figure lives on this event alone
    and is never duplicated across other events. Per C9 the figure is the
    server-reported real usage when available, otherwise the boundary estimate
    ``max(1, len(content) // 4)``; ``usage_reported`` records which.

    :ivar run_id: Run correlation id.
    :ivar token_estimate: Total token figure for the call, surfaced through the
        same ``CodeResult.token_estimate`` field name across all backends (C9).
    :ivar usage_reported: ``True`` when ``token_estimate`` is a server-reported
        real usage count, ``False`` when it is the boundary estimate (C9).
    :ivar event_count: Total number of stream events consumed to completion.
    :ivar truncated: ``True`` if accumulated content hit the response cap and was
        truncated.
    :ivar timestamp: Timezone-aware UTC time the stream completed.
    """

    event_type: ClassVar[str] = "openhands.completed"

    run_id: str
    token_estimate: int
    usage_reported: bool
    event_count: int
    truncated: bool
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenHandsError(DomainEvent):
    """Emitted on an error event or a terminal transport failure (C8).

    Carries only a classification and a status code — never the raw error
    message from OpenHands, which may echo observation or payload text (C13).

    :ivar run_id: Run correlation id.
    :ivar error_type: Classification, e.g. ``"stream_error"`` (an error event on
        the Action/Observation stream) or ``"transport"`` (a REST/WS transport
        failure).
    :ivar code: Short status code, e.g. ``"UNAVAILABLE"``, an HTTP status name,
        or ``"stream_error"``; a status string only.
    :ivar event_count: Number of stream events consumed before the error.
    :ivar timestamp: Timezone-aware UTC time the error was observed.
    """

    event_type: ClassVar[str] = "openhands.error"

    run_id: str
    error_type: str
    code: str
    event_count: int
    timestamp: datetime = field(default_factory=_utc_now)
