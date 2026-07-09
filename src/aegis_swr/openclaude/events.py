"""Forward declaration of OpenClaude lifecycle events (owned by Task 05.0).

This module hosts the minimal ``OpenClaude*`` lifecycle events that the process
lifecycle manager (Task 03.0) needs to emit before Task 05.0 canonicalises the
full event set - mirroring how ``exceptions.py`` forward-declares the exception
hierarchy.

Both events **subclass the live** :class:`aegis_swr.core.events.DomainEvent`.
This deliberately deviates from Task 05.0's stale draft text (which described a
plain dataclass carrying an ``event_type`` string and no base class): that draft
assumed a routing event bus keyed on a string discriminator which was never
built. The bus that actually ships (:class:`aegis_swr.core.events.EventBus`)
dispatches by walking ``type(event).__mro__`` and delivers only to
:class:`DomainEvent` subclasses, so a plain dataclass would be silently dropped
to zero subscribers. Subclassing :class:`DomainEvent` is therefore the only
shape that dispatches on the live bus.

When Task 05.0 canonicalises these events it **must preserve** both the
:class:`DomainEvent` subclassing and the field names declared here so existing
subscribers and the Task 03.0 emitter keep working; it may only extend them.

This module must not import ``grpc`` or ``litellm`` (contract C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    :return: ``datetime.now`` bound to UTC (never a naive timestamp).
    """
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeConnected(DomainEvent):
    """Emitted once when an OpenClaude session is ready to serve requests.

    :ivar run_id: Investigation run id this session is bound to.
    :ivar grpc_url: Ready ``host[:port]`` endpoint the caller may dial;
        configuration, never incident payload (C9).
    :ivar mode: Lifecycle mode that produced the session - ``"external"`` for a
        pre-running sidecar, ``"managed"`` for an Aegis-started process.
    :ivar timestamp: Timezone-aware UTC time the connection was established.
    """

    event_type: ClassVar[str] = "openclaude.connected"

    run_id: str
    grpc_url: str
    mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeDisconnected(DomainEvent):
    """Emitted once when an OpenClaude session is torn down.

    :ivar run_id: Investigation run id this session was bound to.
    :ivar reason: Short, payload-free reason string (e.g. ``"context_exit"``).
    :ivar timestamp: Timezone-aware UTC time the disconnect fired.
    """

    event_type: ClassVar[str] = "openclaude.disconnected"

    run_id: str
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeToolCall(DomainEvent):
    """Emitted on each ``TOOL_CALL`` frame from the gRPC stream (C2).

    Records that OpenClaude's internal loop invoked one of its allowlisted
    tools. The tool's argument JSON is **not** carried - it may contain incident
    payload - only the tool name and an argument count (C9).

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool name, e.g. ``"Grep"`` (an allowlisted status
        string, never free-form text).
    :ivar arg_count: Number of arguments in the tool call; a count, not content.
    :ivar timestamp: Timezone-aware UTC time the frame was received.
    """

    event_type: ClassVar[str] = "openclaude.tool_call"

    run_id: str
    tool: str
    arg_count: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeToolResult(DomainEvent):
    """Emitted on each ``TOOL_RESULT`` frame from the gRPC stream (C2).

    Records that a tool invocation returned. The tool output text is **not**
    carried - it may contain incident payload - only its size in bytes and a
    success flag (C9).

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool name that produced the result.
    :ivar ok: ``True`` if the tool reported success, ``False`` on tool error.
    :ivar result_size: Byte length of the tool output; a count, not content.
    :ivar timestamp: Timezone-aware UTC time the frame was received.
    """

    event_type: ClassVar[str] = "openclaude.tool_result"

    run_id: str
    tool: str
    ok: bool
    result_size: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudePermissionDenied(DomainEvent):
    """Emitted on a ``PERMISSION_REQ`` frame for a disallowed command (C2, C7).

    OpenClaude runs non-interactively; a request for a tool or ``Bash`` binary
    outside the allowlist is denied, this event is emitted, and the invocation
    halts. Only the offending binary name is captured - never the full command
    line - so no incident payload leaks (C9).

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :ivar denied_binary: The binary name that was requested but not allowlisted.
    :ivar timestamp: Timezone-aware UTC time the request was denied.
    """

    event_type: ClassVar[str] = "openclaude.permission_denied"

    run_id: str
    tool: str
    denied_binary: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeStreamCompleted(DomainEvent):
    """Emitted on the terminal ``DONE`` frame; the only event with token data.

    Carries the boundary token estimate for the whole delegated call (C5) and
    the number of stream frames consumed. Per C8 the token estimate lives on
    this event alone and is never duplicated across other events.

    :ivar run_id: Run correlation id.
    :ivar token_estimate: Boundary token estimate for the call,
        ``max(1, len(content) // 4)`` (C5); an estimate, not an exact count.
    :ivar frame_count: Total number of stream frames consumed to completion.
    :ivar truncated: ``True`` if accumulated content hit ``max_response_tokens``
        and was truncated (C5).
    :ivar timestamp: Timezone-aware UTC time the stream completed.
    """

    event_type: ClassVar[str] = "openclaude.stream_completed"

    run_id: str
    token_estimate: int
    frame_count: int
    truncated: bool
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeStreamError(DomainEvent):
    """Emitted on an ``ERROR`` frame or a terminal gRPC status error (C2).

    Carries only a classification and a status code - never the raw error
    message from OpenClaude, which may echo response or payload text (C9).

    :ivar run_id: Run correlation id.
    :ivar error_type: Classification, ``"stream_error"`` (an ``ERROR`` frame) or
        ``"grpc_status"`` (a channel-level status error).
    :ivar code: Short status code, e.g. ``"UNAVAILABLE"``,
        ``"DEADLINE_EXCEEDED"``, or ``"stream_error"``; a status string only.
    :ivar frame_count: Number of frames consumed before the error.
    :ivar timestamp: Timezone-aware UTC time the error was observed.
    """

    event_type: ClassVar[str] = "openclaude.stream_error"

    run_id: str
    error_type: str
    code: str
    frame_count: int
    timestamp: datetime = field(default_factory=_utc_now)
