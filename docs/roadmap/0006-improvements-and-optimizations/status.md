# Milestone 0006 — Improvements & Optimizations — Status

Tracks progress against [plan.md](/docs/roadmap/0006-improvements-and-optimizations/plan.md).
Updated as each task lands.

## Current status

| Task | Name                                              | Status         | Tests |
|------|------------------------------------------------------|----------------|-------|
| 01.0 | Static Analysis Rule Expansion                    | ⬜ Not started | -     |
| 02.0 | Close the mypy Enforcement Gap                    | ⬜ Not started | -     |
| 03.0 | Storage Layer Durability & Concurrency            | ⬜ Not started | -     |
| 04.0 | CI Supply-Chain Integrity                          | ⬜ Not started | -     |
| 05.0 | Cost & Latency Telemetry for Router/Harness Events | ⬜ Not started | -     |
| 06.0 | Scheduled Documentation Health Checks              | ⬜ Not started | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** Milestone opened 2026-08-30. **All six tasks are now
decomposed into subtasks** — 30 subtasks in total:

- Task 01.0 — 14 subtasks ([01.0-static-analysis-rule-expansion/](01.0-static-analysis-rule-expansion/))
- Task 02.0 — 6 subtasks ([02.0-close-mypy-enforcement-gap/](02.0-close-mypy-enforcement-gap/))
- Task 03.0 — 3 subtasks ([03.0-storage-durability-concurrency/](03.0-storage-durability-concurrency/))
- Task 04.0 — 2 subtasks ([04.0-ci-supply-chain-integrity/](04.0-ci-supply-chain-integrity/))
- Task 05.0 — 3 subtasks ([05.0-cost-latency-telemetry/](05.0-cost-latency-telemetry/))
- Task 06.0 — 2 subtasks ([06.0-scheduled-doc-health-checks/](06.0-scheduled-doc-health-checks/))

No task has started implementation yet. The 2026-10-03 decomposition re-verified
each task's "verified gap" against the current repo and corrected three stale
figures (mypy disables 11 codes not 4; `PostgresStore` is still a stub with no
SQLAlchemy models; nine `uv sync` call sites not eight) — see each task README's
re-verification note.

## Notes & decisions

- 2026-08-30 — Milestone created. Task 01.0 (the explicitly requested
  static-analysis rule expansion) fully decomposed into 14 subtasks: 6 new
  custom Flake8 `X013`–`X018` rules plus 8 native-ruff rule-category
  additions, split per the project's own "don't reimplement what ruff already
  does" standard (`docs/dev/python_language_rules.md` §1.4). Tasks 02.0–06.0
  are each grounded in a gap read directly out of the repository during
  planning (see `plan.md`'s per-task "Verified gap" notes) rather than a
  generic checklist.
