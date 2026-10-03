# 02 — Burn down `no-untyped-def` + `no-untyped-call`

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Add the mypy CI job](01-mypy-ci-job.md)
**Blocks:** nothing, but should land before 03–06 (largest backlog; its
annotations incidentally reduce the other groups' counts)

## Objective

`mypy.ini`'s `disable_error_code` (mypy.ini:6) disables `no-untyped-def` and
`no-untyped-call`. Measured 2026-10-03 (full re-enable run, see parent README):
**128 + 65 = 193 occurrences — 91% of all 211 errors found across the whole
task.** This is unambiguously the largest gap: `src/aegis_swr/` has ~739 `def`
sites across 82 files, and at least ~144 are single-line signatures ending in
`):` with **no return annotation** — e.g. `backends/storage/sqlite_store.py`
alone has four (`def __init__(self, settings: StorageSettings):` at line 59,
`def _init_db(self):` at 64, plus the two `_sync_*` helpers). Each such def is
a `no-untyped-def` error under strict mypy; every call to one is a
`no-untyped-call` error. Re-enable both and annotate until the count is zero.

(`annotation-unchecked` — originally grouped here on the plan's grep-based
estimate — was verified to measure **zero** notes in this codebase even with
`no-untyped-def`/`no-untyped-call` still disabled, confirmed by testing both
configurations directly; it is dropped for free in subtask 01 and needs no
burn-down here.)

## Why these two together

Annotating one function clears both codes at once for that function:

- adding `-> T` and parameter types removes its `no-untyped-def` error;
- that same annotation makes every call site type-check, removing the
  `no-untyped-call` errors that pointed at it.

Splitting them into two subtasks would mean two passes over the same
functions. One campaign is correct.

## Implementation approach

1. Baseline each code with the methodology from subtask 01:
   ```bash
   uv run mypy --enable-error-code no-untyped-def src/aegis_swr/ 2>&1 | grep -c "error:"
   ```
   Record both starting counts (expect ~128 and ~65) in the PR.
2. Annotate module by module, leaf packages first (e.g. `core/`, `backends/`)
   so that by the time you reach callers their callees are already typed and the
   `no-untyped-call` errors have already cleared. A typical fix:

   ```python
   # before (sqlite_store.py:64) — no-untyped-def
   def _init_db(self):
       ...

   # after
   def _init_db(self) -> None:
       ...
   ```
3. Use real types, never `Any`, to close an error — a `-> Any` return would
   dodge `no-untyped-def` cheaply rather than pinning the actual type (and
   `no-any-return` is already re-enabled per subtask 01, so it would simply
   trade one error for another).
4. When both counts reach zero, remove `no-untyped-def` and `no-untyped-call`
   from `disable_error_code` in the same PR as the final fixes.

## Exclusions

- Do **not** annotate with `Any` to shortcut the count (see step 3).
- Generated stubs (`*_pb2.py`, `*_pb2_grpc.py`) are already excluded from the
  linter via `ruff.toml:8` and are not under `src/aegis_swr/`'s type bar in a
  way this subtask needs to touch; leave them.
- `tests/` is out of scope (the CI job is `src/aegis_swr/`-only).

## Test plan

- The CI `mypy` job (subtask 01) is the regression gate: after both codes
  are dropped from `mypy.ini`, the job must stay green on both 3.12 and 3.13.
- No new runtime unit test is expected (annotations are compile-time only). If
  annotating a function forced a real signature/logic correction, that
  correction ships with a `testing-expert` unit test for the corrected
  behaviour.
- Confirm `uv run mypy src/aegis_swr/` is clean locally with both codes
  removed before opening the PR.
</content>
