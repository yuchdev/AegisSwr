# 04 — Burn down `arg-type`

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** [01 — Add the mypy CI job](01-mypy-ci-job.md); land **after**
subtask 02 (annotation coverage) so that function signatures are already typed
and these value-flow errors are visible rather than masked by untyped bodies
**Blocks:** none

## Objective

`mypy.ini:6` disables `arg-type` — a value passed to a parameter whose type
does not match. Measured 2026-10-03 (full re-enable run, see parent README):
**8 occurrences**, the only real backlog in this group. `return-value` and
`no-any-return` — originally grouped here on the plan's grep-based estimate —
measured **zero** violations each and are dropped for free in subtask 01; this
subtask's scope shrinks to `arg-type` alone.

## Implementation approach

1. Re-baseline with `uv run mypy --enable-error-code arg-type src/aegis_swr/`
   (subtask 01 methodology) — confirm the count is still small before starting;
   if new code has pushed it meaningfully higher than 8, reconsider whether
   this is still a single small PR.
2. For each site, fix the **caller** when it is passing the wrong type, or
   widen the callee's parameter only when the broader type is genuinely correct
   — never `# type: ignore` a real mismatch. At 8 occurrences this is a single
   PR covering every site, not a multi-PR campaign.
3. Drop `arg-type` from `disable_error_code` in the same PR as the fixes.

## Exclusions

- An `arg-type` whose root cause is an untyped third-party library's return
  feeding into a typed parameter is a stubbing problem — defer that specific
  site to subtask 06 (`import-untyped`) rather than forcing a local cast here.
- `assignment`/`attr-defined` errors are subtask 05's concern even if
  they appear in the same file; do not expand scope.

## Test plan

- CI `mypy` job stays green after `arg-type` is removed from `mypy.ini`.
- **Any fix that changes a value's type at runtime** (not just its annotation)
  ships with a `testing-expert` unit test asserting the corrected behaviour —
  these codes can uncover real bugs, and the fix must be proven, not just
  type-silenced.
- A fix touching investigation flow (e.g. a corrected `RCAReport` field type)
  gets an `incident-analyst` pass per `.claude/CLAUDE.md` §5.
- `uv run mypy src/aegis_swr/` clean locally before the PR.
</content>
