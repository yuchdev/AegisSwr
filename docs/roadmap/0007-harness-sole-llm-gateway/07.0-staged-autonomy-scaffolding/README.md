# Task 07.0 — Staged Autonomy Scaffolding (Stage 0/1)

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §E.9 (four opt-in autonomy stages, each gated; HITL and
escalation never removed)
**Contracts:** C11 (staged autonomy gate), C9 (execution tier = payload/sandbox)
**Gates:** `incident-analyst` (any stage transition is a lifecycle change);
`security-auditor` (any capability escalation; CRITICAL blocks merge).

## Scope

This task builds the **capability-tier gate** that turns Aegis from "always
read-only" into a staged, opt-in autonomy ramp — but only **Stage 0 (Analyse,
today's default)** and **Stage 1 (Suggest, candidate patch never executed)** are
built. Stage 2 gets an **extension-point stub only**; Stage 3 is a separate future
ADR and is **not** built (ADR §E.9, Future scope).

| Stage | Capability | Output | Gate (cumulative) | This task |
|-------|-----------|--------|-------------------|-----------|
| 0 Analyse | read-only | `RCAReport` / `HITLRequest` | baseline | **built (default)** |
| 1 Suggest | + write-to-sandbox-scratch | RCAReport **+ candidate patch/playbook** (never executed) | human review | **built (opt-in)** |
| 2 Execute-validated | execute in sandbox, non-prod | validated run + result | `/playbook-validate`; `HITLRequest`; `incident-analyst` | **stub only** |
| 3 Autonomous (allowlisted `FaultClass`) | execute for a narrow pre-approved allowlist | auto-remediation + audit | all of Stage 2 + standing HITL + `security-auditor` CRITICAL | **future ADR; not built** |

Non-negotiable across all stages: the `HITLRequest` escalation path stays reachable
at every tier (low consensus confidence still escalates to a human); any stage
transition is an `incident-analyst` lifecycle change; any capability escalation is
a `security-auditor` pass that CRITICAL-blocks merge; execution only ever happens
inside the sandboxed (OpenHands / payload-tier) runtime (C9). **No stage removes a
human's ability to intervene.**

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`AutonomyStage` gate + opt-in flags](01-autonomy-stage-gate.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [Stage 1 candidate-patch output on `RCAReport`](02-stage1-candidate-patch.md) | ⬜ Not started | 08.0 |
| 03 | [HITL preserved across stages + lifecycle hook](03-hitl-and-lifecycle.md) | ⬜ Not started | 08.0 |
| 04 | [Stage 2 extension-point stub (no execution)](04-stage2-extension-stub.md) | ⬜ Not started | - |

Subtask 01 (the gate) is the foundation; 02 (candidate patch), 03 (HITL/lifecycle),
and 04 (Stage 2 stub) depend on it.

## Contracts touched

- **C11** — defined and implemented here (Stage 0/1; Stage 2 stub).
- **C9** — Stage 1's sandbox-scratch write and any future execution are payload-tier
  / sandboxed only.

## Key constraints

- Stages 1–3 are **off by default**; each requires an explicit per-deployment
  opt-in flag; Stage 0 is the default (C11).
- Stage 1's candidate patch is **never executed** — it is attached to the report for
  human review only. No execution path is wired in this milestone (C11).
- Every stage keeps `HITLRequest` reachable; the existing
  `../CLAUDE.md`/`AEGIS_PROD_CONFIRMED` guard and the orchestrator's
  "never auto-remediate" rule (`core/orchestrator.py:_make_synthesizer_node`
  comment) are preserved and reinforced, not relaxed.

## Files created or modified by this task

```
src/aegis_swr/
├── core/
│   ├── autonomy.py        ← NEW: AutonomyStage enum + opt-in gate (C11)
│   ├── schemas.py         ← modified: optional candidate-patch field on RCAReport (Stage 1)
│   └── orchestrator.py    ← modified: synthesis path attaches a Stage-1 candidate patch when opted in
└── config/settings.py     ← modified: autonomy-stage opt-in flags (default Stage 0)

tests/unit/core/test_autonomy.py   ← NEW
```
