# Task 05.0 — Claude Code Events & Exceptions

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

This task delivers the two leaf modules of the Claude Code backend's
observability and failure surface, implementing milestone contract **C10** for
the `claude_code.*` family:

- `aegis_swr/claude_code/events.py` — the **eight** frozen event dataclasses of
  the C10 taxonomy (`ClaudeCodeSpawned`, `ClaudeCodeExited`,
  `ClaudeCodeToolCall`, `ClaudeCodeToolResult`, `ClaudeCodePermissionDenied`,
  `ClaudeCodeAuthFailed`, `ClaudeCodeCompleted`, `ClaudeCodeError`). Each
  **subclasses the live `aegis_swr.core.events.DomainEvent`** (the shape 0004
  actually shipped — not the stale plain-dataclass/`event_type`-string spec
  text), carries `run_id`, a UTC `timestamp`, and a `ClassVar[str] event_type`
  sentinel. `ClaudeCodeCompleted` alone carries the **real** `token_estimate`
  (C9); `ClaudeCodeAuthFailed` carries only a failure-reason status string and
  **never** any credential or token value (C7).
- `aegis_swr/claude_code/exceptions.py` — the **canonical** typed-error
  hierarchy: `ClaudeCodeConfigError` (settings-shape/ambiguity, `ValueError`
  base), `ClaudeCodeUnavailableError` (runtime capability failure, **including
  auth-probe failures**), and `PermissionDeniedError` (a non-allowlisted
  command; analogous to OpenClaude's `PermissionDeniedError`). This module is
  the canonical home for the errors that Tasks 02.0 / 03.0 / 04.0
  **forward-declared** as same-name placeholders; landing this task replaces
  those placeholders with re-export aliases so **no downstream import path
  changes** (exactly as Milestone 0004 Task 05.0 canonicalised
  `OpenClaudeConfigError`).

> This task is the events/exceptions **leaf** of the Claude Code track. It does
> not spawn a subprocess, parse NDJSON, resolve credentials, or run the auth
> probe — those belong to [Task 03.0](/docs/roadmap/0005-harness-backends/plan.md)
> (subprocess tool) and [Task 04.0](/docs/roadmap/0005-harness-backends/04.0-claude-code-auth/README.md)
> (authentication). It only supplies the event vocabulary those tasks *emit* and
> the exception types they *raise*.

## Why two subtasks, not three (contrast with Milestone 0004 Task 05.0)

Milestone 0004 Task 05.0 needed a **third** subtask ("EventBus registry
update") because its `openclaude.*` events were plain frozen dataclasses that
did **not** subclass any base event, so they had to be made discoverable and
distributable through a separate re-export/registration step. This milestone's
C10 events **subclass `DomainEvent` directly**, so they are distributed by the
existing `EventBus` for free (subscribing to `DomainEvent` receives every
subclass; subscribing to a concrete subclass receives that one via the bus's
MRO walk in `EventBus.publish`). No registration step and no change to
`aegis_swr/core/events.py` is required — the taxonomy is therefore split into
exactly two subtasks: events and exceptions.

## Forward-declared exceptions this task canonicalises

| Placeholder                  | Forward-declared in (task / file)                                                       | Canonicalised here                                     |
|------------------------------|-----------------------------------------------------------------------------------------|--------------------------------------------------------|
| `ClaudeCodeConfigError`      | Task 02.0 `claude_code/config.py` (settings validators)                                 | `exceptions.py`; `config.py` becomes a re-export alias |
| `ClaudeCodeUnavailableError` | Task 03.0 `claude_code/tool.py` / `process.py`; Task 04.0 `exceptions.py` (auth errors) | `exceptions.py`; upstream modules import from here     |
| `PermissionDeniedError`      | (new here — no earlier placeholder; mirrors OpenClaude)                                 | `exceptions.py`                                        |

The re-export-alias pattern is identical to how `openclaude/config.py`
re-exports `OpenClaudeConfigError` from `openclaude/exceptions.py`: the
placeholder body is deleted and replaced with
`from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError as ClaudeCodeConfigError`,
so `aegis_swr.claude_code.config.ClaudeCodeConfigError` keeps resolving to the
same object with no caller changes. The forward declaration and the canonical
definition are behaviourally identical (same base, same `__init__` signature,
same-formatted message), so every `except ClaudeCodeConfigError` site is
unaffected.

## Subtasks

| #  | Document                                                           | Status         | Blocks |
|----|--------------------------------------------------------------------|----------------|--------|
| 01 | [Eight `claude_code.*` event dataclasses](01-event-dataclasses.md) | ⬜ Not started | none   |
| 02 | [Canonical exception hierarchy](02-exception-types.md)             | ⬜ Not started | none   |

Both subtasks land in the same package and have no ordering dependency on each
other: `events.py` imports only `aegis_swr.core.events.DomainEvent`, and
`exceptions.py` is a pure leaf module. Neither subtask blocks any downstream
task — this task **canonicalises placeholders that upstream tasks already made
against**, so it is a leaf of the Claude Code track rather than a blocker (per
the milestone dependency graph, 05.0 hangs off 02.0 parallel to the
03.0 → 04.0 chain and blocks nothing).

## Dependencies

- **Depends on:** Task 02.0 (Claude Code Settings & Config) only — it needs the
  `claude_code/` package to exist and the placeholder `ClaudeCodeConfigError`
  signature to canonicalise. It is a **parallel sibling** of the
  03.0 → 04.0 chain (dependency graph) and shares no code with it beyond the
  exception types it here makes canonical.
- **Blocks:** none. Tasks 03.0 and 04.0 forward-declared their own placeholders
  and do not hard-block on this task; when 05.0 lands, they switch to importing
  from `exceptions.py` with no import-path change.

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- All event classes **subclass `aegis_swr.core.events.DomainEvent`**, are `frozen=True, kw_only=True`, and carry **no `Any` fields**; they round-trip through the existing `EventBus` without error (C10).
- Every event class carries `run_id: str`, a timezone-aware UTC `timestamp: datetime`, and a `ClassVar[str] event_type` set to the exact `claude_code.*` string from the C10 table.
- Event payloads never carry raw incident payload, tool arguments, unredacted response text, argv, or any credential/token value — only ids, counts, estimates, and short status strings (C7, C10, C13).
- `ClaudeCodeCompleted` is the **only** event carrying the token figure; it is never duplicated across events (C10). Its real `usage` breakdown (`input_tokens` / `output_tokens`) lives on that one event alongside the sum.
- `ClaudeCodeAuthFailed` carries only the failure reason status string (`"ambiguous_credential"` / `"no_stored_login"` / `"token_rejected"`) — never a credential, token, or credential-file path (C7, C10).
- Two distinct failure surfaces, never conflated (C7): `ClaudeCodeConfigError` (settings-construction, `ValueError` base) vs `ClaudeCodeUnavailableError` (runtime capability, including auth-probe failure). Neither subclasses the other.
- `events.py` imports **only** `aegis_swr.core.events` from the project (plus stdlib); `exceptions.py` is a pure leaf. Neither imports a sibling backend, `grpc`, or any client library (C3). A backend importing `aegis_swr.core` is permitted; the C3 boundary only forbids the reverse..

## Files created or modified by this task

```
src/aegis_swr/
└── claude_code/
    ├── events.py       ← NEW (subtask 01): eight claude_code.* DomainEvent subclasses; ClaudeCodeCompleted carries real tokens (C9/C10)
    ├── exceptions.py    ← subtask 02: CANONICAL ClaudeCodeConfigError, ClaudeCodeUnavailableError, PermissionDeniedError (replaces Task 02.0/03.0/04.0 placeholders)
    └── config.py        ← modified (subtask 02): placeholder ClaudeCodeConfigError body replaced with a re-export alias (no import-path change)

tests/unit/claude_code/
└── test_events.py      ← NEW (Task 11.0, incremental): event field/type/secrecy assertions + EventBus round-trip
```

> `tests/unit/claude_code/test_events.py` is authored under **Task 11.0**
> (incrementally, alongside this task, per the milestone's testing convention);
> it is listed here to name the coverage this task's behaviour requires.
