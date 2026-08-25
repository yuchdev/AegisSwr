# 05 - Milestone closeout + Global acceptance criteria walk

**Parent task:** 13.0 Documentation & CI
**State:** ✅ Complete
**Depends on:** 01, 02, 03, 04 (docs + CI gates in place) and Tasks 01.0–12.0 (all implementation and test tasks delivered).
**Blocks:** none

## Objective

Close Milestone 0005: confirm every task is delivered, walk [plan.md](/docs/roadmap/0005-harness-backends/plan.md)'s "Global
acceptance criteria" checklist item by item recording the evidence for each, flip
all 13 task rows (and their subtasks) to ✅ in `status.md`, and add a
`CHANGELOG.md` entry that references all 13 tasks by number/name and records that
this milestone **extends** (does not supersede) Milestone 0004. This is a
verification-and-record subtask; it produces no product code.

## Changes

### 1. Verify Global acceptance criteria (from plan.md)

Walk **every** bullet of [plan.md](/docs/roadmap/0005-harness-backends/plan.md)'s "Global acceptance criteria" section and
confirm it is met; record the evidence (test / CI job / command) next to each.
The full list, in [plan.md](/docs/roadmap/0005-harness-backends/plan.md) order:

- [ ] `harness/composition.py` is the only module importing more than one backend
      family; each backend imports no sibling — evidence: subtask 04 isolation job
      rules 2 & 3.
- [ ] `core/`, `views/`, `code_intel/` import none of `aegis_swr.openclaude`,
      `aegis_swr.claude_code`, `aegis_swr.openhands`, or `grpc` — evidence:
      subtask 04 rule 1.
- [ ] `code_intel/backend.py`, `agent.py`, `budget.py` byte-for-byte unchanged;
      `CodeResult.token_estimate` keeps its name and `int` type — evidence: `git
      diff` against the 0004 final state / Task 10.0 verification.
- [ ] `openclaude/composition.py` deleted; its C4 logic present verbatim in
      `harness/composition.py` — evidence: Task 10.0 + subtask 04 (job no longer
      references the deleted file).
- [ ] Selector unset plus zero signals → capability unavailable, no exception —
      evidence: Task 11.0 selection-matrix unit test.
