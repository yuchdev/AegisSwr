# 01 - Seven OpenHands event dataclasses

**Parent task:** 09.0 OpenHands Events & Exceptions
**State:** ✅ Complete
**Depends on:** none (uses only the live `aegis_swr.core.events.DomainEvent`)
**Blocks:** 08.0

## Objective

Implement `aegis_swr/openhands/events.py` — the seven `frozen=True, kw_only=True`
event dataclasses of the OpenHands column of contract [C10](/docs/roadmap/0005-harness-backends/plan.md#c10--per-backend-event-taxonomy)
that observe the OpenHands delegation lifecycle and the Docker-sandboxed
Action/Observation event stream. Each is emitted on the existing
`aegis_swr.core.events.EventBus` and **subclasses the live**
`aegis_swr.core.events.DomainEvent`, carrying `run_id`, a UTC `timestamp`, and a
`ClassVar[str] event_type` sentinel.

**Subclass `DomainEvent` — do not write a plain dataclass.** The live
`EventBus` (`src/aegis_swr/core/events.py`) dispatches by walking
`type(event).__mro__` and delivering only to `DomainEvent` subclasses; a plain
dataclass carrying a bare `event_type` string (as 0004's task 05.0 *draft* text
described) is silently dropped to zero subscribers. The OpenClaude events that
actually shipped (`src/aegis_swr/openclaude/events.py`) already resolved this by
subclassing `DomainEvent`, and this file mirrors that shipped shape exactly. The
`event_type` `ClassVar` remains — consumers filter with
`event.event_type == "openhands.completed"` without `isinstance` checks — but it
is a discriminator *alongside* the base class, not a replacement for it.

Because these events observe sandbox tool output, C13 imposes a hard rule:
**no field may carry raw incident payload, action arguments, sandbox command
lines, or unredacted observation text** — only ids, counts, byte sizes, boolean
flags, and short status strings.

## File: `aegis_swr/openhands/events.py`

```python
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
```

## Implementation notes

- **Subclass `DomainEvent`; mirror the shipped OpenClaude file.** The single
  most important structural decision here is subclassing
  `aegis_swr.core.events.DomainEvent`, exactly as
  `src/aegis_swr/openclaude/events.py` shipped. The live `EventBus.publish`
  walks `type(event).__mro__` and delivers only to `DomainEvent` subclasses, so
  a plain dataclass reaches zero subscribers. Follow the shipped OpenClaude
  imports verbatim: `from datetime import UTC, datetime` and
  `datetime.now(UTC)` (not `datetime.utcnow()`, not `timezone.utc`).
- **`kw_only=True`** makes every construction keyword-only, so a `timestamp`
  with a default factory can sit last without forcing defaults on the preceding
  fields — which a positional frozen dataclass would reject.
- **`ClassVar[str] event_type`** is the filter discriminator
  (`event.event_type == "openhands.completed"`); it is not an instance field and
  never appears in a constructor call.
- **`OpenHandsCompleted` is the sole carrier of `token_estimate`** (C10). No
  action, observation, permission, or error event carries token data, keeping
  telemetry single-sourced. Its `usage_reported` flag records the C9 provenance
  (server-reported real usage vs. boundary estimate) without ever carrying the
  usage payload itself.
- **No `auth_failed` event.** Unlike Claude Code (C7), OpenHands has no
  Aegis-owned credential surface — the model credential is the operator's
  LiteLLM concern — so the C10 table marks `auth_failed` n/a. Do not add one.
- **Payload-free by construction.** `OpenHandsAction` carries `arg_count` (not
  the args); `OpenHandsObservation` carries `content_size` (not the content);
  `OpenHandsPermissionDenied` carries `denied_binary` (not the command line);
  `OpenHandsError` carries `code` (not the raw message). This is the C13 hard
  rule for this taxonomy, because these events observe sandbox output directly.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- All seven dataclasses are `frozen=True, kw_only=True` and **subclass** `aegis_swr.core.events.DomainEvent`.
- Every class has a `ClassVar[str] event_type` set to the exact `openhands.*` string from C10; every instance carries `run_id: str` and a timezone-aware UTC `timestamp: datetime`.
- **No field is typed `Any`**; all fields are `str`, `int`, `bool`, or `datetime`.
- No raw incident payload, action arguments, sandbox command line, or unredacted observation text on any field — only ids, counts, byte sizes, flags, and short status strings (C13).
- `token_estimate` appears on `OpenHandsCompleted` only (C10).
- No `auth_failed` event (n/a per C10).
- No OpenHands client library, `grpc`, `httpx`, or `websockets` import in this file (C3).
- `ruff` clean; every public class has an RST-style docstring.

## Success criteria

- [ ] All seven event classes exist with the fields and `event_type` strings above, matching the C10 OpenHands column exactly.
- [ ] Every class subclasses `aegis_swr.core.events.DomainEvent` and is delivered by a real `EventBus` publish/subscribe cycle (a subscriber on `DomainEvent` receives everything; a plain dataclass would not).
- [ ] Every class is `frozen=True` and constructs keyword-only (positional construction raises `TypeError`).
- [ ] Every instance carries `run_id: str` and a timezone-aware UTC `timestamp: datetime` (`tzinfo` is not `None`).
- [ ] `OpenHandsCompleted` is the only class exposing `token_estimate` (and it also carries `usage_reported`, `event_count`, and `truncated`).
- [ ] No `openhands.auth_failed` event exists (n/a per C10).
- [ ] No field annotation is `Any`; no field carries action arguments, observation content, a command line, or a raw error message (asserted by a unit test inspecting field names/types).
- [ ] `python -c "import aegis_swr.openhands.events"` succeeds with no OpenHands client library, `grpc`, `httpx`, or `websockets` pulled in.
- [ ] `ruff check src/ tests/` - clean.
