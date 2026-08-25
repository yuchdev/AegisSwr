"""Claude Code lifecycle and NDJSON-stream events (contract C10).

The eight ``claude_code.*`` frozen event dataclasses that observe the one-shot
``claude`` delegation lifecycle and its ``stream-json`` (NDJSON) result. Each
event **subclasses the live** :class:`aegis_swr.core.events.DomainEvent`, carries
a ``run_id``, a timezone-aware UTC ``timestamp``, and a ``ClassVar[str]
event_type`` sentinel that consumers filter on
(``event.event_type == "claude_code.completed"``) without ``isinstance`` checks.

Subclassing :class:`DomainEvent` is load-bearing, not cosmetic. The bus that
ships (:class:`aegis_swr.core.events.EventBus`) dispatches by walking
``type(event).__mro__`` and delivers only to :class:`DomainEvent` subclasses, so
a subscriber to :class:`DomainEvent` receives every ``claude_code.*`` event and a
subscriber to a concrete subclass receives just that one. No separate
registration step and no change to :mod:`aegis_swr.core.events` is required (this
is why Milestone 0004's third "registry" subtask is unnecessary here). A plain
dataclass would reach zero subscribers.

Because these events observe model output and process state, C10/C13 impose a
hard rule: **no field may carry raw incident payload, tool arguments, unredacted
response text, argv, or any credential/token value** - only ids, counts,
estimates, and short status strings. :class:`ClaudeCodeCompleted` alone carries
the token figure (C9); :class:`ClaudeCodeAuthFailed` carries only a
fixed-vocabulary failure reason (C7).

This module imports only :mod:`aegis_swr.core.events` from the project (plus
stdlib); it never imports a sibling backend, ``grpc``, or any client library
(C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar, Optional

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC ``datetime``.

    :return: ``datetime.now`` bound to :data:`datetime.UTC` so every event
        timestamp is unambiguous and comparable across processes (never a naive
        timestamp).
    """
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeSpawned(DomainEvent):
    """Emitted exactly once when the one-shot ``claude`` subprocess starts (C6).

    Signals that a fresh Claude Code process has been spawned for this
    ``delegate()`` call and code-intelligence capability is in use. There is no
    persistent sidecar - this is the per-call "process up" signal, paired with
    :class:`ClaudeCodeExited`.

    :ivar run_id: Run correlation id shared by every event in one delegation.
    :ivar auth_mode: Resolved authentication mode, ``"auto"`` | ``"api_key"`` |
        ``"subscription"`` (C7). A mode *name*, never a credential or token.
    :ivar binary: Configured binary name (e.g. ``"claude"``); configuration,
        never argv or incident payload.
    :ivar timestamp: Timezone-aware UTC instant the subprocess was spawned.
    """

    event_type: ClassVar[str] = "claude_code.spawned"

    run_id: str
    auth_mode: str
    binary: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeExited(DomainEvent):
    """Emitted exactly once when the one-shot ``claude`` subprocess is reaped.

    Paired with :class:`ClaudeCodeSpawned`; emitted on normal completion,
    timeout, spawn failure, or non-zero exit. Carries a classification and the
    process return code only - never the process's stderr/stdout text (C13).

    :ivar run_id: Run correlation id.
    :ivar reason: Short status string, e.g. ``"completed"``, ``"timeout"``,
        ``"spawn_failed"``, or ``"nonzero_exit"``; never an error payload.
    :ivar exit_code: Subprocess return code when known; ``None`` when the
        process never started (``"spawn_failed"``). A number, not content.
    :ivar timestamp: Timezone-aware UTC instant the subprocess exited or was
        reaped.
    """

    event_type: ClassVar[str] = "claude_code.exited"

    run_id: str
    reason: str
    exit_code: Optional[int] = None
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeToolCall(DomainEvent):
    """Emitted on each tool-use message parsed from the NDJSON stream (C6).

    Records that Claude Code's internal loop invoked one of its allowlisted
    tools. The tool's argument JSON is **not** carried - it may contain incident
    payload - only the tool name and an argument count (C10/C13).

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool name, e.g. ``"Grep"`` (an allowlisted status
        string, never free-form text).
    :ivar arg_count: Number of arguments in the tool call; a count, not content.
    :ivar timestamp: Timezone-aware UTC instant the message was parsed.
    """

    event_type: ClassVar[str] = "claude_code.tool_call"

    run_id: str
    tool: str
    arg_count: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeToolResult(DomainEvent):
    """Emitted on each tool-result message parsed from the NDJSON stream (C6).

    Records that a tool invocation returned. The tool output text is **not**
    carried - it may contain incident payload - only its size in bytes and a
    success flag (C10/C13).

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool name that produced the result.
    :ivar ok: ``True`` if the tool reported success, ``False`` on tool error.
    :ivar result_size: Byte length of the tool output; a count, not content.
    :ivar timestamp: Timezone-aware UTC instant the message was parsed.
    """

    event_type: ClassVar[str] = "claude_code.tool_result"

    run_id: str
    tool: str
    ok: bool
    result_size: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodePermissionDenied(DomainEvent):
    """Emitted when a tool/command outside the allowlist is denied (C6).

    Claude Code runs non-interactively with ``--allowedTools`` and a
    non-bypassing ``permission_mode``; a request for a tool or ``Bash`` binary
    outside the allowlist is denied, this event is emitted, and the invocation
    halts. Only the offending binary name is captured - never the full command
    line - so no incident payload leaks (C10/C13). Paired with the raised
    :class:`aegis_swr.claude_code.exceptions.PermissionDeniedError`.

    :ivar run_id: Run correlation id.
    :ivar tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :ivar denied_binary: The binary name that was requested but not allowlisted.
    :ivar timestamp: Timezone-aware UTC instant the request was denied.
    """

    event_type: ClassVar[str] = "claude_code.permission_denied"

    run_id: str
    tool: str
    denied_binary: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeAuthFailed(DomainEvent):
    """Emitted when the startup auth-probe or a delegation reveals bad auth (C7).

    Carries **only** a short failure-reason status string and the mode that was
    attempted. It **never** carries a credential, an OAuth token, a
    ``CLAUDE_CODE_OAUTH_TOKEN`` value, an ``ANTHROPIC_API_KEY`` value, or a
    credential-file path (C7/C13). Paired with the raised
    :class:`aegis_swr.claude_code.exceptions.ClaudeCodeUnavailableError`.

    :ivar run_id: Run correlation id.
    :ivar reason: One of ``"ambiguous_credential"`` (an ``ANTHROPIC_API_KEY`` /
        ``ANTHROPIC_AUTH_TOKEN`` present under ``subscription`` mode),
        ``"no_stored_login"`` (subscription mode with no usable stored session
        and no ``CLAUDE_CODE_OAUTH_TOKEN``), or ``"token_rejected"`` (the
        resolved credential was rejected by the probe). A fixed vocabulary of
        status strings only.
    :ivar auth_mode: The authentication mode being attempted, ``"auto"`` |
        ``"api_key"`` | ``"subscription"`` (C7). A mode name, never a credential.
    :ivar timestamp: Timezone-aware UTC instant the auth failure was observed.
    """

    event_type: ClassVar[str] = "claude_code.auth_failed"

    run_id: str
    reason: str
    auth_mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeCompleted(DomainEvent):
    """Emitted on the terminal ``result`` message; the only event with token data.

    Carries the **real** token accounting from the ``stream-json`` terminal
    ``result`` message (C9) - Claude Code reports actual usage rather than a
    boundary estimate. Per C10 the token figure lives on this event alone and is
    never duplicated across other events; ``input_tokens`` / ``output_tokens``
    are the two components of the reported sum and sit on this same single event
    (they are not a second carrier of the figure).

    :ivar run_id: Run correlation id.
    :ivar token_estimate: ``usage.input_tokens + usage.output_tokens`` from the
        terminal ``result`` message - the **real** count charged to the budget
        via ``CodeResult.token_estimate`` (C9). Keeps the shared field name so
        ``CodeAgent`` stays backend-agnostic.
    :ivar input_tokens: Reported ``usage.input_tokens`` component; a real count.
    :ivar output_tokens: Reported ``usage.output_tokens`` component; a real
        count.
    :ivar num_turns: Number of agent turns consumed to completion when reported
        by the ``result`` message; ``None`` if the field is absent. A count.
    :ivar timestamp: Timezone-aware UTC instant the stream completed.
    """

    event_type: ClassVar[str] = "claude_code.completed"

    run_id: str
    token_estimate: int
    input_tokens: int
    output_tokens: int
    num_turns: Optional[int] = None
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeError(DomainEvent):
    """Emitted on a spawn/parse/timeout/non-zero-exit failure of the call (C6).

    Carries only a classification and a short status code - never the raw error
    text from the ``claude`` process, which may echo response or payload text
    (C13).

    :ivar run_id: Run correlation id.
    :ivar error_type: Classification, one of ``"spawn_error"``,
        ``"parse_error"``, ``"timeout"``, or ``"nonzero_exit"``.
    :ivar code: Short status code, e.g. ``"ENOENT"``, ``"DEADLINE_EXCEEDED"``,
        or the string form of a non-zero exit code; a status string only.
    :ivar timestamp: Timezone-aware UTC instant the error was observed.
    """

    event_type: ClassVar[str] = "claude_code.error"

    run_id: str
    error_type: str
    code: str
    timestamp: datetime = field(default_factory=_utc_now)
