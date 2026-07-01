# Task 07.0 - Remediation Planner Agent

**Parent milestone:** [Milestone 0002 - Forensic Agents](/docs/roadmap/0002-forensic-agents/plan.md)
**Status:** ⬜ Not started
**Depends on:** Task 02.0 (Extensible Panel - registry, `AgentPanelSettings`, dynamic orchestrator)
**Blocks:** Task 08.0 (Panel Integration, Docs & Hardening)

## Scope

Implement `RemediationPlannerAgent` - the sole **synthesis-tier** agent introduced
by Milestone 0002. Its purpose is to turn a confirmed, converged `RCAReport` into
an ordered, idempotent, rollback-covered remediation playbook compatible with the
`/playbook-validate` skill.

This agent is architecturally distinct from every forensic specialist in this milestone:

- It is **not a debate voter**. It does not appear in `create_agent_panel()` and
  carries no consensus weight entry in `AgentWeightEntry.weights`.
- It runs **exactly once**, inside `_output_synthesizer_node`, after the skeptic
  has confirmed convergence.
- It is **skipped entirely on the HITL path**. When the debate deadlocks and the
  orchestrator routes to `_hitl_node`, `RemediationPlannerAgent` is never called.
  Escalate to a human; do not auto-remediate an inconclusive investigation.
- It is controlled by `AgentPanelSettings.enabled_synthesis` (a new list field),
  not by the per-fault debate panel list.

Module: `src/aegis_swr/agents/synthesis/remediation_planner.py`
Class: `RemediationPlannerAgent`
`agent_key = "remediation_planner"` | `category = "synthesis"` | `display_name = "Remediation Planner Agent"`

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [RemediationPlan / RemediationStep schema](01-remediation-schema.md) | ⬜ Not started | 02, 03 |
| 02 | [Agent implementation](02-agent-implementation.md) | ⬜ Not started | 03 |
| 03 | [Synthesis-tier wiring](03-synthesis-wiring.md) | ⬜ Not started | 05 |
| 04 | [/playbook-validate alignment](04-playbook-validate-alignment.md) | ⬜ Not started | 05 |
| 05 | [Tests](05-tests.md) | ⬜ Not started | - |

Subtasks 01 → 02 → 03 are strictly sequential. Subtask 04 may proceed in
parallel with 03 once 01 is done. Subtask 05 depends on 01–04.

## Key constraints

- **Synthesis-tier, not a voter.** `AGENT_REGISTRY` registers it with
  `category = "synthesis"`; `create_agent_panel` filters it out by category.
- **Skipped on HITL.** The orchestrator's `_hitl_node` must not instantiate or
  call this agent. `RCAReport.remediation_plan` remains `None` on a HITL outcome.
- **Idempotency and rollback are non-negotiable.** The system prompt must
  instruct the model that every step requires an `idempotent` flag and a
  `rollback` string. The schema validator rejects steps that omit either.
- **`AEGIS_PROD_CONFIRMED` guard.** Any plan step flagged as production-affecting
  must carry `requires_human_approval = True`; the incident-analyst safety rule
  (never auto-remediate without `AEGIS_PROD_CONFIRMED=1`) is documented in
  subtask 04 and enforced in the orchestrator wiring.
- **`Optional[T]` everywhere**, never `T | None`. `mypy --strict` and `ruff`
  must both pass on every deliverable.
- **No raw incident payload in logs.** Agent receives the summarized, PII-scrubbed
  `RCAReport` fields (root cause, faulting module, hypotheses); never the raw
  stack or dump text.
