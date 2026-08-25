# Task 13.0 — Documentation & CI

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ✅ Complete (2026-08-25) — all five subtasks

## Scope

Close the milestone with operator-facing documentation and enforced CI gates for
the two new backends and the neutral harness layer.

Author, per backend family, a setup guide and a config reference that **mirror
the shipped OpenClaude pair** ([`docs/config/openclaude-setup.md`](/docs/config/openclaude-setup.md),
[`docs/config/openclaude-config-reference.md`](/docs/config/openclaude-config-reference.md))
section-for-section: `docs/config/claude-code-setup.md` +
`docs/config/claude-code-config-reference.md` (the setup guide states both C7 auth modes
and the C7 licensing caveat explicitly), and `docs/config/openhands-setup.md` +
`docs/config/openhands-config-reference.md` (the setup guide calls out the
Docker-on-Windows prerequisite explicitly). Author `docs/config/harness-selection.md` —
the operator-facing rendering of the C2 selection/ambiguity truth table — and
update the root `README.md` system-requirements area with the Docker-on-Windows
line and a backend-selection pointer.

Extend CI: generalize the existing `openclaude-isolation` `grep` boundary job to
also cover the `claude_code` and `openhands` packages plus the neutral `harness/`
layer (C3 — no backend imports a sibling; only `harness/composition.py` imports
more than one family), and extend the coverage gate to require ≥ 90% per-backend
unit coverage and 100% branch coverage on each new tool's `delegate()`, mirroring
Milestone 0004's `tool.py` gate. Finally, walk [plan.md](/docs/roadmap/0005-harness-backends/plan.md)'s "Global acceptance
criteria" checklist item by item, and describe the mechanics of flipping all 13
tasks (and their subtasks) to ✅ in `status.md`.

## Subtasks

| #  | Name                                                                                                                                                              | Status         | Blocks |
|----|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------|--------|
| 01 | [Claude Code docs (`claude-code-setup.md` + `claude-code-config-reference.md`)](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/01-claude-code-docs.md) | ✅ Complete    | none   |
| 02 | [OpenHands docs (`openhands-setup.md` + `openhands-config-reference.md`)](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/02-openhands-docs.md)         | ✅ Complete    | none   |
| 03 | [`harness-selection.md` + root `README.md` update](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/03-harness-selection-readme.md)                      | ✅ Complete    | none   |
| 04 | [CI isolation + coverage gate extensions](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/04-ci-isolation-coverage.md)                                  | ✅ Complete    | none   |
| 05 | [Milestone closeout + Global acceptance criteria walk](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/05-milestone-closeout.md)                        | ✅ Complete    | none   |

## Key constraints

- Each new doc **mirrors** its OpenClaude counterpart section-for-section — same section order, same table shape, same cross-link discipline — differing only in the per-backend facts (process model, presence signal, auth surface, sandbox).
- `docs/config/claude-code-setup.md` must state the **C7 licensing caveat** explicitly: no confirmed Anthropic ToS language for non-interactive production automation at scale on subscription seats; confirm with Anthropic before using `auth_mode="subscription"` in production. It must not present `subscription` as the default automation path (default is `auto`).
- `docs/config/openhands-setup.md` and the root `README.md` must call out **Docker-on-Windows** as a new operator prerequisite (Aegis SWR is Windows-only; the OpenHands runtime is Docker-sandboxed by default, C8).
- The `grep` CI extension must fail the build on a deliberately introduced cross-family import (e.g. `import aegis_swr.openhands` in `aegis_swr/claude_code/`, or any backend import in `core/`/`views/`/`code_intel/`), and on the OpenHands client library imported outside `openhands/client.py`.
- The coverage gate is enforced in CI configuration, not merely documented: ≥ 90% unit per backend package, 100% branch on each new `tool.py`'s `delegate()`.
- All docs render with zero broken internal links (`python scripts/check_doc_links.py docs/`); absolute-from-repo-root links with a leading `/`, no relative `../../` chains.
- No design in any doc may cause secrets, credentials, or incident payloads to be logged or persisted unredacted (C7, C13).

## Files

```
docs/roadmap/0005-harness-backends/13.0-documentation-ci/
├── README.md                       ← this file
├── 01-claude-code-docs.md          ← claude-code-setup.md + claude-code-config-reference.md
├── 02-openhands-docs.md            ← openhands-setup.md + openhands-config-reference.md
├── 03-harness-selection-readme.md  ← harness-selection.md + root README.md update
├── 04-ci-isolation-coverage.md     ← grep isolation extension + coverage gate extension
└── 05-milestone-closeout.md        ← Global acceptance criteria walk + status.md flip mechanics

Deliverables authored during implementation:
docs/
└── config/                             ← existing category; also home to openclaude-setup.md /
                                           openclaude-config-reference.md (moved here from a bare
                                           docs/ location as part of this milestone)
    ├── claude-code-setup.md            ← NEW (mirrors docs/config/openclaude-setup.md; C7 auth modes + licensing caveat)
    ├── claude-code-config-reference.md ← NEW (mirrors docs/config/openclaude-config-reference.md)
    ├── openhands-setup.md              ← NEW (Docker-on-Windows prerequisite)
    ├── openhands-config-reference.md   ← NEW
    └── harness-selection.md            ← NEW (C2 selection/ambiguity truth table for operators)
README.md (repo root)               ← updated: Docker-on-Windows prerequisite + backend-selection note
.github/workflows/ci.yml            ← updated: isolation grep + per-backend coverage gates
pyproject.toml                      ← updated: per-backend integration markers (if needed)
```
