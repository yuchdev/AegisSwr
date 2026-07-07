# 04 - /playbook-validate alignment

**Parent task:** 07.0 Remediation Planner Agent
**State:** ⬜ Not started
**Depends on:** 01 (schema), 03 (wiring)
**Blocks:** 05

## Objective

Ensure that a `RemediationPlan` serialized to JSON can be passed to the
`/playbook-validate` skill and receive a `VALID` verdict. Specify the field
mapping, any adapter shim needed, and the safety rule for low-confidence plans.

## What `/playbook-validate` expects

The skill checks two levels of structure (from `SKILL.md §Checks`):

**Playbook-level required fields:** `id`, `name`, `trigger`, `steps`, `owner`, `severity`.

**Per-step required fields:** `id`, `description`, `action`, `idempotent` (bool),
`rollback`, `requires_authorisation` (bool), `timeout`.

`RemediationPlan` and `RemediationStep` do not carry all of these fields natively
(e.g. `id`, `trigger`, `owner`, `severity`, `timeout` are absent). An adapter
shim is required for validation runs; the shim is NOT part of the runtime schema.

## Field mapping

### Playbook-level

| `/playbook-validate` field | Source in `RemediationPlan` / `RCAReport` | Notes |
|---|---|---|
| `id` | `RCAReport.incident_id` (UUID, str-cast) | Injected by the adapter |
| `name` | `"Remediation for " + RCAReport.root_cause[:80]` | Adapter-constructed |
| `trigger` | `RCAReport.mode.value + "/" + fault_class` | Adapter-constructed from report context |
| `steps` | `RemediationPlan.steps` (see step mapping below) | Direct |
| `owner` | `"aegis_swr:remediation_planner"` | Constant injected by the adapter |
| `severity` | `ConfidenceLevel` mapped: HIGH→"P1", MEDIUM→"P2", LOW→"P3" | Adapter-constructed |

### Per-step

| `/playbook-validate` field | Source in `RemediationStep` | Notes |
|---|---|---|
| `id` | `f"step-{order:02d}"` | Adapter-derived from `order` |
| `description` | `action` | Direct (same content) |
| `action` | `action` | Direct |
| `idempotent` | `idempotent` | Direct |
| `rollback` | `rollback` | Direct |
| `requires_authorisation` | `requires_human_approval` | Renamed by adapter |
| `timeout` | `"300s"` | Constant default; overridable by adapter config |

The adapter shim is a standalone pure function
`remediation_plan_to_playbook_dict(plan: RemediationPlan, report: RCAReport) -> dict[str, Any]`
located in `src/aegis_swr/agents/synthesis/remediation_planner.py`. It is not
called at runtime during normal pipeline execution; it is called by the
`/playbook-validate` compatibility test (subtask 05) and can be called by
operators to export a plan for manual validation.

## Low-confidence advisory mode

When `RemediationPlan.confidence < 0.70` (the schema validator already sets
`requires_human_approval = True` in this case):

- The plan is **advisory only**. The orchestrator logs a `WARNING` (without
  plan content) and the API response marks `remediation_plan.requires_human_approval = True`.
- Downstream automation (runbook engines, CI gates) must check this flag before
  executing any step. Execution without human sign-off when the flag is `True`
  is a policy violation.
- The `/playbook-validate` skill will surface a **Warning** (non-blocking) for
  any step where `requires_authorisation` is `True` without `AEGIS_PROD_CONFIRMED`
  context.

## Incident-analyst safety rule

The following rule is cross-referenced from `.claude/CLAUDE.md §3` and must be
documented inline in the synthesis wiring code via a comment:

> Never auto-remediate without `AEGIS_PROD_CONFIRMED=1`. If
> `plan.requires_human_approval` is `True`, the plan is surfaced as advisory.
> No step in the plan is dispatched to any execution engine automatically.
> An operator must explicitly confirm with `AEGIS_PROD_CONFIRMED=1` before
> any production-affecting step runs.

This is an architectural invariant, not a runtime check. The orchestrator does
not dispatch plan steps - it only attaches the `RemediationPlan` to the
`RCAReport`. Execution is the caller's responsibility.

## Idempotency and rollback coverage rules

Consistent with the `/playbook-validate` checks:

- A step where `idempotent = False` and `rollback` equals
  `"read-only: no state change"` must be rejected by the schema validator as
  inconsistent. Specify this as a `model_validator` on `RemediationStep`.
- Any state-changing step (i.e. `idempotent = False` OR `requires_human_approval = True`)
  where `rollback` is the read-only sentinel string is a schema error.

Add this cross-field validator to `RemediationStep` (specify for `python-expert`):
validate in `mode="after"` that if `idempotent is False`, then
`rollback != "read-only: no state change"`.

## Constraints

- The adapter shim `remediation_plan_to_playbook_dict` must be pure (no I/O,
  no AI calls) and covered by a unit test in subtask 05.
- The adapter is only used for export/validation; it must never be called on
  the hot path of `_output_synthesizer_node`.
- `Optional[T]`, `replace_optional.py --check`, `ruff` clean on the adapter function.

## Success criteria

- [ ] `remediation_plan_to_playbook_dict(plan, report)` exists in
      `src/aegis_swr/agents/synthesis/remediation_planner.py` with the
      field mapping described above.
- [ ] A `RemediationStep` where `idempotent=False` and
      `rollback="read-only: no state change"` raises `ValidationError`.
- [ ] `RemediationPlan.requires_human_approval` is `True` whenever
      `confidence < 0.70`.
- [ ] The adapter output contains all playbook-level and step-level fields
      required by `/playbook-validate`.
- [ ] The incident-analyst safety rule comment appears in the orchestrator's
      `_output_synthesizer_node` method.
- [ ] `ruff` clean on `remediation_planner.py`.
