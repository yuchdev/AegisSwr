# Task 04.0 — CI Supply-Chain Integrity

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

`uv.lock` is committed, but **every** `uv sync` invocation across the workflow
files runs *unlocked*. An unlocked `uv sync` re-resolves dependencies against
`pyproject.toml` and will happily install something `uv.lock` does not pin if the
two have drifted — the exact opposite of the reproducible-build guarantee a
committed lockfile exists to give. This task makes CI install **only** what the
lockfile pins, and adds a dedicated fast-failing step that reports lockfile
drift once, clearly, instead of as a confusing downstream resolution difference.

### Re-verification note — the call-site count was stale (8 → 9)

`plan.md`'s Task 04.0 "Verified gap" says *"eight call sites total"* across
`ci.yml` and `coverage.yml`. At decomposition time a direct grep finds **nine**:

| File | `uv sync` line(s) | Count |
|------|-------------------|-------|
| `.github/workflows/ci.yml` | 30, 60, 71, 171, 199, 265, 301, 334 | 8 |
| `.github/workflows/coverage.yml` | 35 | 1 |
| **Total** | | **9** |

(The reusable `_ci-relevance-gate.yml` has no `uv sync` — it only runs the
relevance classifier.) The plan's "eight" counted `ci.yml` alone and omitted the
one in `coverage.yml`, or predates a since-added job. Subtask 01 is scoped to all
**nine**. If
[Task 02.0](/docs/roadmap/0006-improvements-and-optimizations/02.0-close-mypy-enforcement-gap/README.md)
lands its new `mypy` job first, that becomes a tenth call site — subtask 01 must
sweep whatever count is present at implementation time, not a frozen nine.

## Subtasks

| #  | Name                                                | Document                                                   | Status         |
|----|-----------------------------------------------------|------------------------------------------------------------|----------------|
| 01 | `uv sync --locked` across every workflow call site  | [Pin every uv sync to the lockfile](01-uv-sync-locked.md)  | ⬜ Not started |
| 02 | Dedicated fast-failing lockfile-drift CI step       | [Lockfile-drift gate](02-lockfile-drift-gate.md)           | ⬜ Not started |

**Sequencing.** Land 02 (the drift gate) **before or with** 01. Rationale: the
drift gate is what produces a *clear* failure message; if 01's `--locked` sweep
lands first and the lockfile happens to already be drifted, every job fails with
an opaque resolution error at once. Landing 02 first means the first symptom of
any pre-existing drift is the single, labelled drift step — then 01 converts the
rest. Both edit the workflow files, so land them as one PR or two tightly-ordered
ones to avoid conflicts.

## Key constraints

- `uv sync --locked` **fails** (non-zero) if `uv.lock` is out of date with
  `pyproject.toml`, rather than silently re-resolving — that failure *is* the
  guarantee; do not pair it with any flag that re-enables resolution.
- The drift gate must run **early in the `lint` job** (before the expensive test
  jobs) so drift is reported in seconds, not after a full matrix build.
- This task touches workflow YAML only — no `src/`, no `tests/`, no
  `pyproject.toml`/`uv.lock` content change (a drifted lockfile is fixed by
  `uv lock`, which is the developer's action the gate prompts, not part of this
  task).
- Every edited job keeps its existing `needs: assess` /
  `if: needs.assess.outputs.run_ci == 'true'` relevance-gate wiring untouched.

## Files created or modified by this task

```
.github/workflows/ci.yml        ← 8 `uv sync` → `uv sync --locked` (lines 30, 60,
                                   71, 171, 199, 265, 301, 334); new drift step
                                   added early in the `lint` job (subtask 02)

.github/workflows/coverage.yml  ← 1 `uv sync` → `uv sync --locked` (line 35)
```
</content>
