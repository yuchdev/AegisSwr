# 01 - Default Panels & Weight Audit

**Parent task:** Task 08.0 - Panel Integration, Docs & Hardening
**Status:** ⬜ Not started
**Depends on:** Tasks 03.0, 04.0, 05.0, 06.0, 07.0 (all forensic + synthesis agents delivered)
**Blocks:** [02-config-and-examples.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/02-config-and-examples.md), [04-hardening-gates.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/04-hardening-gates.md)

---

## Objective

Ratify the exact per-fault consensus weight vectors for all ten `FaultClass`
values. Resolve any overlaps or unnormalized proposals left open by the
individual forensic tasks (03.0–06.0). Produce the canonical weight table that
all downstream artifacts (config, tests, docs) must reference. Assert in an
automated test that every fault class's debate weights sum to 1.0.

---

## Authority matrix recap

From [plan.md](/docs/roadmap/0002-forensic-agents/plan.md) §Specialist →
fault-class authority matrix. Base agents always participate; specialists join
for the fault classes marked with a check. The presence check column shows which
agents are voters for each class.

| FaultClass               | os_kernel | code_analyst | log_historian | skeptic | memory_forensics | concurrency_analyst | exploitability | resource_exhaustion |
|--------------------------|:---------:|:------------:|:-------------:|:-------:|:----------------:|:-------------------:|:--------------:|:-------------------:|
| memory_access_violation  | voter     | voter        | voter         | voter   | voter (primary)  |                     | voter          |                     |
| null_pointer_dereference | voter     | voter        | voter         | voter   | voter            |                     |                |                     |
| use_after_free           | voter     | voter        | voter         | voter   | voter (primary)  | voter               | voter          |                     |
| stack_overflow           | voter     | voter        | voter         | voter   |                  |                     | voter          | voter               |
| integer_divide_by_zero   | voter     | voter        | voter         | voter   |                  |                     |                |                     |
| deadlock                 | voter     | voter        | voter         | voter   |                  | voter (primary)     |                | voter               |
| assertion_failure        | voter     | voter        | voter         | voter   |                  | voter               |                |                     |
| resource_exhaustion      | voter     | voter        | voter         | voter   |                  |                     |                | voter (primary)     |
| unhandled_exception      | voter     | voter        | voter         | voter   |                  |                     |                |                     |
| unknown                  | voter     | voter        | voter         | voter   |                  |                     |                |                     |

`remediation_planner` is not a weighted voter and is absent from this table.

---

## Ratified weight table

The design principle for each fault class is:

- The specialist designated "primary" in the matrix receives the largest single
  weight share among all voters.
- `skeptic` always holds a reserved share of 0.10 in specialist panels (to
  preserve its veto function) and 0.15 in base-only panels (its 0001 default).
- `log_historian` is reduced from its 0001 share when a specialist with stronger
  signal joins the same panel, since the specialist subsumes part of its role.
- All weights within a row must sum to 1.0 (tolerance 1e-6).

### Fault classes with only base agents (back-compat rows)

These rows must reproduce the 0001 `AgentWeightsSettings` defaults exactly.

| FaultClass             | os_kernel | code_analyst | log_historian | skeptic | Sum  |
|------------------------|-----------|--------------|---------------|---------|------|
| integer_divide_by_zero | 0.35      | 0.40         | 0.10          | 0.15    | 1.00 |
| unhandled_exception    | 0.30      | 0.35         | 0.20          | 0.15    | 1.00 |
| unknown                | 0.30      | 0.35         | 0.20          | 0.15    | 1.00 |

### Fault classes with one specialist

| FaultClass             | os_kernel | code_analyst | log_historian | skeptic | memory_forensics | concurrency_analyst | exploitability | resource_exhaustion | Sum  |
|------------------------|-----------|--------------|---------------|---------|:----------------:|:-------------------:|:--------------:|:-------------------:|------|
| null_pointer_dereference | 0.25    | 0.25         | 0.10          | 0.10    | 0.30             |                     |                |                     | 1.00 |
| assertion_failure      | 0.20      | 0.30         | 0.10          | 0.10    |                  | 0.30                |                |                     | 1.00 |
| resource_exhaustion    | 0.20      | 0.20         | 0.15          | 0.10    |                  |                     |                | 0.35                | 1.00 |

### Fault classes with two specialists

| FaultClass    | os_kernel | code_analyst | log_historian | skeptic | memory_forensics | concurrency_analyst | exploitability | resource_exhaustion | Sum  |
|---------------|-----------|--------------|---------------|---------|:----------------:|:-------------------:|:--------------:|:-------------------:|------|
| stack_overflow | 0.25     | 0.20         | 0.10          | 0.10    |                  |                     | 0.20           | 0.15                | 1.00 |
| deadlock      | 0.15      | 0.15         | 0.10          | 0.10    |                  | 0.35                |                | 0.15                | 1.00 |

