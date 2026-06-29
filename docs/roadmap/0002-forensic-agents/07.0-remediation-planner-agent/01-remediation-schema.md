# 01 — RemediationPlan / RemediationStep schema

**Parent task:** 07.0 Remediation Planner Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0 (C6 — shared-contracts schema extension pattern)
**Blocks:** 02, 03

## Objective

Add `RemediationStep` and `RemediationPlan` Pydantic v2 models to
`src/aegis_swr/core/schemas.py`, and attach an optional `remediation_plan` field
to `RCAReport`. No agent or orchestrator code is touched in this subtask.

## Files

- **Modify** `src/aegis_swr/core/schemas.py`
- **Modify** `tests/unit/test_schemas.py`

## New models

### `RemediationStep`

Each field is designed to be compatible with the `/playbook-validate` skill's
per-step required set (see `/playbook-validate` SKILL.md §Checks).

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `order` | `int` | required | 1-based execution sequence; steps must be monotonically increasing. |
| `action` | `str` | required | Human-readable imperative description of the action. Matches `/playbook-validate` `description`+`action` semantics. |
| `idempotent` | `bool` | required | `True` if re-running the step produces no additional side-effects. Non-idempotent steps must supply a `rollback`. |
| `rollback` | `str` | required | Reversal instruction. For genuinely read-only steps use the literal string `"read-only: no state change"`. May not be an empty string. |
| `verification` | `Optional[str]` | `None` | Command or observable that confirms the step succeeded. |
| `risk` | `Optional[str]` | `None` | Free-text risk note (e.g. "restarts service, ~30 s downtime"). |
| `requires_human_approval` | `bool` | `False` | Set `True` for any production-affecting action. Checked against `AEGIS_PROD_CONFIRMED` at execution time. |

The field name `requires_human_approval` maps to `/playbook-validate`'s
`requires_authorisation` on serialization (see subtask 04 for the adapter spec).

### `RemediationPlan`

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `steps` | `list[RemediationStep]` | required | Ordered list; validator asserts `step.order` values are unique and form a contiguous 1-based sequence. |
| `summary` | `str` | required | One-paragraph plain-English description of the overall remediation approach. |
| `confidence` | `float` | required | Synthesizer's confidence that this plan addresses the confirmed root cause. Range `[0.0, 1.0]`. |
| `requires_human_approval` | `bool` | required | `True` if any step sets `requires_human_approval=True` OR `confidence` is below `0.70`. The orchestrator treats `True` as advisory-only. |

A Pydantic `model_validator(mode="after")` on `RemediationPlan` raises
`ValueError` if `steps` is empty, or if step `order` values are not a
contiguous sequence starting at 1.

### `RCAReport` extension

Add one field to the existing `RCAReport` model, after `hitl_request`:

```
remediation_plan: Optional[RemediationPlan] = None
```

This field is `None` on HITL outcomes (never populated by `_hitl_node`) and
`None` when synthesis is disabled via `AgentPanelSettings`.

## Constraints

- All optional fields use `Optional[T]` imported from `typing`; never `T | None`.
- `list[RemediationStep]` uses `Field(default_factory=list)` only where the
  field has a default; here `steps` is required (no default).
- `mypy --strict` must pass; the validator method is annotated
  `-> RemediationPlan` and uses `@model_validator(mode="after")`.
- The `rollback` field is a plain `str` (not `Optional[str]`) — every step must
  supply one. This is a deliberate design choice that prevents silent omissions.
- RST-style docstrings (`:ivar:`, `:type:`) on both new models and on the
  updated `RCAReport.remediation_plan` field, consistent with the surrounding
  schema file.

## Tests (`tests/unit/test_schemas.py`)

- `test_remediation_step_requires_rollback` — constructing `RemediationStep`
  with an empty `rollback` string raises `ValidationError`.
- `test_remediation_step_defaults` — `verification`, `risk` default to `None`;
  `requires_human_approval` defaults to `False`.
- `test_remediation_plan_rejects_empty_steps` — `RemediationPlan(steps=[],
  summary="x", confidence=0.9, requires_human_approval=False)` raises
  `ValidationError`.
- `test_remediation_plan_rejects_non_contiguous_order` — steps with `order`
  values `[1, 3]` raise `ValidationError`; values `[1, 2, 3]` pass.
- `test_remediation_plan_requires_human_approval_on_low_confidence` — a plan
  with `confidence=0.60` and no step-level approval flags still reports
  `requires_human_approval=True` after the model validator runs.
- `test_rca_report_remediation_plan_optional` — an `RCAReport` constructed
  without `remediation_plan` serializes without error and
  `report.remediation_plan is None`.
- `test_rca_report_with_remediation_plan_roundtrips` — a full `RCAReport` with
  a valid `RemediationPlan` survives `model_dump_json()` → `model_validate_json()`
  round-trip with identity on all `RemediationStep` fields.

## Success criteria

- [ ] `RemediationStep` and `RemediationPlan` are defined in `core/schemas.py`
      with all fields typed as specified above.
- [ ] `RCAReport.remediation_plan: Optional[RemediationPlan] = None` is present.
- [ ] The `RemediationPlan` model validator enforces non-empty steps and
      contiguous 1-based ordering.
- [ ] `confidence < 0.70` on `RemediationPlan` forces `requires_human_approval=True`.
- [ ] All seven unit tests above pass.
- [ ] `mypy --strict` clean on `core/schemas.py`.
- [ ] `ruff` clean (no unused imports introduced).
