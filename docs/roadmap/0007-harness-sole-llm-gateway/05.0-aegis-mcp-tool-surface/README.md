# Task 05.0 — Aegis MCP Tool Surface (redaction chokepoint)

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §C.6 (hybrid push + Aegis-as-MCP-tool-surface), §C.7 (the
MCP tool surface is the single redaction chokepoint)
**Contracts:** C7, C8, C13
**Gate:** `security-auditor` — this is a net-new attack surface; a CRITICAL finding
blocks merge (ADR Links).

## Scope

This task stands up `aegis_swr/mcp/`: Aegis exposing itself as an MCP tool surface
(the "Topology C" inversion from
[Milestone 0004 plan.md](/docs/roadmap/0004-code-intelligence/plan.md#topology-c--openclaude-as-the-primary-orchestrator-inverted))
so a harness session can **pull deeper incident detail on demand**, and — decisively
— making this surface the **single redaction chokepoint**: no incident byte crosses
into a harness except through the pushed pre-redacted summary (C7, Task 04.0) or an
MCP tool response redacted at the tool boundary.

Four tools:

- `get_similar_incidents` — served by `core/incident_similarity.py`; returns
  **redacted structured hits** (`HistoryMatch.as_dict()`-shaped), never raw prior
  payloads. This is the user's "load similar issues into context memory" phrase.
- `get_event_log` — redacted structured event log for a run.
- `get_evidence_slice` — a bounded, redacted slice of evidence text on demand.
- `analyze_incident` — a **payload-tier** tool (must run on a sandboxed backend);
  see subtask 04 for the recursion-risk gate.

Every tool response is redacted at `mcp/redaction.py`, `SensitiveFilter`-covered,
and authorization-checked. Raw dump/log/stack text is never forwarded unredacted,
never logged, never persisted unredacted.

> **Open items flagged (status.md):** the concrete **authorization model** (C8) and
> the **`analyze_incident` recursion posture** (single-process regress risk) are
> underspecified by ADR 0006; subtasks 04/05 propose a scheme and flag both for the
> `security-auditor` gate rather than guessing silently.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [MCP server scaffolding + tool registration](01-mcp-server-scaffolding.md) | ⬜ Not started | 02, 03, 04, 05 |
| 02 | [`get_similar_incidents` (incident_similarity)](02-get-similar-incidents.md) | ⬜ Not started | 05 |
| 03 | [`get_event_log` + `get_evidence_slice`](03-event-log-evidence-slice.md) | ⬜ Not started | 05 |
| 04 | [`analyze_incident` (payload tier + recursion gate)](04-analyze-incident.md) | ⬜ Not started | 05 |
| 05 | [Redaction boundary + authorization (security gate)](05-redaction-and-authorization.md) | ⬜ Not started | - |

Subtask 01 (scaffolding) is the foundation; 02/03/04 (the tools) depend on it and
may proceed in parallel; 05 (the redaction + authz boundary) is the gate every tool
routes through and is co-designed with them.

## Contracts touched

- **C7** — the pull half of the hybrid context model; the push half is Task 04.0.
- **C8** — the single redaction chokepoint is defined and implemented here.
- **C13** — MCP isolation: `core/`, `views/`, `code_intel/` import no `mcp` server
  module; `mcp/redaction.py` is the sole egress for incident content into a tool
  response.

## Key constraints

- No incident byte reaches a tool response unredacted; `SensitiveFilter` on every
  sink; authz-checked (C8).
- Untrusted payload text must never reach a shell, SQL string, `eval`, or an AI
  prompt without sanitisation/parameterisation (`../CLAUDE.md` §3).
- `core/incident_similarity.py` is **unchanged** — the tool reads it, does not
  modify it.

## Files created or modified by this task

```
src/aegis_swr/mcp/            ← NEW PACKAGE
├── __init__.py
├── server.py                 ← MCP server scaffolding + tool registration; SensitiveFilter (subtask 01)
├── tools.py                  ← the four tools (subtasks 02–04)
└── redaction.py              ← the single redaction + authorization boundary (subtask 05)

tests/unit/mcp/
├── test_tools.py             ← NEW
└── test_redaction.py         ← NEW (hostile-fixture redaction assertions)

docs/security/2026-10-DD-aegis-mcp-tool-surface.md   ← NEW: security-auditor threat model
```
