# Task 01.0 — Static Analysis Rule Expansion

**Parent milestone:** [Milestone 0006 — Improvements & Optimizations](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
**Status:** ⬜ Not started

## Scope

Add 10–15 rules to the project's static-analysis gate to catch low-quality
code before it merges. This task delivers **14 rules**, split honestly across
two mechanisms rather than written as 14 bespoke AST checks:

1. **6 new custom Flake8 rules (`X013`–`X018`)** in
   `src/flake8_project_rules/rules.py` — for checks that require knowledge of
   *this* codebase's own architecture (its settings convention, its timeout
   mandate, its sensitive-logging invariant) and that no off-the-shelf ruff
   plugin can express.
2. **8 native ruff rule-category additions** to `ruff.toml`'s `[lint] select`
   — configuration-only, zero new code, for checks a ruff plugin already
   implements.

### Why the split (read this before adding rule #15 as a custom `X`-code)

`docs/dev/python_language_rules.md` §1.4 is explicit: *"Do not use Flake8 to
re-implement checks ruff already performs — that just produces duplicate or
conflicting diagnostics."* Every rule proposed for this task was checked
against ruff's native plugin catalogue before being assigned to group 1 or
group 2:

| Originally considered                              | Already native to ruff?                          | Assigned to |
|-----------------------------------------------------|---------------------------------------------------|-------------|
| `os.environ`/`os.getenv` outside settings modules   | No plugin covers this (project-specific)           | `X013` |
| External call missing an explicit `timeout=`        | No plugin covers this (project-specific)           | `X014` |
| `subprocess.Popen`/`socket.socket` not RAII-managed | Partial — `SIM115` covers bare `open()` only, not `Popen`/`socket` | `X015` (scoped to exclude what `SIM115` would cover) |
| Malformed `# TODO` annotation format                 | No plugin covers comment *format* (only existence: `FIX002`) | `X016` |
| `print()`/`pprint()` in product code                 | **Yes** — `T20` (flake8-print)                     | ruff subtask |
| Sensitive-named value in a logging/exception call    | No plugin covers this (project-vocabulary-specific)| `X017` |
| `assert` in product code                             | **Yes** — `S101` (flake8-bandit)                   | ruff subtask |
| `eval()`/`exec()`/`compile()`                        | **Yes** — `S102`/`S307` (flake8-bandit)             | ruff subtask |
| Missing `from __future__ import annotations`         | **Yes** — `FA100`/`FA102` (flake8-future-annotations)| ruff subtask |
| Unprefixed mutable module-level global                | No plugin covers the *naming* convention (only literal-default-arg mutability, via `B006`, which is unrelated) | `X018` |
| Too many public methods on a class                    | **Yes** — `PLR0904` (pylint)                       | ruff subtask |
| Naive `datetime.now()` without `tzinfo`               | **Yes** — `DTZ005`/`DTZ003`/`DTZ011` (flake8-datetimez)| ruff subtask |
| Too many function arguments                           | **Yes** — `PLR0913`/`PLR0917` (pylint)              | ruff subtask |
| Too many statements/branches (complexity)              | **Yes** — `C901` (mccabe), `PLR0912`/`PLR0915` (pylint) | ruff subtask |

Six rules had no native ruff equivalent and became new `X`-codes; eight did
and become config-only ruff subtasks. This table is the actual design
rationale — a future contributor proposing a 15th rule should extend this
table, not skip straight to writing AST code.

## Subtasks

### Group A — new custom Flake8 rules (`src/flake8_project_rules/rules.py`)

| #  | Rule  | Document                                                                 | Status         |
|----|-------|---------------------------------------------------------------------------|----------------|
| 01 | X013  | [Env access outside settings modules](01-env-access-outside-settings.md) | ⬜ Not started |
| 02 | X014  | [External call missing a timeout](02-external-call-missing-timeout.md)  | ⬜ Not started |
| 03 | X015  | [Non-RAII subprocess/socket resource](03-non-raii-subprocess-socket.md) | ⬜ Not started |
| 04 | X016  | [Malformed TODO annotation](04-malformed-todo-annotation.md)            | ⬜ Not started |
| 05 | X017  | [Sensitive value in a log/exception call](05-sensitive-value-in-log-call.md) | ⬜ Not started |
| 06 | X018  | [Unprefixed mutable module-level global](06-unprefixed-mutable-global.md) | ⬜ Not started |

### Group B — native ruff rule-category additions (`ruff.toml` only)

