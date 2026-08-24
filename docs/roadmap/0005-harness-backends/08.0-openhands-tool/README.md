# Task 08.0 — OpenHands Tool Implementor

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started
**Category:** infrastructure

## Scope

Create `aegis_swr/openhands/tool.py` — `OpenHandsTool`, a concrete
`CodeIntelBackend` (contract C8) backed by the **long-lived OpenHands sidecar
over REST/WS** (Topology A-equivalent, sandboxed). It takes an open-ended task
string, delegates it to OpenHands, consumes the sandboxed runtime's
**Action/Observation event stream**, and reduces it to a single
`CodeResult`; there is no multi-tool selection on the Aegis SWR side. The class
holds an injected `OpenHandsClient` (task 07.0), `OpenHandsSettings` (task 06.0),
the `EventBus`, and a per-call `CallBudget`, and exposes a short `description`
advertising it as the Docker-sandboxed multi-file navigation backend.

`OpenHandsTool` is the **direct structural sibling of `OpenClaudeTool`**
(Milestone 0004, task 04.0) — same seam (`CodeIntelBackend.delegate(task, ctx)
→ CodeResult`), same ordered gates (budget pre-check → dry-run → stream), same
"never raises; every failure is a typed `CodeResult`" guarantee, same
100%-branch-coverage bar on the tool file — adapted for a REST/WS
Action/Observation stream instead of OpenClaude's gRPC frame stream, and for the
**dual token-accounting source** OpenHands allows (C9).

`delegate()` behaviour (finalised in subtask 02):

1. **Budget pre-check (C5-equivalent).** Pre-check the `CallBudget` against
   `max_response_tokens // 4` and return a **non-retriable** failure **without
   opening any connection** if insufficient.
2. **Dry-run (C8 item 6).** When `ctx.dry_run`, short-circuit to a `[dry-run]`
   zero-token `CodeResult` **before any network call** (no REST/WS traffic).
3. **Stream (subtask 01).** Otherwise call `client.stream(task, run_id)` and
   iterate the Action/Observation event stream — accumulating the assistant's
   text up to the terminal event, emitting `OpenHandsAction` /
   `OpenHandsObservation` per frame (C10), and emitting
   `OpenHandsPermissionDenied` + halting non-retriably for a surfaced
   non-allowlisted action.
4. **Token accounting (C9).** On the terminal event, resolve
   `CodeResult.token_estimate`: use the **server-reported real usage** when the
   stream carries it, else the boundary estimate `max(1, len(content) // 4)` —
   the same OpenClaude convention. The figure is charged to the budget **after**
   completion (never pre-charged) and surfaced through `CodeResult.token_estimate`
   (unchanged field name and `int` type — the C9 hard invariant).
5. **Truncation.** Accumulated content is clamped at the
   `max_response_tokens`-equivalent cap (if `OpenHandsSettings` defines one) with
   a `truncated` metadata flag; on server/transport error, emit
   `OpenHandsStreamError` and return a retriable failure for a transient status,
   non-retriable otherwise.

## Subtasks

| # | Name | Blocks | Status |
|---|------|--------|--------|
| 01 | [Tool skeleton + Action/Observation stream consumption](/docs/roadmap/0005-harness-backends/08.0-openhands-tool/01-stream-consumption.md) | 02 | ⬜ Not started |
| 02 | [`delegate()`: budget pre-check, token-estimate resolution, dry-run, truncation](/docs/roadmap/0005-harness-backends/08.0-openhands-tool/02-delegate-budget-tokens.md) | 09.0, 11.0 | ⬜ Not started |

## Key constraints

- Implements the unchanged `CodeIntelBackend` contract from
  `aegis_swr/code_intel/backend.py` (Milestone 0004); it imports nothing from
  `aegis_swr.code_intel` beyond that contract, and `aegis_swr/code_intel/` never
  imports it (C3). `code_intel/backend.py`, `agent.py`, `budget.py` stay
  byte-for-byte unchanged; `CodeResult.token_estimate` keeps its name and `int`
  type (C9).
- The tool **never imports the OpenHands HTTP/WS client library** — every event
  type it consumes comes from `aegis_swr/openhands/client.py` (task 07.0), the
  **sole** importer of that library (C3, C8 item 3). No sibling-backend import.
- Budget is charged **after** stream completion, never pre-charged; the pre-check
  reserves nothing. Failure paths (insufficient budget, dry-run, denial,
  transport error) charge **zero** tokens (C5-equivalent).
- `token_estimate` is the **server-reported real usage when present**, else the
  boundary estimate `max(1, len(content) // 4)` (C9); it is carried by exactly
  one event, `OpenHandsStreamCompleted` (`openhands.completed`), never
  duplicated (C10).
- `ctx.dry_run` returns `[dry-run]`/`0` **without any REST/WS call** (C8 item 6).
- **100% branch coverage required** on `tool.py` (task 11.0), mirroring the 0004
  `OpenClaudeTool` gate; no unhandled exception escapes `delegate()`.
- `from __future__ import annotations`; `Optional[T]` from `typing`, never
  `T | None` (C13); `ruff` and `python scripts/replace_optional.py --check`
  clean; no `Any` in any signature.
- Loguru with `SensitiveFilter` on every sink; **no** assistant text,
  observation output, action arguments, or incident payload ever reaches a log
  sink, exception message, or event payload — events carry counts and
  status/type strings only (C13).

## Files

```
src/aegis_swr/openhands/
├── tool.py        ← OpenHandsTool (this task): CodeIntelBackend impl,
│                     Action/Observation stream → CodeResult, budget, dry-run (C8, C9)
├── client.py      ← task 07.0: sole importer of the OpenHands client; yields the
│                     normalised OpenHands event stream this tool consumes
├── process.py     ← task 07.0: sidecar lifecycle (mirrors OpenClaudeProcess / 0004 C6)
├── config.py      ← task 06.0: OpenHandsSettings (server_url, runtime_mode,
│                     allowlist, timeouts, auto_start; max_response_tokens per C5)
├── events.py      ← task 09.0: openhands.* DomainEvent taxonomy (imported here)
└── exceptions.py  ← task 09.0: OpenHandsUnavailableError, … (imported here)

tests/unit/openhands/
└── test_tool.py   ← task 11.0: per-branch delegate() coverage, no-network-on-dry-run,
                      token-estimate-source matrix, no-secret-in-events assertions
```
