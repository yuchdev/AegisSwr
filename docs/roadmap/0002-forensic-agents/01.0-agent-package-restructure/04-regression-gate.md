# 04 - Regression gate

**Parent task:** 01.0 Agent Package Restructure
**State:** ⬜ Not started
**Depends on:** 02, 03
**Blocks:** -

## Objective

Prove the restructure changed nothing observable: the full suite is green, types
and lint are clean, and both old and new import paths resolve.

## Checks (all must pass)

1. **Unit suite:** `poetry run pytest tests/unit/ -q` - same pass count as before
   the task (478+ passing, 3 skipped per 0001 status). No new failures, no
   weakened/`xfail`'d tests.
2. **Integration suite:** `poetry run pytest tests/integration/ -q` - unchanged.
3. **Types:** `python scripts/replace_optional.py --check` - clean.
4. **Lint/format:** `ruff check src/ tests/` and `ruff format --check src/ tests/`.
5. **Optional convention:** `python scripts/replace_optional.py --check`.
6. **Import matrix** (new `test_agents_package.py` from subtasks 02–03):
   - new `agents.base` path,
   - top-level `agents` re-export,
   - any retained legacy shim,
   - `forensic`/`synthesis` packages importable.

## Constraints

- This is a verification-only subtask - no `src/` logic changes. If a check
  fails, fix the cause in the owning subtask (01/02/03), not by relaxing the gate.

## Success criteria

- [ ] `pytest tests/unit/` and `tests/integration/` green with the same counts as
      the pre-task baseline.
- [ ] `ruff` clean; `replace_optional.py --check` clean.
- [ ] The import-matrix tests pass.
- [ ] `status.md` Task 01.0 row flipped to ✅ with the test list.
