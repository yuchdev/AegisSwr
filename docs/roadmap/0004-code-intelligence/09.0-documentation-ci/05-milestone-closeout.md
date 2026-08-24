# 05 - Milestone closeout + CHANGELOG.md

**Parent task:** 09.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01, 02, 03, 04 (docs + CI gates in place) and Tasks 01.0–08.0 (all implementation + test tasks delivered).
**Blocks:** none

## Objective

Close Milestone 0004: confirm every task is delivered, walk the plan.md "Global
acceptance criteria" checklist item by item, flip all nine task rows to ✅ in
`status.md`, and add a `CHANGELOG.md` entry that references all nine tasks by
number/name and records that this milestone supersedes the original (now-deleted)
"Code Intelligence Layer" design. This is a verification-and-record subtask; it
produces no product code.

## Changes

### 1. Verify Global acceptance criteria (from plan.md)

Walk each item in plan.md's "Global acceptance criteria" section and confirm it
is met; record the evidence (test/CI job/command) next to each:

- [ ] `import grpc` appears in exactly one file: `aegis/openclaude/grpc/client.py`
      — evidence: `openclaude-isolation` CI job (subtask 03).
- [ ] `aegis/core/`, `aegis/ui/`, `aegis/code_intel/` import neither
      `aegis.openclaude` nor `grpc` — evidence: subtask 03 rule 1.
- [ ] `OpenClaudeTool` is instantiated/registered only when `OPENCLAUDE_GRPC_URL`
      is set; absent it, code-intel capability reports unavailable (C4).
- [ ] All unit tests pass with `OPENCLAUDE_GRPC_URL` unset and no binary on `PATH`
      — evidence: `openclaude-unit-coverage` job (subtask 04).
- [ ] Integration tests are **skipped** (not failed) when binary/env var absent.
- [ ] `python -m aegis.app --dry-run` completes with no API keys, no
      `OPENCLAUDE_GRPC_URL`, and no OpenClaude binary.
- [ ] `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL` set does not
      open a gRPC connection.
- [ ] `OpenClaudeTool` enforces `bash_allowlist`; a non-allowlisted
      `PERMISSION_REQ` is denied without corrupting boundary budget accounting.
- [ ] Token budget is charged after stream completion, not pre-charged (C5).
- [ ] Adding OpenClaude requires only setting `OPENCLAUDE_GRPC_URL` — zero Python
      changes.
- [ ] No raw incident payload or unredacted response text reaches any log sink.
- [ ] All new public classes/functions have RST docstrings.
- [ ] `ruff`, `replace_optional.py --check` all clean.
- [ ] Coverage: ≥ 90% overall unit; 100% on `tool.py` — evidence: subtask 04 gates.
- [ ] Proto schema committed; `uv run python scripts/proto_gen.py` reproduces identical output.

### 2. Structural / docs gates

- [ ] `aegis/openclaude/` exists with `__init__.py`, `config.py`, `tool.py`,
      `process.py`, `events.py`, `exceptions.py`, and `grpc/{client.py,proto/}`.
- [ ] `aegis/code_intel/` scaffolding exists (`backend.py`, `agent.py`, `budget.py`).
- [ ] `tests/openclaude/unit/` and `tests/openclaude/integration/` exist.
- [ ] `docs/config/openclaude-setup.md` and `docs/config/openclaude-config-reference.md` exist
      and are linked from `docs/README.md`.
- [ ] `python scripts/check_doc_links.py docs/` passes (zero broken links).

### 3. Flip status.md to ✅ (action item for the implementer)

> **Note:** this closeout subtask does **not** edit `status.md` in the current
> decomposition pass — that tracker is maintained centrally. When this subtask is
> executed during implementation, the action is: flip all nine task rows (01.0–09.0)
> in
> [docs/roadmap/0004-code-intelligence/status.md](/docs/roadmap/0004-code-intelligence/status.md)
> from ⬜ to ✅ in the `## Current status` table, fill each task's "Delivered" and
> "Test coverage" lines in the Per-task detail section, and update the
> `**Current gate status:**` line to reflect completion.

### 4. CHANGELOG.md entry

Add an `[Unreleased]` (or dated milestone) entry that:

- Names all nine tasks by number and name:
  - 01.0 OpenClaude Settings & Config
  - 02.0 gRPC Proto & Client
  - 03.0 Process Lifecycle Manager
  - 04.0 OpenClaudeTool Implementor
  - 05.0 Event Types & Exceptions
  - 06.0 App Wiring & agents.yaml
  - 07.0 Test Suite — Unit
  - 08.0 Test Suite — Integration
  - 09.0 Documentation & CI
- Records that Milestone 0004 (OpenClaude Integration) **supersedes** the original
  "Code Intelligence Layer" milestone. Summarise, from the "Notes & decisions"
  section of
  [docs/roadmap/0004-code-intelligence/status.md](/docs/roadmap/0004-code-intelligence/status.md),
  only the accurate historical record — do not invent detail:
  - Decided 2026-07-05: OpenClaude promoted from an optional fallback `CodeTool`
    to the central Code Intelligence mechanism.
  - The bespoke tool-per-capability design (`gtags` / `zoekt` / `tree-sitter`
    indices, six hand-built tools, a custom `ReActLoop`) is cancelled as duplicate
    effort; OpenClaude's own internal agentic loop provides the same navigation
    via `Bash`.
  - Accepted trade-off: token accounting degrades to a boundary estimate and
    correlation becomes model-driven rather than deterministic.
  - The superseded design is referenced at
    `docs/roadmap/0004-code-intelligence-layer/plan.md` (code span, not a live
    link: that path is referenced by plan.md/status.md but is absent on disk —
    see the inconsistency flagged in the closeout report).

Draft skeleton:

```markdown
## [Unreleased] — Milestone 0004: OpenClaude Integration

### Added
- OpenClaude as the central Code Intelligence backend (gRPC sidecar), delivered
  across tasks 01.0 Settings & Config, 02.0 gRPC Proto & Client, 03.0 Process
  Lifecycle Manager, 04.0 OpenClaudeTool Implementor, 05.0 Event Types &
  Exceptions, 06.0 App Wiring & agents.yaml, 07.0 Unit Test Suite, 08.0
  Integration Test Suite, and 09.0 Documentation & CI.
- Enable via `OPENCLAUDE_GRPC_URL` with zero Python changes.

### Changed
- Supersedes the original "Code Intelligence Layer" milestone (decided
  2026-07-05): the bespoke tool-per-capability design is cancelled in favour of
  OpenClaude's own agentic loop. Trade-off accepted: boundary-estimate token
  accounting and model-driven (non-deterministic) correlation.
```

## Constraints
- Does not itself edit `status.md` in this decomposition pass (describe the flip
  as an implementer action item only).
- The `CHANGELOG.md` entry must name all nine tasks and record the supersession.
- Historical record must be summarised from status.md "Notes & decisions" — no
  invented details.
- `python scripts/check_doc_links.py docs/` must pass after any doc/link updates.

## Success criteria
- [ ] Every plan.md Global acceptance criterion confirmed met with recorded evidence.
- [ ] Structural + docs gates confirmed.
- [ ] Implementer action item to flip all nine `status.md` rows to ✅ is stated.
- [ ] `CHANGELOG.md` entry names all nine tasks (01.0–09.0) and records the
      supersession of the original Code Intelligence Layer milestone.
- [ ] No invented historical detail; record matches status.md "Notes & decisions".
