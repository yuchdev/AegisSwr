# 05 - Tests

**Parent task:** 06.0 Resource Exhaustion Agent
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04
**Blocks:** -

## Objective

Deliver the full test suite for `ResourceExhaustionAgent`. Coverage spans the
output schema (subtask 01), consensus weight normalization (subtask 02), the
agent's `run()` contract and deterministic pre-check (subtask 03), registry
wiring (subtask 04), and a mock-pipeline integration smoke test.

## Files

- **Modify** `tests/unit/test_schemas.py` - schema tests (specified in subtask 01).
- **Create** `tests/unit/test_resource_exhaustion_agent.py`
- **Modify** `tests/unit/test_consensus_weights.py` - weight normalization tests
  (one new parametrize case per affected fault class).
- **Modify** `tests/unit/test_agent_registry.py` - registry presence test.
- **Create** `tests/integration/test_resource_exhaustion_pipeline.py`

## Unit tests - `test_resource_exhaustion_agent.py`

### Pre-check tests

`test_precheck_detects_oom`
: Brief with `log_summary = "java.lang.OutOfMemoryError: GC overhead limit exceeded"`;
  assert `_extract_leak_indicators` returns a list with at least one entry
  containing `"out of memory"` (case-insensitive) or `"oom"`.

`test_precheck_detects_too_many_open_files`
: Brief with `raw_text_excerpt = "accept: too many open files (errno 24)"`;
  assert the returned list contains an entry referencing open files.

`test_precheck_detects_win32_resource_error`
: Brief with `raw_text_excerpt = "CreateHandle failed: ERROR_NO_SYSTEM_RESOURCES"`;
  assert the returned list is non-empty.

`test_precheck_detects_thread_exhaustion`
: Brief with `log_summary = "thread pool exhausted: limit 64 workers reached"`;
  assert the returned list contains an entry referencing thread exhaustion.

`test_precheck_detects_connection_pool`
: Brief with `log_summary = "ConnectionPool timeout: pool full (100/100)"`;
  assert the returned list is non-empty.

`test_precheck_empty_brief`
: Brief with no `log_summary` and no `raw_text_excerpt` (both absent or `None`);
  assert `_extract_leak_indicators` returns `[]` without raising.

`test_precheck_never_raises`
: Pass a malformed brief (e.g. `log_summary` is an `int`); assert no exception
  is raised; assert return value is a `list`.

`test_precheck_trims_long_indicators`
: Brief with a `log_summary` that contains a matching pattern embedded in 500
  characters of surrounding text; assert each returned indicator is at most 200
  characters.

### Agent `run()` tests (using `MockAIBackend`)

`test_run_returns_agent_turn`
: Construct `ResourceExhaustionAgent` with `MockAIBackend` returning a valid
  `ResourceExhaustionOutput` fixture (minimal: one hypothesis, `confidence_score
  = 0.72`, `exhausted_resource = "Win32 handle table"`, `leak_indicators = []`,
  `growth_trend = None`). Call `await agent.run(state)`. Assert the result is
  an `AgentTurn` with `agent == "Resource Exhaustion Agent"`.

`test_run_merges_precheck_into_turn`
: Use a brief whose `log_summary` triggers the OOM pre-check pattern. The
  `MockAIBackend` returns `ResourceExhaustionOutput` with an empty
  `leak_indicators`. Assert the returned `AgentTurn` has non-empty `hypotheses`
  and that the mock was called with a user message containing
  `"precheck_leak_indicators"`.

`test_run_includes_log_summary_in_context`
: Brief has `log_summary = "handle count: 62100 (threshold 60000)"`. Assert the
  JSON passed to `MockAIBackend.generate` contains the key `"log_summary"`.

`test_run_includes_log_summary_key_even_when_none`
: Brief has no `log_summary`. Assert the JSON passed to
  `MockAIBackend.generate` still contains the key `"log_summary"` with value
  `None`.

`test_run_incorporates_skeptic_corrections`
: State has `round_number = 2` and a `discussion_history` containing a Skeptic
  Agent turn for round 1 with `corrections = ["check handle leak in thread X"]`.
  Assert the user message passed to the AI contains
  `"skeptic_corrections_from_previous_round"`.

`test_run_confidence_propagated`
: `MockAIBackend` returns `confidence_score = 0.85`. Assert
  `agent_turn.confidence_score == 0.85`.

### Prompt content test

`test_system_prompt_contains_resource_keywords`
: Assert `agent.system_prompt` contains each of the following substrings:
  `"handle"`, `"file descriptor"` or `"fd"`, `"thread"`, `"memory"`,
  `"ResourceExhaustionOutput"` or `"resource_exhaustion"`, `"log_summary"`.

## Unit tests - consensus weight normalization

In `tests/unit/test_consensus_weights.py`, add a parametrized case for each
affected fault class using the data-driven `AgentWeightEntry.weights` map:

`test_resource_exhaustion_fault_class_weights_sum_to_one`
: Load the weight entry for `resource_exhaustion` fault class; assert
  `abs(sum(weights.values()) - 1.0) < 1e-4`.

`test_stack_overflow_weights_sum_to_one_after_resource_exhaustion`
: Load the weight entry for `stack_overflow`; assert the sum invariant.

`test_deadlock_weights_sum_to_one_after_resource_exhaustion`
: Load the weight entry for `deadlock`; assert the sum invariant.

## Unit tests - registry

In `tests/unit/test_agent_registry.py`, add:

`test_registry_contains_resource_exhaustion`
: Assert `"resource_exhaustion" in AGENT_REGISTRY` and
  `AGENT_REGISTRY["resource_exhaustion"] is ResourceExhaustionAgent`.

`test_panel_resource_exhaustion_fault_includes_specialist`
: Call `create_agent_panel(mock_backend, settings,
  fault_class=FaultClass.RESOURCE_EXHAUSTION)`. Assert the panel contains
  exactly one `ResourceExhaustionAgent` instance and that `skeptic` is last.

`test_panel_stack_overflow_includes_resource_exhaustion`
: Same pattern for `FaultClass.STACK_OVERFLOW`.

`test_panel_deadlock_includes_resource_exhaustion`
: Same pattern for `FaultClass.DEADLOCK`.

## Integration test - `test_resource_exhaustion_pipeline.py`

`test_resource_exhaustion_incident_includes_debate_turn`
: Build a minimal `InvestigationState` with `fault_class = "resource_exhaustion"`
  and a brief whose `log_summary` contains `"too many open files"`. Wire a panel
  that includes `ResourceExhaustionAgent` backed by `MockAIBackend`. Run one
  debate round (call `agent.run(state)` directly, not through the full
  orchestrator). Assert:
  - The returned `AgentTurn.agent == "Resource Exhaustion Agent"`.
  - `AgentTurn.confidence_score` is in `[0.0, 1.0]`.
  - The mock AI was invoked exactly once.
  - The user message the mock received contains both `"incident_brief"` and
    `"log_summary"` keys.

## Constraints

- All tests use `MockAIBackend`; no real AI calls.
- No real filesystem, DB, or network access in unit tests.
- `ruff check src/ tests/` - clean.
- `Optional[T]` in any new test helpers; never `T | None`.
- Tests must pass under `poetry run pytest tests/unit/ -q`.

## Success criteria

- [ ] All pre-check unit tests pass for the six signal patterns.
- [ ] All `run()` unit tests pass including context-key assertions.
- [ ] System prompt content test passes.
- [ ] Three consensus weight normalization tests pass.
- [ ] Three registry/panel tests pass.
- [ ] Integration smoke test passes.
- [ ] `ruff check src/ tests/` - clean across all new test files.