- [ ] Selector unset plus exactly one signal → that backend auto-selected;
      `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes — evidence:
      Task 11.0 test + `docs/config/harness-selection.md` §6.
- [ ] Selector unset plus more than one signal → `HarnessConfigError` at
      settings-construction time — evidence: Task 11.0 ambiguity test.
- [ ] Selector set to a backend whose signal is absent → `HarnessUnavailableError`
      at composition/health-check time — evidence: Task 11.0 test.
- [ ] Claude Code task text never appears in the constructed argv — evidence:
      Task 11.0 argv-safety unit test (C6).
- [ ] `--dangerously-skip-permissions` (and any settings value producing it)
      rejected at `ClaudeCodeSettings` validation — evidence: Task 02.0/11.0 test.
- [ ] Claude Code `token_estimate` is the real `usage` sum from the `result`
      message — evidence: Task 03.0/11.0 test (C9).
- [ ] `auth_mode="subscription"` rejects construction when `ANTHROPIC_API_KEY` /
      `ANTHROPIC_AUTH_TOKEN` present, and never passes `--bare` — evidence: Task
      04.0/11.0 auth-mode matrix (C7).
- [ ] `auth_mode="subscription"` honours `CLAUDE_CODE_OAUTH_TOKEN` when set, else
      relies on and health checks a pre-existing `claude login` before first
      `delegate()` — evidence: Task 04.0/11.0 + 12.0 subscription-mode variant.
- [ ] `auth_mode="auto"` adds no extra validation beyond the `claude` binary's own
      precedence — Task 03.0 behavior unchanged when 04.0 is not exercised —
      evidence: Task 11.0 test.
- [ ] No OAuth token, credential-file content, or `ANTHROPIC_API_KEY` value ever
      reaches a log sink, exception message, or `claude_code.auth_failed` payload —
      evidence: Task 11.0 no-secret-in-logs assertions (C7/C13).
- [ ] OpenHands runs in the Docker-sandboxed runtime by default; a non-sandboxed
      runtime requires explicit override — evidence: Task 06.0/11.0 test plus the
      docs' ADR-required-override note (C8).
- [ ] `OpenHandsClient` is the only importer of the OpenHands client library —
      evidence: subtask 04 rule 4.
- [ ] `aegis code-intel check` is backend-agnostic and reports which backend is
      active (or "unavailable") for every selection outcome — evidence: Task
      10.0/11.0 test + `docs/config/harness-selection.md` §5.
- [ ] `agents.yaml` carries `claude_code_agent` and `openhands_agent` roles, each
      `enabled_when` its own presence signal — evidence: Task 10.0 (C11) +
      config-reference docs.
- [ ] `Settings.harness.openclaude` resolves; `Settings.openclaude` no longer
      exists; all consumers migrated — evidence: Task 10.0 (C12).
- [ ] All unit tests pass with `AEGIS_CODE_INTEL_BACKEND` unset, all presence
      signals unset, no `claude`/Docker/OpenHands available — evidence: subtask 04
      hermetic unit jobs.
- [ ] Integration tests skipped (not failed) when a signal/binary/Docker is
      absent; subscription-auth variant additionally skipped without a live login /
      `CLAUDE_CODE_OAUTH_TOKEN` — evidence: subtask 04 integration gating plus Task
      12.0 skip guards.
- [ ] No raw incident payload, argv, or unredacted response/credential text reaches
      any log sink — evidence: Task 11.0 assertions (C13).
- [ ] All new public classes and functions have RST docstrings — evidence: review
      / `ruff` docstring conventions.
- [ ] `ruff` clean; per-backend unit coverage ≥ 90%; 100% branch on each new
      tool's `delegate` — evidence: subtask 04 coverage gates + `ruff check`.

Also confirm (project-wide mandate, not in [plan.md](/docs/roadmap/0005-harness-backends/plan.md)'s list but required by `../CLAUDE.md`)

### 2. Structural / docs gates

- [ ] `aegis_swr/harness/` exists with `__init__.py`, `config.py`,
      `composition.py`, `exceptions.py`.
- [ ] `aegis_swr/claude_code/` exists with `__init__.py`, `config.py`, `tool.py`,
      `process.py`, `events.py`, `exceptions.py`.
- [ ] `aegis_swr/openhands/` exists with `__init__.py`, `config.py`, `client.py`,
      `process.py`, `tool.py`, `events.py`, `exceptions.py`.
- [ ] `openclaude/composition.py` is **absent** (deleted, Task 10.0).
- [ ] `tests/unit/{harness,claude_code,openhands}/` and
      `tests/integration/{claude_code,openhands}/` exist.
- [ ] `docs/config/claude-code-setup.md`, `docs/config/claude-code-config-reference.md`,
      `docs/config/openhands-setup.md`, `docs/config/openhands-config-reference.md`, and
      `docs/config/harness-selection.md` exist and are linked from `docs/README.md`.
- [ ] Root `README.md` carries the Docker-on-Windows line and the
      backend-selection pointer.
- [ ] `python scripts/check_doc_links.py docs/` passes (zero broken links).

### 3. Flip status.md to ✅ (action item for the implementer)

> **Note:** this closeout subtask does **not** edit `status.md` in the current
> decomposition pass — that tracker is maintained centrally. When this subtask is
> executed during implementation, the action is: flip all 13 task rows (01.0–13.0)
> in
> [docs/roadmap/0005-harness-backends/status.md](/docs/roadmap/0005-harness-backends/status.md)
> from ⬜ to ✅ in the `## Current status` table (and fill each row's Tests
> column), flip each subtask's `**State:**`/`Status` line in every task directory's
> README and subtask files to ✅, fill each task's "Delivered" / "Test coverage"
> notes in the `## Per-task detail` section, and update the
> `**Current gate status:**` line to reflect completion. Because this milestone
> introduced full task → subtask decomposition after planning, the flip must walk
> **both** the task rows **and** every subtask file's state marker, not just the
> summary table.

### 4. CHANGELOG.md entry

Add an `[Unreleased]` (or dated milestone) entry that:

