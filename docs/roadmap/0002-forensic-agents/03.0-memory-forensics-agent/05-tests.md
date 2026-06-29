# 05 — Tests

**Parent task:** 03.0 Memory Forensics Agent
**State:** ⬜ Not started
**Depends on:** 01 (output schema), 02 (consensus weights), 03 (agent implementation), 04 (registry & panel wiring)
**Blocks:** —

## Objective

Deliver a complete test suite for `MemoryForensicsAgent` covering: schema
validation, system-prompt content, the deterministic fill-pattern pre-check, mock
pipeline execution, and an integration test demonstrating that enabling the agent
on a `memory_access_violation` incident produces a `memory_forensics` debate turn.

## Files

- **Modify** `tests/unit/test_schemas.py` — schema tests (covered in subtask 01;
  verify they are present, add any missed).
- **Create** `tests/unit/test_memory_forensics_agent.py`
- **Create** `tests/integration/test_memory_forensics_integration.py`

## Unit tests (`tests/unit/test_memory_forensics_agent.py`)

### System-prompt content

- `test_system_prompt_contains_specialism_keywords` — assert `_SYSTEM_PROMPT`
  contains at least: `"heap"`, `"use-after-free"`, `"fill"`, `"0xBAADF00D"`,
  `"MemoryForensicsOutput"`.
- `test_system_prompt_does_not_instruct_shell_or_eval` — assert `_SYSTEM_PROMPT`
  does not contain the strings `"shell"`, `"eval"`, `"exec("`, `"subprocess"`.

### ClassVar identity

- `test_classvar_agent_key` — `MemoryForensicsAgent.agent_key == "memory_forensics"`.
- `test_classvar_category` — `MemoryForensicsAgent.category == "forensic"`.
- `test_classvar_display_name` — `MemoryForensicsAgent.display_name == "Memory Forensics Agent"`.

### Fill-pattern pre-check

Use a fixture `incident_brief_with_baadfd00` that includes `"raw_text_excerpt"`
containing the string `"0xBAADF00D"` and no other sentinels.

- `test_fill_pattern_precheck_detects_baadf00d` — construct an
  `InvestigationState` with the fixture brief, run `agent.run(state)` against a
  `MockAIBackend` that returns a `MemoryForensicsOutput` with
  `corruption_signatures=[]`; assert the returned `AgentTurn` has a non-empty
  `hypotheses` list and that `"0xBAADF00D"` appears in the LLM context passed to
  the mock (inspect `MockAIBackend.last_messages`).

Use a second fixture `incident_brief_multiple_sentinels` containing
`"0xFEEEFEEE"` and `"0xDDDDDDDD"` in `stack_frames`.

- `test_fill_pattern_precheck_multiple_sentinels` — after `run()`, assert both
  sentinels appear in the context passed to `MockAIBackend`.
- `test_fill_pattern_precheck_merges_with_llm_output` — `MockAIBackend` returns
  `corruption_signatures=["0xABABABAB"]`; assert the merged list in the final
  turn contains both the pre-check sentinel and the LLM-returned one.
- `test_fill_pattern_precheck_clean_brief_no_signatures` — a brief with no
  sentinel strings produces `pre_detected_signatures == []` and the agent does
  not add spurious entries.

### `run()` output shape

Use `MockAIBackend` returning a fully-populated `MemoryForensicsOutput`.

- `test_run_returns_agent_turn` — `run()` returns an `AgentTurn` instance.
- `test_run_agent_name_matches_display_name` — `turn.agent == "Memory Forensics Agent"`.
- `test_run_confidence_score_propagated` — `turn.confidence_score` equals the
  value returned by `MockAIBackend`.
- `test_run_hypotheses_propagated` — `len(turn.hypotheses) == len(mock_output.hypotheses)`.
- `test_run_accumulates_tokens` — `self._accumulate_tokens` is called (spy or
  assert `state["total_tokens"]` is updated after `run()`).

### Skeptic corrections

- `test_run_incorporates_skeptic_corrections` — an `InvestigationState` with
  `round_number=2` and a prior Skeptic turn carrying `corrections=["re-examine
  heap header"]` causes those corrections to appear in the context dict passed
  to `MockAIBackend`.

## Mock pipeline test

In `tests/unit/test_memory_forensics_agent.py`:

- `test_mock_pipeline_memory_access_violation` — build a minimal panel
  `[OSKernelAgent(mock_ai), MemoryForensicsAgent(mock_ai), SkepticAgent(mock_ai)]`
  via `create_agent_panel` with `fault_class=FaultClass.memory_access_violation`
  and default settings. Run each agent's `run()` sequentially against a shared
  `InvestigationState`. Assert:
  - The panel contains exactly one `MemoryForensicsAgent`.
  - `MemoryForensicsAgent` is not last (Skeptic is last).
  - All three turns are `AgentTurn` instances with correct `agent` strings.

## Integration test (`tests/integration/test_memory_forensics_integration.py`)

Uses a mocked AI backend (no live LLM call) and the full orchestrator path.

- `test_memory_forensics_turn_present_in_debate` — configure the orchestrator
  with `fault_class=memory_access_violation` and a settings object that enables
  `memory_forensics` in the panel. Run the orchestrator against a synthetic
  `IncidentBrief` fixture (no real dump). Assert:
  - `InvestigationState.discussion_history` contains at least one `AgentTurn`
    with `agent == "Memory Forensics Agent"`.
  - The final `RCAReport` is produced (not a `HITLRequest`), given a confident
    mock output.
- `test_memory_forensics_absent_from_unrelated_fault_class` — configure with
  `fault_class=deadlock` (default panel, no `memory_forensics` in per-fault
  override). Assert no turn with `agent == "Memory Forensics Agent"` appears
  in `discussion_history`.

## Constraints

- `MockAIBackend` must return a valid `MemoryForensicsOutput` (use
  `model_validate` or direct construction — no raw dict bypass).
- All tests use `pytest.mark.asyncio` for `async` test functions.
- No live network calls, no real filesystem writes in unit tests.
- `Optional[T]` from `typing`; `mypy --strict` clean; `ruff` clean.
- The Stop hook runs the unit suite; integration tests run separately under
  `tests/integration/`.

## Success criteria

- [ ] All unit tests in `test_memory_forensics_agent.py` pass.
- [ ] Fill-pattern pre-check tests confirm `0xBAADF00D`, `0xFEEEFEEE`, and
      `0xDDDDDDDD` are detected from `raw_text_excerpt` and `stack_frames`.
- [ ] Merge test confirms LLM-supplied signatures are not discarded.
- [ ] Mock pipeline test confirms panel ordering (Skeptic last).
- [ ] Integration tests confirm agent appears in debate for authoritative fault
      classes and is absent for non-authoritative ones.
- [ ] `mypy --strict` clean; `ruff` clean.
