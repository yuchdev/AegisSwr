# 05 - Tests

**Parent task:** 07.0 Remediation Planner Agent
**State:** ⬜ Not started
**Depends on:** 01 (schema), 02 (agent), 03 (wiring), 04 (alignment)
**Blocks:** -

## Objective

Deliver full test coverage for the remediation schema, agent, synthesis wiring,
and `/playbook-validate` adapter. All tests in `tests/unit/` must run in CI
without external services. Integration tests use mocked AI and storage backends.

## Unit tests

### Schema tests (`tests/unit/test_schemas.py`)

These are specified in subtask 01 and must pass here as the primary gate.
Summarized for completeness:

- `test_remediation_step_requires_rollback`
- `test_remediation_step_defaults`
- `test_remediation_plan_rejects_empty_steps`
- `test_remediation_plan_rejects_non_contiguous_order`
- `test_remediation_plan_requires_human_approval_on_low_confidence`
- `test_rca_report_remediation_plan_optional`
- `test_rca_report_with_remediation_plan_roundtrips`
- `test_remediation_step_rejects_readonly_rollback_when_not_idempotent` - a
  `RemediationStep` with `idempotent=False` and
  `rollback="read-only: no state change"` raises `ValidationError`.

### Agent unit tests (`tests/unit/test_remediation_planner.py`)

- `test_run_raises_not_implemented` - calling `agent.run(state)` on a
  `RemediationPlannerAgent` raises `NotImplementedError`.
- `test_run_synthesis_returns_plan_with_all_steps_idempotent` - with a mocked
  `AIAPIBackend.generate` returning a `RemediationPlan` where every step has
  `idempotent=True` and a non-empty `rollback`, the method returns
  `(AgentTurn, RemediationPlan)` with no validation errors.
- `test_run_synthesis_plan_has_rollback_on_every_step` - assert that in the
  returned plan, `all(step.rollback for step in plan.steps)` is `True`.
- `test_run_synthesis_turn_has_synthesis_agent_label` - the returned `AgentTurn`
  has `agent == "Remediation Planner Agent"` and `turn_number == 0`.
- `test_run_synthesis_does_not_include_raw_payload` - mock the `generate` call
  to capture the `messages` argument; assert that none of the message content
  strings contain the sentinel raw payload text (`"raw_text_excerpt"` key or
  its value). Use a `RCAReport` fixture where `raw_text_excerpt` is a distinct
  string.
- `test_class_vars` - `RemediationPlannerAgent.agent_key == "remediation_planner"`,
  `category == "synthesis"`, `display_name == "Remediation Planner Agent"`.

### Playbook adapter unit tests (`tests/unit/test_remediation_planner.py`)

- `test_playbook_adapter_contains_required_fields` - call
  `remediation_plan_to_playbook_dict(plan, report)` with a minimal valid plan
  and report; assert all of `id`, `name`, `trigger`, `steps`, `owner`,
  `severity` are present in the result dict.
- `test_playbook_adapter_step_fields` - each step dict in the output contains
  `id`, `description`, `action`, `idempotent`, `rollback`,
  `requires_authorisation`, `timeout`.
- `test_playbook_adapter_requires_authorisation_maps_correctly` - a
  `RemediationStep` with `requires_human_approval=True` produces a step dict
  where `requires_authorisation=True`.
- `test_playbook_adapter_step_id_format` - step with `order=3` produces
  `step["id"] == "step-03"`.

## Mock pipeline tests (`tests/unit/test_orchestrator.py`)

- `test_output_synthesizer_attaches_remediation_plan` - with a converged
  `InvestigationState`, a mocked `RemediationPlannerAgent.run_synthesis`
  returning a valid `(AgentTurn, RemediationPlan)`, and
  `enabled_synthesis=["remediation_planner"]` in settings, assert that
  `state["result"]["remediation_plan"]` is not `None` after
  `_output_synthesizer_node` runs.
- `test_output_synthesizer_synthesis_disabled_leaves_plan_none` - with
  `enabled_synthesis=[]`, the synthesizer node completes without calling
  `run_synthesis`, and `state["result"]["remediation_plan"]` is `None`.
- `test_output_synthesizer_synthesis_exception_is_soft_failure` - when
  `run_synthesis` raises an exception, the node does not propagate it;
  `state["result"]["remediation_plan"]` is `None` and the RCA report is
  still returned.
- `test_hitl_node_never_calls_synthesis` - run `_hitl_node` with a deadlocked
  state; assert `RemediationPlannerAgent.run_synthesis` is never called (use
  `unittest.mock.patch` to intercept).
- `test_agent_spoke_emitted_after_synthesis` - after a successful synthesis
  call, the `EventBus` receives an `AgentSpoke` event whose `agent` field is
  `"Remediation Planner Agent"`.

## Integration tests (`tests/integration/test_remediation_planner_integration.py`)

All integration tests use mocked AI and storage backends (no live LLM or DB).

- `test_converged_investigation_yields_remediation_plan` - run a full
  orchestrator pipeline with mocked agents that converge in round 1; assert
  the returned `RCAReport.remediation_plan` is not `None`, has at least one
  step, and all steps have non-empty `rollback`.
- `test_hitl_investigation_yields_no_remediation_plan` - configure the
  orchestrator to exhaust `max_debate_rounds=1` without convergence; assert
  the returned `RCAReport.remediation_plan is None` and
  `RCAReport.hitl_request is not None`.
- `test_playbook_validate_compatible_output` - on a converged investigation,
  call `remediation_plan_to_playbook_dict(report.remediation_plan, report)` and
  assert every `/playbook-validate` required field is present at both playbook
  and step levels. This is a structural compatibility test, not a live skill
  invocation.

## Constraints

- All unit tests must run without a network connection and without any AI
  backend API key configured.
- Mock `AIAPIBackend.generate` using `unittest.mock.AsyncMock` returning a
  pre-built `RemediationPlan` fixture.
- Test fixtures for `RemediationPlan` and `RCAReport` must use `Optional[T]`
  types consistently (no `T | None` in test helper code).
- `mypy --strict` clean on all new test files (test files are included in
  `mypy` scope per project convention).
- `ruff` clean; no unused imports.

## Success criteria

- [ ] All eight schema unit tests pass.
- [ ] All six agent unit tests pass.
- [ ] All four playbook adapter unit tests pass.
- [ ] All five mock pipeline tests pass.
- [ ] All three integration tests pass.
- [ ] `test_hitl_node_never_calls_synthesis` confirms zero calls to
      `run_synthesis` on the HITL path.
- [ ] `test_converged_investigation_yields_remediation_plan` confirms
      `remediation_plan is not None` and `all(step.rollback for step in plan.steps)`.
- [ ] `test_hitl_investigation_yields_no_remediation_plan` confirms
      `remediation_plan is None`.
- [ ] `mypy --strict` and `ruff` clean across all new test files.
