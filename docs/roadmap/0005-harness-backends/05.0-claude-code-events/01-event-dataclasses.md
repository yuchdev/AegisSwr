# 01 - Eight `claude_code.*` event dataclasses

**Parent task:** 05.0 Claude Code Events & Exceptions
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none

## Objective

Implement `aegis_swr/claude_code/events.py` — the **eight** `frozen=True`,
`kw_only=True` event dataclasses of contract **C10** that observe the Claude
Code one-shot delegation lifecycle and its NDJSON (`stream-json`) result. Each
event **subclasses the live `aegis_swr.core.events.DomainEvent`** (the shape
Milestone 0004 actually shipped — see [plan.md](/docs/roadmap/0005-harness-backends/plan.md) C10, which explicitly overrides
the stale plain-dataclass/`event_type`-string spec text), carries a `run_id`, a
UTC `timestamp`, and a `ClassVar[str] event_type` sentinel that consumers filter
on (`event.event_type == "claude_code.completed"`) without `isinstance` checks.

Because these events subclass `DomainEvent`, they are distributed by the
existing `EventBus` for free: `EventBus.publish` walks `type(event).__mro__`, so
a subscriber to `DomainEvent` receives every `claude_code.*` event and a
subscriber to a concrete subclass receives just that one. **No change to
`aegis_swr/core/events.py` and no separate registration step is required** (this
is why Milestone 0004's third "registry" subtask is unnecessary here).

Because these events observe model output and process state, C10/C13 impose a
hard rule: **no field may carry raw incident payload, tool arguments,
unredacted response text, argv, or any credential/token value** — only ids,
counts, estimates, and short status strings. `ClaudeCodeAuthFailed` in
particular carries **only** a failure-reason string (C7).

## Confirmed base-class shape

`aegis_swr/core/events.py` currently defines:

```python
@dataclass(frozen=True)
class DomainEvent:
    """Base class for all investigation events"""
    pass
```

It is a frozen dataclass with **no fields**, so every `claude_code.*` subclass
adds its own `run_id`, `timestamp`, and payload-free fields. Declaring the
subclasses `kw_only=True` lets a defaulted `timestamp` sit last without forcing
defaults on the preceding required fields (a positional frozen dataclass would
reject that ordering). The `kw_only` base-has-no-fields combination is safe: the
base contributes no fields to the ordering.

## File: `aegis_swr/claude_code/events.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar, Optional

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC ``datetime``.

    :return: ``datetime.now`` bound to :data:`datetime.timezone.utc` so every
        event timestamp is unambiguous and comparable across processes.
    """
    return datetime.now(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class ClaudeCodeSpawned(DomainEvent):
    """Emitted exactly once when the one-shot ``claude`` subprocess starts (C6).

    Signals that a fresh Claude Code process has been spawned for this
    ``delegate()`` call and code-intelligence capability is in use. There is no
    persistent sidecar — this is the per-call "process up" signal, paired with
    :class:`ClaudeCodeExited`.

    :ivar run_id: Run correlation id shared by every event in one delegation.
    :ivar timestamp: UTC instant the subprocess was spawned.
    :ivar auth_mode: Resolved authentication mode, ``"auto"`` | ``"api_key"`` |
        ``"subscription"`` (C7). A mode *name*, never a credential or token.
    :ivar binary: Configured binary name (e.g. ``"claude"``); configuration,
        never argv or incident payload.
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
    process return code only — never the process's stderr/stdout text (C13).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the subprocess exited or was reaped.
    :ivar reason: Short status string, e.g. ``"completed"``, ``"timeout"``,
        ``"spawn_failed"``, or ``"nonzero_exit"``; never an error payload.
    :ivar exit_code: Subprocess return code when known; ``None`` when the
        process never started (``"spawn_failed"``). A number, not content.
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
    tools. The tool's argument JSON is **not** carried — it may contain incident
    payload — only the tool name and an argument count (C10/C13).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the message was parsed.
    :ivar tool: Claude Code tool name, e.g. ``"Grep"`` (an allowlisted status
        string, never free-form text).
    :ivar arg_count: Number of arguments in the tool call; a count, not content.
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
    carried — it may contain incident payload — only its size in bytes and a
    success flag (C10/C13).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the message was parsed.
    :ivar tool: Claude Code tool name that produced the result.
    :ivar ok: ``True`` if the tool reported success, ``False`` on tool error.
    :ivar result_size: Byte length of the tool output; a count, not content.
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
    halts. Only the offending binary name is captured — never the full command
    line — so no incident payload leaks (C10/C13). Paired with the raised
    :class:`aegis_swr.claude_code.exceptions.PermissionDeniedError`.

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the request was denied.
    :ivar tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :ivar denied_binary: The binary name that was requested but not allowlisted.
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
    :ivar timestamp: UTC instant the auth failure was observed.
    :ivar reason: One of ``"ambiguous_credential"`` (an ``ANTHROPIC_API_KEY`` /
        ``ANTHROPIC_AUTH_TOKEN`` present under ``subscription`` mode),
        ``"no_stored_login"`` (subscription mode with no usable stored session
        and no ``CLAUDE_CODE_OAUTH_TOKEN``), or ``"token_rejected"`` (the
        resolved credential was rejected by the probe). A fixed vocabulary of
        status strings only.
    :ivar auth_mode: The authentication mode being attempted, ``"auto"`` |
        ``"api_key"`` | ``"subscription"`` (C7). A mode name, never a credential.
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
    ``result`` message (C9) — Claude Code reports actual usage rather than a
    boundary estimate. Per C10 the token figure lives on this event alone and is
    never duplicated across other events; ``input_tokens`` / ``output_tokens``
    are the two components of the reported sum and sit on this same single event
    (they are not a second carrier of the figure).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the stream completed.
    :ivar token_estimate: ``usage.input_tokens + usage.output_tokens`` from the
        terminal ``result`` message — the **real** count charged to the budget
        via ``CodeResult.token_estimate`` (C9). Keeps the shared field name so
        ``CodeAgent`` stays backend-agnostic.
    :ivar input_tokens: Reported ``usage.input_tokens`` component; a real count.
    :ivar output_tokens: Reported ``usage.output_tokens`` component; a real count.
    :ivar num_turns: Number of agent turns consumed to completion when reported
        by the ``result`` message; ``None`` if the field is absent. A count.
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

    Carries only a classification and a short status code — never the raw error
    text from the ``claude`` process, which may echo response or payload text
    (C13).

    :ivar run_id: Run correlation id.
    :ivar timestamp: UTC instant the error was observed.
    :ivar error_type: Classification, one of ``"spawn_error"``,
        ``"parse_error"``, ``"timeout"``, or ``"nonzero_exit"``.
    :ivar code: Short status code, e.g. ``"ENOENT"``, ``"DEADLINE_EXCEEDED"``,
        or the string form of a non-zero exit code; a status string only.
    """

    event_type: ClassVar[str] = "claude_code.error"
    run_id: str
    error_type: str
    code: str
    timestamp: datetime = field(default_factory=_utc_now)
```

## Implementation notes

- **Subclass `DomainEvent`, not a plain dataclass.** This is the C10-mandated
  divergence from Milestone 0004's `openclaude.*` events (which were plain
  frozen dataclasses matching the router pattern). Subclassing lets the events
  flow through the existing `EventBus` with no registration and lets views
  subscribe to `DomainEvent` to receive the whole `claude_code.*` family.
- **`kw_only=True`** makes every construction keyword-only, so field order is
  free and a `timestamp` with a default factory can sit last without forcing
  defaults on the preceding required fields.
- **`ClassVar[str] event_type`** is the filter sentinel: subscribers branch on
  `event.event_type == "claude_code.completed"` rather than `isinstance`. As a
  `ClassVar` it is not an instance field and never appears in a constructor call.
- **`timestamp` via `_utc_now`** is always timezone-aware UTC; the factory (not
  `datetime.utcnow`) guarantees `tzinfo` is set so events are comparable and
  serialise unambiguously — identical to the 0004 events' convention.
- **`ClaudeCodeCompleted` is the sole carrier of the token figure (C9/C10).**
  No spawn/tool/error event carries token data. The real `input_tokens` /
  `output_tokens` components live on this one event alongside their sum, so the
  charged figure and its provenance are single-sourced. This is the genuine
  accounting improvement over OpenClaude's boundary estimate, delivered without
  changing `CodeResult.token_estimate`'s shape.
- **Payload-free by construction.** `ClaudeCodeToolCall` carries `arg_count`
  (not the args JSON); `ClaudeCodeToolResult` carries `result_size` (not the
  output); `ClaudeCodeError` carries `code` (not the raw message);
  `ClaudeCodePermissionDenied` carries `denied_binary` (not the full command);
  `ClaudeCodeAuthFailed` carries `reason` from a fixed vocabulary (never a
  credential). This is the C10/C13 hard rule for this taxonomy.
- **`ClaudeCodeAuthFailed.reason` vocabulary is fixed** and aligns 1:1 with the
  reason string carried by `ClaudeCodeUnavailableError` (subtask 02), so the
  emitted event and the raised exception describe the same failure without ever
  exposing the credential that caused it (C7).
- **`exit_code` and `num_turns` are `Optional[int]`** because a spawn failure
  has no return code and a `result` message may omit the turn count; both are
  the only optional fields in the taxonomy and are written `Optional[int]` (never
  `int | None`) per C13.

## Constraints

- All eight dataclasses subclass `aegis_swr.core.events.DomainEvent` and are
  `frozen=True, kw_only=True`.
- Every class has a `ClassVar[str] event_type` set to the exact `claude_code.*`
  string from the C10 table; `run_id: str` and a UTC `timestamp: datetime`.
- **No field is typed `Any`**; all fields are `str`, `int`, `bool`, `datetime`,
  or `Optional[int]`.
- No raw incident payload, tool arguments, unredacted response text, argv, or
  credential/token value on any field — only ids, counts, estimates, and short
  status strings (C10/C13).
- `token_estimate` appears on `ClaudeCodeCompleted` only, never duplicated (C10).
- `ClaudeCodeAuthFailed` carries only the fixed-vocabulary `reason` and the mode
  name — never a credential (C7).
- `from __future__ import annotations` at the top; `Optional[T]` from `typing`,
  never `T | None`; `replace_optional.py --check` clean; `ruff` clean.
- Imports only `aegis_swr.core.events` from the project (plus stdlib); no
  sibling backend, `grpc`, or client-library import (C3). Importing
  `aegis_swr.core` from a backend is permitted — C3 forbids only the reverse.

## Success criteria

- [ ] All eight event classes exist with the fields and `event_type` strings
      above, matching the C10 table exactly, and each subclasses `DomainEvent`.
- [ ] Every class is `frozen=True` and constructs keyword-only (positional
      construction raises `TypeError`).
- [ ] Every instance carries `run_id: str` and a timezone-aware UTC
      `timestamp: datetime`.
- [ ] `ClaudeCodeCompleted` is the only class exposing `token_estimate` (and it
      also carries `input_tokens`, `output_tokens`, and `num_turns`).
- [ ] `ClaudeCodeAuthFailed` exposes only `reason` (fixed vocabulary) and
      `auth_mode`; no field can hold a credential or token (asserted by a unit
      test inspecting field names/types).
- [ ] No field annotation is `Any`; the only `Optional` fields are `exit_code`
      and `num_turns`; `ruff` and `replace_optional.py --check` are clean.
- [ ] No field carries tool arguments, tool output, response text, argv, a raw
      error message, or a credential (asserted by a unit test inspecting field
      names/types).
- [ ] All eight events round-trip through a real `EventBus`
      publish/subscribe cycle: a `DomainEvent` subscriber receives all eight,
      and a concrete-subclass subscriber receives just its own, distinguishable
      by `event.event_type`.
- [ ] `python -c "import aegis_swr.claude_code.events"` succeeds with no `grpc`
      or client-library import pulled in.
