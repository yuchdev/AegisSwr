# 01 - Seven event dataclasses

**Parent task:** 05.0 Event Types & Exceptions
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03, 03.0, 04.0

## Objective

Implement `aegis/openclaude/events.py` - the seven `frozen=True` event
dataclasses of contract C8 that observe the OpenClaude delegation lifecycle and
gRPC stream. Each is emitted on the existing `EventBus` (the same bus the
Milestone 0003 `RouterEvent` types use), carries a `run_id`, a UTC `timestamp`,
and a `ClassVar[str]` `event_type` sentinel that consumers filter on
(`event.event_type == "openclaude.stream_completed"`) without `isinstance`
checks. They follow the router's `aegis/router/events.py` pattern exactly: plain
frozen dataclasses that do **not** subclass any base event and carry no `litellm`
/ `grpc` imports. Because these events observe model output, C9 imposes a hard
rule: **no field may carry raw incident payload, tool arguments, or unredacted
response text** - only ids, counts, estimates, and short status strings.

## File: `aegis/openclaude/events.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    :return: ``datetime.now`` bound to :data:`datetime.timezone.utc` so every
        event timestamp is unambiguous and comparable across processes.
    """
    return datetime.now(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeConnected:
    """Emitted exactly once after a successful health check or process start.

    Signals that the OpenClaude gRPC sidecar is reachable and code-intelligence
    capability is available for this run (C6).

    :ivar run_id: Run correlation id shared by every event in one delegation.
    :ivar timestamp: UTC instant the connection was established.
    :ivar grpc_url: Host[:port] of the sidecar; configuration, never payload.
    :ivar mode: Lifecycle mode, ``"external"`` or ``"managed"`` (C6).
    """

    event_type: ClassVar[str] = "openclaude.connected"
    run_id: str
    grpc_url: str
    mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeDisconnected:
    """Emitted exactly once on process stop or connection loss.

    Paired with :class:`OpenClaudeConnected`; emitted on context exit in both
    external and managed modes, including when entry raised after the port
    opened (C6).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant of disconnection.
    :ivar reason: Short status string, e.g. ``"context_exit"`` or
        ``"connection_lost"``; never an error payload.
    """

    event_type: ClassVar[str] = "openclaude.disconnected"
    run_id: str
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeToolCall:
    """Emitted on each ``TOOL_CALL`` frame from the gRPC stream (C2).

    Records that OpenClaude's internal loop invoked one of its allowlisted
    tools. The tool's argument JSON is **not** carried - it may contain incident
    payload - only the tool name and an argument count (C9).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the frame was received.
    :ivar tool: Claude Code tool name, e.g. ``"Grep"`` (an allowlisted status
        string, never free-form text).
    :ivar arg_count: Number of arguments in the tool call; a count, not content.
    """

    event_type: ClassVar[str] = "openclaude.tool_call"
    run_id: str
    tool: str
    arg_count: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeToolResult:
    """Emitted on each ``TOOL_RESULT`` frame from the gRPC stream (C2).

    Records that a tool invocation returned. The tool output text is **not**
    carried - it may contain incident payload - only its size in bytes and a
    success flag (C9).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the frame was received.
    :ivar tool: Claude Code tool name that produced the result.
    :ivar ok: ``True`` if the tool reported success, ``False`` on tool error.
    :ivar result_size: Byte length of the tool output; a count, not content.
    """

    event_type: ClassVar[str] = "openclaude.tool_result"
    run_id: str
    tool: str
    ok: bool
    result_size: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudePermissionDenied:
    """Emitted on a ``PERMISSION_REQ`` frame for a disallowed command (C2, C7).

    OpenClaude runs non-interactively; a request for a tool or ``Bash`` binary
    outside the allowlist is denied, this event is emitted, and the invocation
    halts. Only the offending binary name is captured - never the full command
    line - so no incident payload leaks (C9).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the request was denied.
    :ivar tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :ivar denied_binary: The binary name that was requested but not allowlisted.
    """

    event_type: ClassVar[str] = "openclaude.permission_denied"
    run_id: str
    tool: str
    denied_binary: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeStreamCompleted:
    """Emitted on the terminal ``DONE`` frame; the only event with token data.

    Carries the boundary token estimate for the whole delegated call (C5) and
    the number of stream frames consumed. Per C8 the token estimate lives on
    this event alone and is never duplicated across other events.

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the stream completed.
    :ivar token_estimate: Boundary token estimate for the call,
        ``max(1, len(content) // 4)`` (C5); an estimate, not an exact count.
    :ivar frame_count: Total number of stream frames consumed to completion.
    :ivar truncated: ``True`` if accumulated content hit ``max_response_tokens``
        and was truncated (C5).
    """

    event_type: ClassVar[str] = "openclaude.stream_completed"
    run_id: str
    token_estimate: int
    frame_count: int
    truncated: bool
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True, kw_only=True)
class OpenClaudeStreamError:
    """Emitted on an ``ERROR`` frame or a terminal gRPC status error (C2).

    Carries only a classification and a status code - never the raw error
    message from OpenClaude, which may echo response or payload text (C9).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the error was observed.
    :ivar error_type: Classification, ``"stream_error"`` (an ``ERROR`` frame) or
        ``"grpc_status"`` (a channel-level status error).
    :ivar code: Short status code, e.g. ``"UNAVAILABLE"``,
        ``"DEADLINE_EXCEEDED"``, or ``"stream_error"``; a status string only.
    :ivar frame_count: Number of frames consumed before the error.
    """

    event_type: ClassVar[str] = "openclaude.stream_error"
    run_id: str
    error_type: str
    code: str
    frame_count: int
    timestamp: datetime = field(default_factory=_utc_now)
```

## Design rationale

- **`kw_only=True`** makes every construction keyword-only (05.0 key
  constraint), so field order is free and a `timestamp` with a default factory
  can sit last without forcing defaults on the preceding fields - which a
  positional frozen dataclass would reject.
- **`ClassVar[str] event_type`** mirrors `aegis/router/events.py`: subscribers
  filter by `event.event_type == "openclaude.stream_completed"` instead of
  `isinstance`, and the string is not an instance field (it never appears in a
  constructor call).
- **`timestamp: datetime` via `_utc_now`** is always timezone-aware UTC; the
  factory (not `datetime.utcnow`) guarantees the `tzinfo` is set so events are
  comparable and serialise unambiguously.
- **`OpenClaudeStreamCompleted` is the sole carrier of `token_estimate`**
  (C5/C8). No tool-call, tool-result, or error event carries token data, keeping
  telemetry aggregation single-sourced - the same invariant `RouterCallCompleted`
  holds for the router.
- **Payload-free by construction.** `OpenClaudeToolCall` carries `arg_count`
  (not the args JSON); `OpenClaudeToolResult` carries `result_size` (not the
  output); `OpenClaudeStreamError` carries `code` (not the raw message);
  `OpenClaudePermissionDenied` carries `denied_binary` (not the full command).
  This is the C9 hard rule for this taxonomy, because these events observe model
  output directly.

## Constraints

- All seven dataclasses are `frozen=True, kw_only=True`.
- Every class has a `ClassVar[str] event_type` set to the exact `openclaude.*`
  string from C8; `run_id: str` and `timestamp: datetime`.
- **No field is typed `Any`** (05.0 key constraint); all fields are `str`,
  `int`, `bool`, or `datetime`.
- No raw incident payload, tool arguments, or unredacted response text on any
  field - only ids, counts, estimates, and short status strings (C9).
- `token_estimate` appears on `OpenClaudeStreamCompleted` only (C8).
- `from __future__ import annotations` at the top; `Optional[T]` from `typing`
  if any optional field is later added (none needed now); `mypy --strict` clean.
- No `grpc` or `litellm` import in this file (C3).

## Success criteria

- [ ] All seven event classes exist with the fields and `event_type` strings
      above, matching the C8 table exactly.
- [ ] Every class is `frozen=True` and constructs keyword-only (positional
      construction raises `TypeError`).
- [ ] Every instance carries `run_id: str` and a timezone-aware UTC
      `timestamp: datetime`.
- [ ] `OpenClaudeStreamCompleted` is the only class exposing `token_estimate`
      (and it also carries `frame_count` and `truncated`).
- [ ] No field annotation is `Any`; `mypy --strict` and
      `replace_optional.py --check` are clean.
- [ ] No field carries tool arguments, tool output, response text, or a raw
      error message (asserted by a unit test inspecting field names/types).
- [ ] `python -c "import aegis.openclaude.events"` succeeds with no `grpc`
      import pulled in.
