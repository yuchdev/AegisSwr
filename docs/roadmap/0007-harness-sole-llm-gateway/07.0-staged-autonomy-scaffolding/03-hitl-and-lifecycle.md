# 03 — HITL preserved across stages + lifecycle hook

**Parent task:** 07.0 Staged Autonomy Scaffolding (Stage 0/1)
**State:** ⬜ Not started
**Depends on:** 01 (`AutonomyGate`)
**Blocks:** Task 08.0
**Contracts:** C11

## Objective

Guarantee — as a tested invariant — that the `HITLRequest` escalation path stays
reachable at **every** autonomy stage, and record the `incident-analyst` lifecycle
hook that any stage transition must pass.

## Scope

- Assert the existing HITL escalation (`core/orchestrator.py:_make_hitl_node` /
  `_hitl_node`, reached when the panel cannot converge within the debate limit) is
  **unconditional on autonomy stage** — raising the stage never removes or bypasses
  it. A low-consensus run at Stage 1 still produces a `HITLRequest`, exactly as at
  Stage 0.
- Add an `incident-analyst` lifecycle checkpoint: changing the active
  `AutonomyStage` is a lifecycle change that must be recorded (a settings-level
  audit note + a docstring/doc pointer) and reviewed by `incident-analyst` before a
  deployment runs above Stage 0. This milestone does not build an approval workflow
  — it records the obligation and exposes the stage on the report/audit trail so the
  review has something to check.
- Any capability escalation (Stage 1 scratch-write, and the future Stage 2/3
  execution) is marked as a `security-auditor` gate in the stage docstrings and the
  Task 10.0 doc; a CRITICAL finding blocks merge.
- Human-intervention guarantee (C11): no stage removes the operator's ability to
  intervene — the HITL path, the `AEGIS_PROD_CONFIRMED` guard, and the
  never-auto-remediate rule all remain in force.

## Acceptance criteria

- [ ] A low-consensus run produces a `HITLRequest` at Stage 0 **and** Stage 1
      (HITL reachable at every stage) (C11).
- [ ] The HITL node logic is unchanged and unconditional on autonomy stage.
- [ ] The active `AutonomyStage` is recorded on the audit trail / report so an
      `incident-analyst` review can check it; the lifecycle obligation is documented.
- [ ] Stage-1+ capability is marked a `security-auditor` gate in docstrings/docs.
- [ ] `ruff` clean.
