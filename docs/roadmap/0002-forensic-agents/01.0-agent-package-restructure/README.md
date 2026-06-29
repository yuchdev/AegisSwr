# Task 01.0 — Agent Package Restructure

**Parent milestone:** [Milestone 0002 — Forensic Agents](/docs/roadmap/0002-forensic-agents/plan.md)
**Status:** ⬜ Not started

## Scope

Reorganize `src/aegis_swr/agents/` into category subpackages — `base/`,
`forensic/`, `synthesis/` — with **zero behavior change**. The existing four
agents (`os_kernel`, `code_analyst`, `log_historian`, `skeptic`) and `base.py`
move into `agents/base/`; the two new (initially empty) category packages are
scaffolded so later tasks have a home. This is the enabling move for the whole
milestone — nothing else can land until the package can hold more than four
agents.

This task is **mechanical and risk-controlled**: every existing import keeps
working via re-export shims, and the full test suite must stay green throughout.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Move base agents into `agents/base/`](01-move-base-agents.md) | ⬜ Not started | 02, 03 |
| 02 | [Update consumers & back-compat shims](02-consumers-and-shims.md) | ⬜ Not started | 04 |
| 03 | [Scaffold `forensic/` & `synthesis/` packages](03-scaffold-categories.md) | ⬜ Not started | 04 |
| 04 | [Regression gate](04-regression-gate.md) | ⬜ Not started | — |

## Key constraints

- **No behavior change.** `git mv`-style moves only; no logic edits to the four
  agent modules in this task (the `BaseAgent` generalization is Task 02.0).
- **Both import paths resolve.** Old (`aegis_swr.agents.os_kernel`) keeps working
  via a shim; new (`aegis_swr.agents.base`) is the real home.
- `mypy --strict`, `ruff`, and `Optional[T]` conventions stay clean.
- The Stop-hook unit suite (478+ tests) passes unchanged after every subtask.
