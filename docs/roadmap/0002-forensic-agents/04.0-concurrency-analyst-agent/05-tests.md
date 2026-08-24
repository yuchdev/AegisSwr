# 05 - Tests

**Parent task:** 04.0 Concurrency Analyst Agent
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04
**Blocks:** -

## Objective

Provide complete unit, mock-pipeline, and integration test coverage for the
`ConcurrencyAnalystAgent` and its `ConcurrencyAnalystOutput` schema. Every
external dependency (AI backend, orchestrator) is mocked; no real LLM or
network calls are made in this suite.

## Test files

- **Create** `tests/unit/test_concurrency_analyst.py`
- **Extend** `tests/unit/test_schemas.py` (schema tests from subtask 01 live here)
- **Extend** `tests/unit/test_agent_registry.py` (registry tests from subtask 04)
- **Create** `tests/integration/test_concurrency_analyst_pipeline.py`

## Unit tests - `test_concurrency_analyst.py`

### Schema request via `MockAIBackend`

- `test_run_returns_agent_turn` - call `ConcurrencyAnalystAgent.run(state)`
  with a `MockAIBackend` that returns a valid `ConcurrencyAnalystOutput`
  fixture; assert the result is an `AgentTurn` with
  `agent == "Concurrency Analyst Agent"` and `confidence_score` matching the
  fixture.

- `test_run_builds_hypotheses_from_output` - the returned `AgentTurn.hypotheses`
  list has the same length and `root_cause` values as the fixture
  `ConcurrencyAnalystOutput.hypotheses`.

- `test_run_merges_precheck_into_empty_wait_chain` - given a fixture where
  `output.wait_chain == []` and the incident brief contains a blocking-primitive
  keyword, assert `AgentTurn` carries the pre-check candidates (verify via a
  side-effect on the `MockAIBackend` context capture or by inspecting a
  monkeypatched `_extract_wait_chain_candidates`).

- `test_run_does_not_overwrite_populated_wait_chain` - when the `MockAIBackend`
  returns `output.wait_chain = ["Thread-3 -> MutexA"]`, the merge step does not
  prepend candidates; the turn reflects the LLM output verbatim.

- `test_run_injects_skeptic_corrections_on_round_2` - build a state with
  `round_number=2` and a history entry from `"Skeptic Agent"` at turn 1
  containing `corrections=["re-examine lock order"]`; assert the context dict
  passed to `MockAIBackend.generate` includes
  `"skeptic_corrections_from_previous_round"`.

### Prompt content

- `test_system_prompt_contains_deadlock_keywords` - assert `_SYSTEM_PROMPT`
  contains the words `deadlock`, `lock`, `race`, `wait_chain`
  (case-insensitive); these are the minimum signals that make the prompt a
  concurrency specialist rather than a generic agent.

- `test_system_prompt_mentions_blocking_primitives` - assert `_SYSTEM_PROMPT`
  contains at least two of: `WaitForMultipleObjects`, `EnterCriticalSection`,
  `pthread_mutex`, `std::mutex`, `futex`.

- `test_system_prompt_references_output_schema` - assert `_SYSTEM_PROMPT`
  references `ConcurrencyAnalystOutput` or its JSON field names so the LLM
  knows the required shape.

### Wait-chain pre-check (`_extract_wait_chain_candidates`)

These tests exercise the pure helper function directly.

- `test_precheck_fires_on_enter_critical_section` - input text containing
  `"EnterCriticalSection"` returns a non-empty list.

- `test_precheck_fires_on_pthread_mutex_lock` - input containing
  `"pthread_mutex_lock"` returns a non-empty list.

- `test_precheck_fires_on_wait_for_multiple_objects` - input containing
  `"WaitForMultipleObjects"` returns a non-empty list.

- `test_precheck_empty_on_unrelated_text` - input with no blocking-primitive
  keywords returns `[]`.

- `test_precheck_no_shell_or_eval` - static analysis assertion: the source
  of `_extract_wait_chain_candidates` does not contain the strings `"shell"`,
  `"eval"`, `"exec"`, `"subprocess"` (read the source via `inspect.getsource`
  and assert).

### ClassVar correctness

- `test_agent_key` - `ConcurrencyAnalystAgent.agent_key == "concurrency_analyst"`.
- `test_category` - `ConcurrencyAnalystAgent.category == "forensic"`.
- `test_display_name` - `ConcurrencyAnalystAgent.display_name == "Concurrency Analyst Agent"`.

## Mock-pipeline test - `test_concurrency_analyst.py` (continued)

- `test_mock_pipeline_deadlock_incident` - construct a minimal
  `InvestigationState` with `fault_class="deadlock"` and a brief whose
  `raw_text_excerpt` contains `"EnterCriticalSection"` and two thread blocks.
  Wire `ConcurrencyAnalystAgent` into a one-node "pipeline" with a
  `MockAIBackend`. Assert:
  - The returned `AgentTurn` has `agent == "Concurrency Analyst Agent"`.
  - `hypotheses` is non-empty.
  - The context supplied to `MockAIBackend.generate` contained
    `"wait_chain_candidates"`.

## Integration test - `test_concurrency_analyst_pipeline.py`

- `test_enabling_concurrency_analyst_yields_debate_turn` - build a full
  `AgentPanelSettings` with `per_fault_class["deadlock"]` containing
  `"concurrency_analyst"`. Call `create_agent_panel(ai_backend=mock,
  settings=settings, fault_class=FaultClass.deadlock)`. Advance the debate
  sub-graph for one round using the `MockAIBackend`. Assert:
  - `ConcurrencyAnalystAgent` appears in the panel.
  - The discussion history after one round includes a turn from
    `"Concurrency Analyst Agent"`.
  - `SkepticAgent` is last in the panel.

- `test_base_panel_unaffected_without_specialist` - with a default
  `AgentPanelSettings` (no `per_fault_class` override), the panel returned for
  `fault_class=FaultClass.deadlock` is the legacy four-agent chain and contains
  no `ConcurrencyAnalystAgent`.

## Fixtures

Define in `tests/conftest.py` (or a `tests/unit/conftest.py`):

- `deadlock_incident_brief` - a dict with `fault_class="deadlock"`,
  `raw_text_excerpt` containing `"EnterCriticalSection"` and two thread
  references, and minimal required fields (`exception_code_raw`, etc.).
- `concurrency_output_fixture` - a valid `ConcurrencyAnalystOutput` with one
  hypothesis, `confidence_score=0.75`, non-empty `wait_chain`,
  `lock_order_inversions=[]`, `suspected_race=None`.

## Constraints

- No real AI, network, or filesystem calls. All external I/O mocked.
- `ruff check src/ tests/` - clean.
- No test may weaken, `xfail`, or delete an existing passing test.
- The Stop hook runs `tests/unit/` automatically; integration tests under
  `tests/integration/` are run separately.
- Sensitive content (raw stack text, log excerpts) in fixtures must be synthetic
  and must not resemble real production system data.

## Success criteria

- [ ] All unit tests in `test_concurrency_analyst.py` pass.
- [ ] Schema tests (subtask 01) in `test_schemas.py` pass.
- [ ] Registry tests (subtask 04) in `test_agent_registry.py` pass.
- [ ] Integration tests in `test_concurrency_analyst_pipeline.py` pass with
      mocked externals.
- [ ] `ruff check src/ tests/` - clean.
- [ ] No existing passing tests are broken.
- [ ] Coverage on `agents/forensic/concurrency_analyst.py` is 90% or above.
