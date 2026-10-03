# Task 03.0 — Harness Session Adapter & Factory

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §B.5 (`AIAPIBackend` → harness adapter; `HarnessSessionFactory`)
**Contracts:** C4 (`HarnessSession` + adapter), C5 (`HarnessSessionFactory`), C10
(token lineage), C7 (bounded-summary push), C12

## Scope

This task builds the seam that makes a harness the reasoning substrate of a
forensic role: a per-role `HarnessSession`, the `HarnessSessionBackend` adapter
that fulfils the retained `AIAPIBackend.generate(...)` contract by delegating to a
session, and the `HarnessSessionFactory` that binds a role (from the Task 01.0
binding table) to a concrete session with the right tool allowlist and trust tier.

The adapter is the **sole production** `AIAPIBackend` (C1): it keeps
`Orchestrator`/`resolve_panel` structurally intact — the change is *what the
backend is*, not *how the panel is driven*. It reuses the `_BaseAIBackend`
structured-output/retry seam (`backends/ai/base.py`) verbatim; only `_invoke()` is
supplied, delegating to the session and parsing its structured `CodeResult` back
into the role's `output_schema`.

> **Open item flagged for confirmation (session statefulness).** ADR §B.5 says
> `generate(system_prompt, messages, ...)` is fulfilled by a harness session, but
> a `CodeIntelBackend.delegate(task, ctx)` is one-shot. Whether a role's session
> is long-lived/stateful across debate rounds or re-delegated per turn is **not
> specified** by the ADR. Subtask 01 proposes **per-turn re-delegation** (bounded
> summary + a digest of prior turns folded into each task string) as the cheapest,
> most auditable option and flags the stateful alternative. Resolve with the user
> before implementing. See
> [status.md → Open items](/docs/roadmap/0007-harness-sole-llm-gateway/status.md).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`HarnessSession` per-role session object](01-harness-session.md) | ⬜ Not started | 02, 03 |
| 02 | [`HarnessSessionBackend` adapter](02-harness-session-backend.md) | ⬜ Not started | 04.0 |
| 03 | [`HarnessSessionFactory` (role binding + allowlist)](03-harness-session-factory.md) | ⬜ Not started | 04.0, 06.0 |
| 04 | [Structured-output parse + token lineage](04-structured-output-and-tokens.md) | ⬜ Not started | 04.0 |

Subtask 01 (the session) is the foundation; 02 (adapter) and 03 (factory) both
depend on it and may proceed in parallel; 04 (parse/token) depends on 02.

## Contracts touched

- **C4/C5** — defined and implemented here.
- **C10** — token lineage from `CodeResult.token_estimate` into `last_usage`.
- **C7** — the bounded pre-redacted summary is folded into the session task here;
  the redaction itself is Task 05.0's boundary (`mcp/redaction.py`), reused.
- **C9** — the factory selects at the role's trust tier; the tier machinery is
  Task 06.0, consumed here.

## Key constraints

- The `AIAPIBackend` ABC and `_BaseAIBackend` seam are unchanged (C1); the adapter
  only supplies `_invoke()`/`stream()`.
- Every session delegation has a timeout and a defined failure path; RAII via the
  caller's `AsyncExitStack` for any sidecar the session's backend owns (C12,
  mirrors 0005 C13).
- No raw incident payload, prompt, or response text reaches a log sink
  unredacted; `SensitiveFilter` on every sink (C12).

## Files created or modified by this task

```
src/aegis_swr/
├── harness/
│   └── session.py            ← NEW: HarnessSession + HarnessSessionFactory (C4, C5)
└── backends/ai/
    ├── __init__.py           ← modified: create_ai_backend constructs HarnessSessionBackend (C1)
    └── harness_adapter.py    ← NEW: HarnessSessionBackend (the sole production AIAPIBackend) (C4)

tests/unit/harness/test_session.py          ← NEW
tests/unit/backends/ai/test_harness_adapter.py ← NEW
```