| #  | Rule(s)                    | Document                                                                     | Status         |
|----|-----------------------------|-------------------------------------------------------------------------------|----------------|
| 07 | `S101`, `S102`, `S307`      | [Bandit subset: assert / exec / eval](07-ruff-bandit-subset.md)              | ⬜ Not started |
| 08 | `T201`, `T203`              | [Print-ban (flake8-print)](08-ruff-print-ban.md)                             | ⬜ Not started |
| 09 | `FA100`, `FA102`            | [Future-annotations required](09-ruff-future-annotations.md)                 | ⬜ Not started |
| 10 | `DTZ001`, `DTZ003`, `DTZ005`, `DTZ011` | [Naive-datetime ban (flake8-datetimez)](10-ruff-datetimez.md)     | ⬜ Not started |
| 11 | `PLR0913`, `PLR0917`        | [Too many function arguments](11-ruff-too-many-arguments.md)                 | ⬜ Not started |
| 12 | `PLR0904`                   | [Too many public methods](12-ruff-too-many-public-methods.md)               | ⬜ Not started |
| 13 | `C901`                      | [Cyclomatic complexity (mccabe)](13-ruff-complexity-mccabe.md)               | ⬜ Not started |
| 14 | `PLR0912`, `PLR0915`        | [Too many branches / statements](14-ruff-too-many-statements-branches.md)    | ⬜ Not started |

Every subtask in Group A is independent of every other — they touch
disjoint functions in `rules.py` and disjoint sample files — and may proceed
fully in parallel. Every subtask in Group B is a disjoint `ruff.toml`
`select` entry and may also proceed in parallel with everything else,
**except** that all eight Group B subtasks edit the same `[lint] select`
list in `ruff.toml`, so they should be landed as small, sequential PRs (or
one combined PR) to avoid merge conflicts on that one file.

## Shared plumbing (not a subtask — a prerequisite touched by every Group A rule)

Every Group A subtask adds one function to `src/flake8_project_rules/rules.py`
and one call to it from `_iter_violations`, plus:

- `tests/flake8_lint/config.py`: extend `KNOWN_RULE_CODES` from
  `range(1, 13)` (X001–X012) to `range(1, 19)` (X001–X018). Do this once, in
  whichever Group A subtask lands first — do not duplicate the edit across
  all six.
- `pyproject.toml` `[tool.flake8_lint_tests]`: add the new code to `select`
  once its rule is ready to be enforced project-wide (mirrors how `X012`
  itself was folded into `select` in Milestone 0005).
- `tests/flake8_lint/samples/`: each subtask adds its own
  `xNNN_<slug>.py` sample (both a violating and a clean variant, mirroring
  the existing `x00N_*` samples), plus a `valid_clean_module.py` check that
  the new rule does not false-positive on already-passing code.
- `docs/dev/python_language_rules.md`: no edit needed — that document
  describes the *tool selection* policy (§1), not individual rule codes; the
  authoritative rule catalogue lives in `rules.py`'s own module docstring
  (update its rule-range comment from "X001–X012" to "X001–X018") and in this
  README's table above.

## Key constraints

- Every new custom rule follows the existing `RuleViolation` /
  `_iter_violations` / `# noqa: XNNN` plumbing in `rules.py` verbatim — no
  parallel rule-engine mechanism.
- Every new custom rule ships with: a violating sample, a clean/passing
  sample, a unit test in `tests/flake8_lint/test_plugin_direct.py`, and a
  project-wide scan pass in `tests/flake8_lint/test_project_lint.py`.
- A newly-enabled ruff category (Group B) may surface pre-existing violations
  in `src/`/`tests/`. Fix them as part of that subtask — do not land the
  `select` addition with a blanket `per-file-ignores` suppression covering
  the whole codebase; that defeats the point of enabling the rule.
- No rule in either group touches runtime behavior — this task changes only
  what the static-analysis gate flags, never `src/aegis_swr`'s product logic
  (outside of whatever pre-existing violations Group B rules require fixing).
- All new/changed code stays `ruff` clean and keeps `mypy.ini`'s current
  (pre-Task-02.0) bar.

## Files created or modified by this task

```
src/flake8_project_rules/
└── rules.py                  ← 6 new check functions (X013–X018) + 6 new
                                 _iter_violations yields; module docstring
                                 range comment updated to "X001-X018"

ruff.toml                     ← [lint] select gains: S101, S102, S307,
                                 T201, T203, FA100, FA102, DTZ001, DTZ003,
                                 DTZ005, DTZ011, PLR0913, PLR0917, PLR0904,
                                 C901, PLR0912, PLR0915 (+ [lint.mccabe]
                                 max-complexity, [lint.pylint] thresholds)

pyproject.toml                ← [tool.flake8_lint_tests] select gains
                                 X013-X018 as each lands

tests/flake8_lint/
├── config.py                  ← KNOWN_RULE_CODES extended to X001-X018
├── samples/
│   ├── x013_env_access.py
│   ├── x014_missing_timeout.py
│   ├── x015_non_raii_resource.py
│   ├── x016_malformed_todo.py
│   ├── x017_sensitive_log_value.py
│   └── x018_unprefixed_mutable_global.py
├── test_plugin_direct.py      ← one test function per new rule
└── test_project_lint.py       ← unchanged mechanism; scope grows automatically
```
