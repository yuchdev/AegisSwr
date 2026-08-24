# Task 09.0 — OpenHands Events & Exceptions

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

Create `aegis_swr/openhands/events.py` with the seven `frozen=True, kw_only=True`
event dataclasses of the OpenHands column of contract [C10](/docs/roadmap/0005-harness-backends/plan.md#c10--per-backend-event-taxonomy)
(`OpenHandsConnected`, `OpenHandsDisconnected`, `OpenHandsAction`,
`OpenHandsObservation`, `OpenHandsPermissionDenied`, `OpenHandsCompleted`,
`OpenHandsError`). Every event **subclasses the live**
`aegis_swr.core.events.DomainEvent` (the shape Milestone 0004 actually shipped —
see `src/aegis_swr/openclaude/events.py`, **not** the stale plain-dataclass draft
text of 0004's task 05.0 README), carries `run_id`, a UTC `timestamp`, and a
`ClassVar[str]` `event_type` sentinel. `OpenHandsCompleted` is the **only** event
carrying the `token_estimate` figure; it is never duplicated across events (C10).
OpenHands has **no** `auth_failed` event — that concept is n/a per the C10 table
(unlike Claude Code, OpenHands treats its model credential entirely as the
operator's own LiteLLM concern).

Create `aegis_swr/openhands/exceptions.py` as the **canonical home** for the
OpenHands exception hierarchy: `OpenHandsConfigError` (invalid
`OpenHandsSettings`, raised by `config.py`), `OpenHandsUnavailableError`
(unreachable sidecar / failed health-check, raised by `process.py` and
`client.py`), and a `PermissionDeniedError` analogous to OpenClaude's (a
non-allowlisted sandbox action). Landing this file **replaces any placeholder
forward-declared in Tasks 06.0/07.0/08.0 with a re-export alias — no downstream
import-path changes** (mirrors the 0004 task 05.0 "canonicalise the forward
declaration" pattern exactly).

Depends on **Task 06.0 only** — it is a parallel sibling of the 07.0 → 08.0
chain within the OpenHands track and can be written alongside 06.0 so that 07.0
and 08.0 have the canonical types available to raise and emit.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [Seven OpenHands event dataclasses](01-event-dataclasses.md) | ⬜ Not started | 08.0 |
| 02 | [Canonical OpenHands exception hierarchy](02-exception-types.md) | ⬜ Not started | 07.0, 08.0 |

## Key constraints

- All seven event dataclasses are `frozen=True, kw_only=True`, **subclass**
  `aegis_swr.core.events.DomainEvent`, and carry **no `Any` fields**; they
  round-trip through the live `EventBus` (which dispatches by walking
  `type(event).__mro__` over `DomainEvent` subclasses) without error.
- Every event carries `run_id: str`, a timezone-aware UTC `timestamp: datetime`,
  and a `ClassVar[str] event_type` set to the exact `openhands.*` string from
  C10.
- Event payloads never carry raw incident payload, tool arguments, sandbox
  command lines, or unredacted observation text (C13) — only ids, counts, byte
  sizes, boolean flags, and short status strings.
- `OpenHandsCompleted` is the only event carrying `token_estimate`; it is not
  duplicated across events (C10). Its provenance flag distinguishes a
  server-reported real usage figure from the boundary estimate (C9).
- No `auth_failed` event exists for OpenHands (n/a per C10).
- `OpenHandsConfigError`, `OpenHandsUnavailableError`, and `PermissionDeniedError`
  form three independent hierarchies — none subclasses another. No exception
  message ever contains dump/log/stack/observation/credential text (C13).
- `exceptions.py` and `events.py` import **no** OpenHands client library, `grpc`,
  `httpx`/`websockets`, or `pydantic` — they are leaf modules the rest of the
  package imports from without a cycle (C3).
- `from __future__ import annotations` in both files; `Optional[T]` from `typing`,
  never `T | None`; `ruff` and `python scripts/replace_optional.py --check` clean;
  every public class has an RST-style docstring.

## Files

```
src/aegis_swr/openhands/
├── events.py        ← subtask 01: seven openhands.* DomainEvent subclasses (C10)
└── exceptions.py    ← subtask 02: OpenHandsConfigError, OpenHandsUnavailableError,
                        PermissionDeniedError (canonical; replaces 06.0/07.0/08.0
                        forward declarations via re-export, no import-path change)
```

> The package `aegis_swr/openhands/__init__.py` re-export of these payload-free,
> client-free events and exceptions (mirroring
> `aegis_swr/openclaude/__init__.py`) is owned by the OpenHands track's package
> scaffolding (Task 06.0/07.0) and is **not** duplicated here; this task only
> defines the two leaf modules. `OpenHandsTool`, `OpenHandsProcess`, and
> `OpenHandsClient` must never be re-exported at package-import time (C3).