- Names all 13 tasks by number and name:
  - 01.0 Harness Settings & Selection Contract
  - 02.0 Claude Code Settings & Config
  - 03.0 Claude Code Subprocess Tool
  - 04.0 Claude Code Subscription/Login Authentication
  - 05.0 Claude Code Events & Exceptions
  - 06.0 OpenHands Settings & Config
  - 07.0 OpenHands Client & Process Lifecycle
  - 08.0 OpenHands Tool Implementor
  - 09.0 OpenHands Events & Exceptions
  - 10.0 Harness Composition Root & CLI
  - 11.0 Test Suite — Unit
  - 12.0 Test Suite — Integration
  - 13.0 Documentation & CI
- Records that Milestone 0005 **extends, does not supersede,** Milestone 0004
  (plan.md's opening note): the `CodeIntelBackend` ABC, `CodeAgent`, and
  `CallBudget` stay untouched; OpenClaude is unchanged except that
  `openclaude/composition.py` is deleted and its logic generalized into
  `harness/composition.py` (ADR 0004). Summarize, from [status.md](/docs/roadmap/0005-harness-backends/status.md) "Notes &
  decisions", only the accurate record — do not invent detail:
  - Single-active-backend, no fallback chain (user-confirmed); selection via
    `AEGIS_CODE_INTEL_BACKEND` + presence signals, ambiguity is a loud
    `HarnessConfigError`.
  - Two new first-class backends: Claude Code (`claude` CLI, one-shot subprocess,
    real token accounting, two auth modes per C7 with the licensing caveat) and
    OpenHands (Docker-sandboxed REST/WS sidecar).
  - 0004's closing guarantee preserved: an `OPENCLAUDE_GRPC_URL`-only deployment
    needs zero changes.
  - Breaking rename `Settings.openclaude` → `Settings.harness.openclaude` (C12).

Draft skeleton:

```markdown
## [Unreleased] — Milestone 0005: Code Intelligence Harness & Multi-Backend Support

### Added
- A neutral `harness/` selection + composition layer and two new Code Intelligence
  backends — Claude Code (`claude` CLI, one-shot subprocess) and OpenHands
  (Docker-sandboxed REST/WS sidecar) — behind the unchanged `CodeIntelBackend`
  ABC. Delivered across tasks 01.0 Harness Settings & Selection Contract, 02.0–05.0
  Claude Code (Settings, Subprocess Tool, Subscription/Login Auth, Events), 06.0–09.0
  OpenHands (Settings, Client & Process, Tool, Events), 10.0 Harness Composition
  Root & CLI, 11.0 Unit Tests, 12.0 Integration Tests, and 13.0 Documentation & CI.
- Single-active-backend selection via `AEGIS_CODE_INTEL_BACKEND` + per-family
  presence signals, with zero Python changes.

### Changed
- Extends (does not supersede) Milestone 0004: `CodeIntelBackend`, `CodeAgent`,
  `CallBudget` untouched; `openclaude/composition.py` deleted and its C4 logic
  generalised into `harness/composition.py` (ADR 0004).
- Breaking rename: `Settings.openclaude` → `Settings.harness.openclaude` (C12).

### Notes
- `auth_mode="subscription"` for Claude Code ships opt-in only, pending
  confirmation with Anthropic of the licensing terms for non-interactive
  production automation at scale (C7).
```

## Constraints
- Does not itself edit `status.md` in this decomposition pass (describe the flip —
  of both task rows and every subtask state marker — as an implementer action
  item only).
- The `CHANGELOG.md` entry must name all 13 tasks and record that 0005 **extends**
  (not supersedes) 0004.
- Historical record summarized from [status.md](/docs/roadmap/0005-harness-backends/status.md) "Notes & decisions" — no invented
  detail.
- `python scripts/check_doc_links.py docs/` must pass after any doc/link updates.

## Success criteria
- [ ] Every [plan.md](/docs/roadmap/0005-harness-backends/plan.md) Global acceptance criterion confirmed met with recorded evidence (all bullets walked, in order).
- [ ] `ruff check src/ tests/` - clean.
- [ ] Structural plus docs gates confirmed.
- [ ] Implementer action item to flip all 13 `status.md` rows **and** every subtask state marker to ✅ is stated.
- [ ] `CHANGELOG.md` entry names all 13 tasks (01.0–13.0) and records that 0005 extends (not supersedes) Milestone 0004, incl. the C12 rename and the C7 licensing caveat.
- [ ] No invented historical detail; record matches [status.md](/docs/roadmap/0005-harness-backends/status.md) "Notes & decisions".
