# Task 04.0 — Panel Rewiring onto Per-Role Sessions

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §B.4 (one harness session per forensic role; arbitration
stays deterministic and Aegis-side)
**Contracts:** C6 (deterministic Aegis-side arbitration, unchanged), C5, C7, C10

## Scope

This task rewires the forensic panel so each role is driven by its **own** harness
session instead of one shared `AIAPIBackend` fanned to every agent — while
proving that the LangGraph, ADR 0002 weights, the one-arbiter invariant, and the
deterministic `consensus.py` output are **unchanged**.

Today `Orchestrator.__init__` takes one shared `ai_backend`
(`core/orchestrator.py:81`) and `resolve_panel` (`agents/panel.py:39`) hands that
same instance to every agent. After this task:

- `resolve_panel` accepts a `HarnessSessionFactory` (Task 03.0) and injects a
  **per-role** `HarnessSessionBackend` into each agent's constructor, keyed by
  `agent_key`/role.
- `Orchestrator` is constructed with the factory at the composition root; its
  LangGraph construction, `AgentTurn`/event accounting, `_fold_turn` token
  tracking, and the exactly-one-ARBITER enforcement are **structurally intact**.
- `core/consensus.py` is **not touched**: it stays a deterministic Aegis-side
  weighted vote over the structured per-agent Pydantic output (`Hypothesis`/
  `SkepticVerdict`). Arbitration is **never** moved into a harness.
- The hybrid context model (C7): a bounded, pre-redacted incident summary (the
  `IncidentBrief` + top-k `HistoryAnalysis.as_context()` hits) is seeded into the
  LangGraph state / each role's first task, with deeper detail pulled on demand via
  the MCP surface (Task 05.0).

The defining acceptance gate is **parity**: run the panel under a
`ScriptedAIBackend`-equivalent harness double producing identical structured
output and prove weights, one-arbiter, and `consensus.py` output are byte-for-byte
unchanged (subtask 03, Task 08.0).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`resolve_panel` per-role session injection](01-resolve-panel-per-role.md) | ⬜ Not started | 02, 03 |
| 02 | [`Orchestrator` composition-root wiring](02-orchestrator-wiring.md) | ⬜ Not started | 03, 07.0 |
| 03 | [Consensus/weight/one-arbiter parity proof](03-consensus-parity-proof.md) | ⬜ Not started | 08.0 |
| 04 | [Hybrid context seeding + token lineage](04-hybrid-context-and-tokens.md) | ⬜ Not started | 05.0 |

Subtask 01 (panel injection) is the foundation; 02 (orchestrator) and 03 (parity)
depend on it; 04 (context seeding) depends on 01 and dovetails with Task 05.0's
redaction boundary.

## Contracts touched

- **C6** — the invariant this task must preserve; the parity proof lives in
  subtask 03 and Task 08.0.
- **C5** — the factory is consumed here.
- **C7** — the bounded push is seeded here (redaction reused from Task 05.0).
- **C10** — per-role token lineage folds into the existing `token_tracker`.

## Key constraints

- `core/consensus.py` is byte-for-byte unchanged (C6).
- `resolve_consensus_weights` (`agents/panel.py:89`) and `_order_panel`,
  `_arbiter_updates`, `_make_router` in the orchestrator are unchanged in logic —
  only the *source of each agent's backend* changes (C6).
- No raw payload/prompt/response in any log sink (C12).

## Files created or modified by this task

```
src/aegis_swr/
├── agents/panel.py        ← modified: resolve_panel injects a per-role session (C6)
├── core/orchestrator.py   ← modified: construct with HarnessSessionFactory; graph UNCHANGED (C6)
└── core/consensus.py      ← UNCHANGED (asserted, not edited)

tests/unit/agents/test_panel_parity.py   ← NEW (subtask 03)
tests/unit/core/test_orchestrator_sessions.py ← NEW (subtask 02)
```
