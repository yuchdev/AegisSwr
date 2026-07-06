# Task 09.0 — Documentation & CI

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Close the milestone with documentation and CI enforcement. Author
`docs/openclaude-setup.md` (prerequisites and OpenClaude install; external-mode
setup with the required allowlist launch flags and `OPENCLAUDE_GRPC_URL`
verification via `--dry-run`; managed-mode setup; the operator-supplied model
env vars OpenClaude itself reads, with a pointer to OpenClaude's docs;
troubleshooting for health-check and allowlist failures) and
`docs/openclaude-config-reference.md` (the full `OpenClaudeSettings` field table
from C1, the `openclaude_agent` role example, allowlist defaults, and the event
reference from C8).

Add CI: extend the `grep` boundary check to reject `aegis.openclaude` imports in
`aegis/core/`, `aegis/ui/`, and `aegis/code_intel/`, and `grpc` imports outside
`aegis/openclaude/grpc/client.py`; run `tests/openclaude/unit/` on every PR with
no external dependencies; gate `tests/openclaude/integration/` behind an
`OPENCLAUDE_INTEGRATION` signal (skipped on PRs, optional on main); enforce the
coverage gate (≥ 90% overall unit, 100% on `tool.py`). Finally, mark all tasks
✅ in `status.md`, verify the global acceptance criteria, and add a `CHANGELOG.md`
entry referencing all nine tasks and the supersession of Milestone 0004.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [`docs/openclaude-setup.md`](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/01-setup-guide.md) | ⬜ Not started | none |
| 02 | [`docs/openclaude-config-reference.md`](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/02-config-reference.md) | ⬜ Not started | none |
| 03 | [CI `grep` boundary check extension](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/03-ci-boundary-check.md) | ⬜ Not started | none |
| 04 | [CI coverage gate extension](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/04-ci-coverage-gate.md) | ⬜ Not started | none |
| 05 | [Milestone closeout + `CHANGELOG.md`](/docs/roadmap/0004-code-intelligence/09.0-documentation-ci/05-milestone-closeout.md) | ⬜ Not started | none |

## Key constraints

- The `grep` CI extension must fail the build on a deliberately introduced
  `import grpc` in `aegis/core/` (and on `aegis.openclaude` imports in
  `aegis/code_intel/`).
- Both docs render without broken internal links
  (`python scripts/check_doc_links.py docs/`).
- The coverage gate is enforced in CI configuration, not merely documented.
- The `CHANGELOG.md` entry references all nine tasks and records that this
  milestone supersedes Milestone 0004.
