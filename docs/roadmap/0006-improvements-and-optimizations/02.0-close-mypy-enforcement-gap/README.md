# Task 02.0 — Close the mypy Enforcement Gap

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

Make `strict = true` in `mypy.ini` true *in practice*, and make a `mypy`
failure block a merge. Two things are broken today, both read directly out of
the repository:

1. **`.github/workflows/ci.yml` has no `mypy` step at all.** The `lint` job
   (ci.yml:15-36) runs `ruff check src/ tests/` and the custom
   `flakeforge check .` gate, and nothing else. `mypy` never runs in CI, so the
   project standard that `docs/dev/python_language_rules.md` §1.4 states —
   "do not merge a change that introduces a new mypy error" — is unenforced.
   `.claude/CLAUDE.md` §4's "Unconditional after every task" gate invokes
   `ruff` and `pytest` but never `mypy` either.
2. **`mypy.ini` disables far more than its headline setting implies.** The file
   is only six lines, but line 6 disables **eleven** error codes:

   ```ini
   [mypy]
   python_version = 3.12
   strict = true
   plugins = pydantic.mypy
   enable_error_code = redundant-cast,no-redef
   disable_error_code = no-untyped-def,no-untyped-call,arg-type,type-arg,no-any-return,assignment,union-attr,attr-defined,return-value,annotation-unchecked,import-untyped
   ```

   A local `uv run mypy` today therefore checks a **materially weaker** contract
   than `strict = true` advertises: untyped function bodies, untyped calls,
   bad argument types, bare generics, `Any` returns, bad assignments,
   attribute access on `Optional`/union values, undefined attributes, wrong
   return values, and missing third-party stubs are all silently accepted.

This task (a) adds a `mypy` CI job that is **green on day one** against the
*current* `mypy.ini`, then (b) retires the eleven disabled codes in grouped
burn-down campaigns until `disable_error_code` is empty.

### Re-verification note — the plan's evidence was stale

`plan.md`'s Task 02.0 "Verified gap" names **four** disabled codes
(`no-untyped-def`, `no-untyped-call`, `arg-type`, `type-arg`). At decomposition
time `mypy.ini` disables **eleven** — the four named plus `no-any-return`,
`assignment`, `union-attr`, `attr-defined`, `return-value`,
`annotation-unchecked`, and `import-untyped`. The plan's "one subtask per
disabled code" sketch (which anticipated four) would have produced an
incomplete task. This task is decomposed against the eleven that are actually
disabled, grouped by burn-down affinity rather than one-code-per-subtask (which
would have been eleven thin files whose fixes overlap heavily — annotating a
function to satisfy `no-untyped-def` usually clears its `no-untyped-call`
call-site errors and its `annotation-unchecked` notes in the same edit).

### Why these groupings (read this before splitting a group into per-code subtasks)

**Baselines below are measured, not estimated.** Re-verified 2026-10-03 by
running `mypy` with every disabled code re-enabled and no other change
(`uv run mypy --config-file <strict, no disable_error_code> src/aegis_swr/`):
**211 errors in 34 files** out of 106 source files checked. The per-code
breakdown changes the picture from the original grep-based estimate in one
important way — **four of the eleven disabled codes have zero current
violations**:

| # | Disabled code(s) in the group | Real count | Nature | Why grouped together |
|---|-------------------------------|-----------:|--------|----------------------|
| 02 | `no-untyped-def`, `no-untyped-call` | 128 + 65 = **193** | Annotation coverage | Annotating a def kills its `no-untyped-def` error and clears the `no-untyped-call` errors at every call site — one campaign, two codes. By far the largest backlog (91% of all errors); land first. |
| 03 | `type-arg` | **5** | Generic parameterisation | Bare `dict`/`list`/`Callable`/`type` without type args. Mechanical, annotation-only. |
| 04 | `arg-type` | **8** | Value-flow at boundaries | Fires on values crossing a typed boundary (an argument expression). Small, real backlog. |
| 05 | `assignment`, `attr-defined` | 1 + 1 = **2** | None-safety / attribute correctness | Tiny backlog; usually the same narrowing/guard edit resolves both on sight. |
| 06 | `import-untyped` | **3** | Third-party stubs | Resolved by installing stub packages or a scoped per-module `ignore_missing_imports`, not by editing product code. Kept separate so the stub decisions are reviewed on their own. |
| — | `no-any-return`, `union-attr`, `return-value`, `annotation-unchecked` | **0** | Zero-violation codes | **Not a subtask.** These four already pass clean under the current codebase — re-enabling them is a one-line `mypy.ini` edit with no burn-down. Fold this into subtask 01 (see below) rather than giving it its own subtask. |

