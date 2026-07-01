# 06 - Tests (task gate)

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04, 05
**Blocks:** -

## Objective

Consolidate the test gate for the extensible-panel refactor. Most assertions are
authored inside subtasks 01–05; this subtask confirms the suite is green as a
whole and adds the cross-cutting **back-compat equivalence** and
**variable-panel** integration tests.

## Cross-cutting tests to add

- `tests/unit/test_consensus.py::test_calculate_matches_0001_for_base_panel`
  (from 02) - pin the exact 0001 numbers.
- `tests/unit/test_agent_registry.py` (from 03) - registry + factory behavior.
- `tests/unit/test_orchestrator.py::test_default_panel_node_chain` (from 04).
- **New integration:** `tests/integration/test_panel_pipeline.py`:
  - `test_default_panel_e2e_equivalent` - run the full pipeline with `MockAIBackend`
    and default config; assert the discussion history contains exactly the four
    base agents in order and the consensus/convergence outcome matches the 0001
    integration baseline.
  - `test_specialist_panel_e2e` - enable one specialist via settings; assert it
    appears as a debate turn and contributes to the weighted consensus.

## Full gate (all must pass)

1. `poetry run pytest tests/unit/ -q` - green, no weakened tests.
2. `poetry run pytest tests/integration/ -q` - green, including the two new tests.
3. `mypy src/` (strict) - zero errors.
4. `ruff check` + `ruff format --check`; `scripts/replace_optional.py --check`.

## Success criteria

- [ ] Back-compat: default-config consensus and panel are provably identical to 0001.
- [ ] Variable-panel: a specialist can be enabled by config and is exercised E2E.
- [ ] Full unit + integration suites green; types/lint clean.
- [ ] `status.md` Task 02.0 row flipped to ✅ with the test list.