### Fault class with three specialists (use_after_free)

The three specialists present are `memory_forensics` (primary), `concurrency_analyst`,
and `exploitability`. Each base agent's share is reduced to make room; `skeptic`
is held at 0.10.

| FaultClass   | os_kernel | code_analyst | log_historian | skeptic | memory_forensics | concurrency_analyst | exploitability | Sum  |
|--------------|-----------|--------------|---------------|---------|:----------------:|:-------------------:|:--------------:|------|
| use_after_free | 0.15    | 0.15         | 0.10          | 0.10    | 0.25             | 0.15                | 0.10           | 1.00 |

### Fault class with memory_forensics + exploitability (memory_access_violation)

| FaultClass              | os_kernel | code_analyst | log_historian | skeptic | memory_forensics | exploitability | Sum  |
|-------------------------|-----------|--------------|---------------|---------|:----------------:|:--------------:|------|
| memory_access_violation | 0.20      | 0.20         | 0.10          | 0.10    | 0.25             | 0.15           | 1.00 |

---

## Default panel configuration

`AgentPanelSettings.per_fault_class` maps each `FaultClass` value to the ordered
list of `agent_key` strings that join the debate panel for that class. The
`default_panel` (used when no `fault_class` is supplied) preserves the 0001
legacy chain exactly.

```
default_panel:
  - os_kernel
  - code_analyst
  - log_historian
  - skeptic

per_fault_class:
  memory_access_violation:   [os_kernel, code_analyst, log_historian, memory_forensics, exploitability, skeptic]
  null_pointer_dereference:  [os_kernel, code_analyst, log_historian, memory_forensics, skeptic]
  use_after_free:            [os_kernel, code_analyst, log_historian, memory_forensics, concurrency_analyst, exploitability, skeptic]
  stack_overflow:            [os_kernel, code_analyst, log_historian, exploitability, resource_exhaustion, skeptic]
  integer_divide_by_zero:    [os_kernel, code_analyst, log_historian, skeptic]
  deadlock:                  [os_kernel, code_analyst, log_historian, concurrency_analyst, resource_exhaustion, skeptic]
  assertion_failure:         [os_kernel, code_analyst, log_historian, concurrency_analyst, skeptic]
  resource_exhaustion:       [os_kernel, code_analyst, log_historian, resource_exhaustion, skeptic]
  unhandled_exception:       [os_kernel, code_analyst, log_historian, skeptic]
  unknown:                   [os_kernel, code_analyst, log_historian, skeptic]
```

`skeptic` is always the final entry in every panel list (panel factory enforces
the order invariant from plan.md C4).

---

## Test specification

File: `tests/unit/test_weight_audit.py`

The implementer (`python-expert`) writes this test file. No product code is
changed - only the test is new.

### Test: `test_all_fault_class_weights_sum_to_one`

For every key in `AgentWeightsSettings.model_fields`, instantiate a default
`AgentWeightsSettings()`, call `for_fault_class(key)`, and assert that the sum
of all float values in the returned `AgentWeightEntry.weights` dict equals
1.0 within tolerance 1e-6. Parametrize over all ten keys.

### Test: `test_default_panel_is_legacy_four`

Instantiate `create_agent_panel(ai_backend=mock_backend, settings=Settings())`
with a default `Settings()` (no `fault_class` supplied). Assert that the
returned panel's `agent_key` list equals
`["os_kernel", "code_analyst", "log_historian", "skeptic"]` in that order.

### Test: `test_specialist_panel_includes_correct_agents`

Parametrize over a representative subset of fault classes. For each, call
`create_agent_panel(..., fault_class=FaultClass.<value>)` with a default
`Settings()` and assert the returned `agent_key` list matches the ratified
`per_fault_class` entry above. `skeptic` must be last in every case.

### Test: `test_back_compat_base_only_weights_unchanged`

For `integer_divide_by_zero`, `unhandled_exception`, and `unknown`, assert that
the weights from a default `AgentWeightsSettings()` equal the 0001 values
exactly (no floating-point tolerance needed for an exact equality check of
the hardcoded defaults).

---

## Success criteria

- [ ] All ten `FaultClass` weight rows are present in the ratified table above.
- [ ] Every row's weights sum to 1.0 (verified by `test_all_fault_class_weights_sum_to_one`).
- [ ] The three back-compat rows (`integer_divide_by_zero`, `unhandled_exception`,
      `unknown`) are byte-identical to the 0001 `AgentWeightsSettings` defaults.
- [ ] `test_default_panel_is_legacy_four` passes, confirming back-compat gate.
- [ ] `test_specialist_panel_includes_correct_agents` passes for all parametrized
      fault classes, with `skeptic` always last.
- [ ] No existing test is weakened or deleted to achieve a green run.
