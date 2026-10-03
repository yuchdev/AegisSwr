# Task 10.0 — Documentation & CI

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 Validation/Rollout (CI gates) + the milestone's doc
mandate (`.claude/CLAUDE.md` §6)
**Contracts:** C1, C8, C9, C11, C13

## Scope

Close the milestone: author/update the operator-facing docs, wire the CI gates ADR
0006 names, sync the roadmap/docs indices, and land the two cross-milestone
amendment notes (Milestone 0003's `status.md` retirement is owned by Task 01.0
subtask 03; this task owns the Milestone 0006 `plan.md` Task 05.0 note and verifies
the 0003 pointer resolves).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Config reference + migration docs](01-config-and-migration-docs.md) | ⬜ Not started | - |
| 02 | [`docs/README.md` + roadmap README sync](02-index-sync.md) | ⬜ Not started | - |
| 03 | [CI grep/coverage gate extensions](03-ci-gates.md) | ⬜ Not started | - |
| 04 | [Cross-milestone amendment notes](04-cross-milestone-amendments.md) | ⬜ Not started | - |
| 05 | [Milestone closeout + CHANGELOG](05-milestone-closeout.md) | ⬜ Not started | - |

The subtasks are independent and close the milestone; 05 is last.

## Contracts touched

- **C13** — the CI grep gate (import bans + MCP isolation) is formalised here.
- **C1/C8/C9/C11** — the config reference documents the sole-gateway posture, the
  MCP surface, the trust tiers, and the autonomy stages.

## Key constraints

- `check_doc_links.py` (the `/link-check` skill) must be clean on every touched file
  (absolute-from-repo-root links; the `doc_link_check` hook enforces it).
- The doc set follows the repo's category convention (`docs/config/`,
  `docs/security/`); the roadmap/docs indices stay current.

## Files created or modified by this task

```
docs/config/
├── harness-gateway.md         ← NEW: sole-gateway posture, no-key boot, role→session binding table (C1, C3)
├── harness-selection.md       ← updated: the two trust tiers + per-tier truth table (C9)
├── mcp-tool-surface.md        ← NEW: the four tools, redaction boundary, authz (C8)
└── autonomy-stages.md         ← NEW: the four-stage ramp, opt-in flags, gates (C11)

docs/roadmap/README.md         ← updated: Milestones table row + decomposition footnote
docs/README.md                 ← updated: roadmap table row

docs/roadmap/0006-improvements-and-optimizations/plan.md ← amended: Task 05.0 telemetry note (subtask 04)

.github/workflows/             ← updated: import-ban grep job + adapter/MCP/tier/gate coverage gates
CHANGELOG.md                   ← updated: Milestone 0007 entry (subtask 05)
```