This reshapes the task materially versus the original grouping (which bundled
`return-value`/`no-any-return` into group 04 and `union-attr`/`annotation-unchecked`
into groups 05/02 as if they carried comparable weight): **193 of 211 errors
(91%) are in group 02 alone**, and the previously-named "value-flow" and
"None-safety" groups are single-digit cleanups, not comparable campaigns. The
four zero-violation codes should be dropped from `disable_error_code`
immediately as part of subtask 01 (a trivial, risk-free win), not treated as
their own burn-down subtasks.

## Subtasks

| #  | Name / codes                                              | Real count | Document                                                        | Status         |
|----|-----------------------------------------------------------|-----------:|-------------------------------------------------------------------|----------------|
| 01 | `mypy` CI job + drop the 4 zero-violation codes for free  | 0 | [Add the mypy CI job](01-mypy-ci-job.md)                        | ⬜ Not started |
| 02 | `no-untyped-def` + `no-untyped-call`                      | 193 | [Annotation-coverage burn-down](02-reenable-untyped-def-call.md) | ⬜ Not started |
| 03 | `type-arg`                                                | 5 | [Generic-parameterisation burn-down](03-reenable-type-arg.md)   | ⬜ Not started |
| 04 | `arg-type`                                                | 8 | [Value-flow burn-down](04-reenable-arg-type-return-value.md)    | ⬜ Not started |
| 05 | `assignment` + `attr-defined`                             | 2 | [None-safety burn-down](05-reenable-assignment-union-attr.md)   | ⬜ Not started |
| 06 | `import-untyped`                                          | 3 | [Third-party stub resolution](06-reenable-import-untyped.md)    | ⬜ Not started |

211 errors total, measured 2026-10-03 (see rationale above); filenames for 04/05
are kept as originally assigned even though their code lists shrank, to avoid
a churny rename across subtask cross-references.

**Sequencing.** Subtask 01 must land first and alone — it establishes the CI
gate, drops the four zero-violation codes immediately, and sets up the
baseline-command methodology every later subtask reuses. Subtasks 02–06 each
edit the single `disable_error_code` line in `mypy.ini`, so they **cannot run
fully in parallel**: they must be landed as small sequential PRs to avoid merge
conflicts on that one line. Recommended order: 03 → 06 → 04 → 05 → 02 — land
the four tiny backlogs (5, 3, 8, and 2 occurrences respectively) first since
each is a single small PR, before the one large campaign (193 occurrences,
91% of all errors) that genuinely benefits from its own dedicated effort and,
being the biggest diff, is likeliest to need an `incident-analyst` pass if any
touched function sits on investigation flow.

## Key constraints

- Subtask 01 must leave CI **green** — it runs `mypy` against the *current*
  `mypy.ini` (all eleven codes still disabled), so it cannot introduce a new
  failure; it only locks in today's bar and makes regressions visible.
- No subtask may drop a code from `disable_error_code` until that code's
  backlog is **zero** across `src/aegis_swr/`. Never land a `select`-style
  partial enable with a blanket per-module `# type: ignore` sweep "to fix
  later" — that is the exact failure mode this task exists to close.
- `# type: ignore[code]` is permitted only with an inline justification comment
  and only for a genuinely unavoidable third-party gap (subtask 06); it is not
  a burn-down shortcut for product code.
- The CI job is scoped to `src/aegis_swr/` (not `tests/`) to match the scope
  `strict = true` is meant to guarantee for shipped code; widening to `tests/`
  is explicitly out of scope for this task.
- No subtask changes runtime behaviour except where a real `None`-dereference
  or wrong-type bug surfaced by `union-attr`/`arg-type` must be fixed — any
  such fix that touches investigation flow needs an `incident-analyst` pass per
  `.claude/CLAUDE.md` §5.

## Files created or modified by this task

```
.github/workflows/ci.yml       ← new `mypy` job (subtask 01): scoped to
                                  src/aegis_swr/, matrix 3.12/3.13, gated on
                                  needs.assess.outputs.run_ci like its siblings

mypy.ini                       ← disable_error_code shrinks group by group
                                  across subtasks 02-06 until it is empty

src/aegis_swr/**/*.py          ← type annotations added / narrowed as each
                                  group's backlog is burned to zero; no runtime
                                  change except real None/type bugs uncovered
```
</content>
</invoke>
