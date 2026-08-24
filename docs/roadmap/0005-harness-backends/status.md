# Milestone 0005 — Code Intelligence Harness & Multi-Backend Support — Status

Tracks progress against [plan.md](/docs/roadmap/0005-harness-backends/plan.md).
Updated as each task lands.

## Current status

| Task | Name                                          | Status         | Tests |
|------|-----------------------------------------------|----------------|-------|
| 01.0 | Harness Settings & Selection Contract         | ⬜ Not started | —     |
| 02.0 | Claude Code Settings & Config                 | ⬜ Not started | —     |
| 03.0 | Claude Code Subprocess Tool                   | ⬜ Not started | —     |
| 04.0 | Claude Code Subscription/Login Authentication | ⬜ Not started | —     |
| 05.0 | Claude Code Events & Exceptions               | ⬜ Not started | —     |
| 06.0 | OpenHands Settings & Config                   | ⬜ Not started | —     |
| 07.0 | OpenHands Client & Process Lifecycle          | ⬜ Not started | —     |
| 08.0 | OpenHands Tool Implementor                    | ⬜ Not started | —     |
| 09.0 | OpenHands Events & Exceptions                 | ⬜ Not started | —     |
| 10.0 | Harness Composition Root & CLI                | ⬜ Not started | —     |
| 11.0 | Test Suite — Unit                             | ⬜ Not started | —     |
| 12.0 | Test Suite — Integration                      | ⬜ Not started | —     |
| 13.0 | Documentation & CI                            | ⬜ Not started | —     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** **not started.** This milestone extends Milestone 0004
(OpenClaude Integration) in its final, post-remediation state (see
[ADR 0003](/docs/adr/0003-code-intel-composition-root.md)). No `src/` work has
begun; the full task → subtask decomposition below is now complete (matching
how 0004 was decomposed before implementation), but every subtask remains
`⬜ Not started` until `python-expert`/`testing-expert` pick up implementation.

**Design decision of record:** the composition-root generalisation (moving the
C4 branch out of `openclaude/composition.py` into a neutral `harness/` package)
is recorded in [ADR 0004](/docs/adr/0004-harness-composition-generalization.md),
which directly extends [ADR 0003](/docs/adr/0003-code-intel-composition-root.md).

## Notes & decisions

- **Research finding — there was never a documented second backend
  (established 2026-08-19).** No open-source alternative to OpenClaude is
  documented anywhere in the existing milestones or their git history. This was
  checked directly: `docs/roadmap/` (all plans and statuses), the deleted
  pre-supersession `0004-code-intelligence-layer/plan.md`, and a full
  `git log -p` sweep of `docs/` for `OpenHands` / `Aider` / `SWE-agent` /
  `Goose` / `Cline` and similar — **zero hits**. The only previously-named
  alternative is "stock Claude Code MCP"
  ([0004 status.md line 127](/docs/roadmap/0004-code-intelligence/status.md):
  "OpenClaude chosen over stock Claude Code MCP…"), which this milestone now adds
  as its own first-class `claude_code` backend. The user was asked to pick a
  researched third backend and chose **OpenHands** (Apache-2.0, LiteLLM-internal
  — an echo of Milestone 0003 — and Docker-sandboxed by default, which fits Aegis
  SWR's "treat every incident payload as hostile" posture better than a
  host-permission subprocess). Aider / Goose / SWE-agent were considered and
  rejected (see [plan.md](/docs/roadmap/0005-harness-backends/plan.md)'s "Alternatives considered" table).

- **Single-active-backend, no fallback chain (user-confirmed).** Generalises
  0004's C4 ("no sibling backends to fall back to"). `AEGIS_CODE_INTEL_BACKEND`
  explicitly selects the active backend; when unset, exactly one presence signal
  auto-selects; more than one signal is a **loud** `HarnessConfigError` at
  settings-construction time (never a silent pick); an explicitly-selected
  backend whose signal is absent is a `HarnessUnavailableError` at
  composition/health-check time. See [plan.md](/docs/roadmap/0005-harness-backends/plan.md) C2 for the full truth table.

- **0004's closing guarantee is preserved.** An existing
  `OPENCLAUDE_GRPC_URL`-only deployment (selector unset, exactly one signal)
  auto-selects OpenClaude and needs **zero further changes**.

- **Claude Code presence is an explicit opt-in.** `CLAUDE_CODE_ENABLED=true` —
  being on `PATH` alone must NOT silently enable it, because that is a weaker,
  more accidental trigger than a configured URL and silent activation of a
  host-permission backend violates the hostile-payload posture.

- **Argv-safety is a new, Claude-Code-specific contract.** Task text must never
  appear in argv (visible via `ps` on a shared host); it is passed via stdin or a
  disposable temp file. This extends "never log secrets" to "never argv secrets"
  (plan.md C6).

- **Real token accounting is a genuine gain over 0004's C5.** Claude Code's
  `stream-json` `result` message carries actual `usage.input_tokens` /
  `usage.output_tokens`; the backend uses them directly while keeping
  `CodeResult.token_estimate`'s field shape unchanged so `CodeAgent` stays
  backend-agnostic (plan.md C9).

- **Claude Code supports subscription-login (non-API-key) automation —
  established 2026-08-19, added as Task 04.0.** Researched directly against the
  official Claude Code documentation (Authentication and Headless/Non-Interactive
  Mode references). Findings, precisely:
  - `claude login` (interactive, once) persists a reusable OAuth session to the
    OS keychain (macOS) or a credentials file (Linux: `~/.claude/.credentials.json`;
    **Windows** — Aegis SWR's target platform —
    `%USERPROFILE%\.claude\.credentials.json`), separate from `ANTHROPIC_API_KEY`.
  - `claude setup-token` mints a **long-lived (~1 year) `CLAUDE_CODE_OAUTH_TOKEN`**
    specifically for non-interactive/CI use, printed to stdout once, requiring no
    `ANTHROPIC_API_KEY`. This is the recommended automation path.
  - Headless (`-p`) mode does **not** unconditionally prefer the API key: it
    follows a documented precedence (cloud-provider creds → `ANTHROPIC_AUTH_TOKEN`
    → `ANTHROPIC_API_KEY` → `apiKeyHelper` → `CLAUDE_CODE_OAUTH_TOKEN` → profile/
    federation creds → stored `claude login` session, lowest). So a subscription
    login **is** usable headlessly, but a stray `ANTHROPIC_API_KEY` in the
    environment silently overrides it — Task 04.0 exists specifically to make
    that failure mode loud instead of silent.
  - `--bare` mode (reproducible-CI mode) **never** reads OAuth/login credentials
    at all — incompatible with subscription-mode by design; the tool must not
    pass `--bare` when `auth_mode="subscription"`.
  - **Open licensing question, explicitly not resolved by this milestone:** no
    documented Anthropic ToS language was found distinguishing personal
    (Pro/Max) from organizational (Team/Enterprise) subscription seats for
    non-interactive production automation at scale. Task 13.0's setup guide must
    flag this and recommend confirming with Anthropic before production use;
    `auth_mode` therefore defaults to `auto` and ships `subscription` as
    opt-in only.
  - See [plan.md](/docs/roadmap/0005-harness-backends/plan.md) C7 for the full contract (the `auth_mode` field, the
    settings-construction-time rejection of an ambiguous `ANTHROPIC_API_KEY` +
    `subscription` combination, and the startup auth-probe).

- **`Settings.openclaude` → `Settings.harness.openclaude` is a deliberate
  breaking rename** (plan.md C12), accepted under the same tolerance the codebase
  applied to ADR 0003's `CodeBackend` → `CodeIntelBackend` rename. Migration path
  is named in task 10.0.

- **Docker-on-Windows is a new operator prerequisite** for the OpenHands backend
  only (the product is Windows-only per `../CLAUDE.md`); flagged for the root
  `README.md` system-requirements area in task 13.0.

## Decomposition tree

Full task → subtask decomposition is complete (mirroring how Milestone 0004 was
decomposed before implementation). No `src/` work has begun on any task — every
task README and subtask file below is at planning granularity only, all states
`⬜ Not started`.

```
docs/roadmap/0005-harness-backends/
├── plan.md                                                                        ← milestone spec (13 tasks, contracts C1–C13)
├── status.md                                                                      ← this tracker
├── 01.0-harness-settings/           README.md (3 subtasks)                        ← configuration (C1, C2)
├── 02.0-claude-code-settings/       README.md (2 subtasks)                        ← configuration (C5, C6)
├── 03.0-claude-code-tool/           README.md (4 subtasks)                        ← infrastructure (argv-safety, NDJSON, real tokens)
├── 04.0-claude-code-auth/           README.md (3 subtasks)                        ← configuration (C7: subscription login vs API key)
├── 05.0-claude-code-events/         README.md (2 subtasks)                        ← infrastructure (C10)
├── 06.0-openhands-settings/         README.md (2 subtasks)                        ← configuration (C5, C8)
├── 07.0-openhands-client-process/   README.md (2 subtasks)                        ← infrastructure (sidecar lifecycle)
├── 08.0-openhands-tool/             README.md (2 subtasks)                        ← infrastructure (CodeIntelBackend impl)
├── 09.0-openhands-events/           README.md (2 subtasks)                        ← infrastructure (C10)
├── 10.0-harness-composition-cli/    README.md (4 subtasks)                        ← integration (C4, C11, C12; deletes openclaude/composition.py)
├── 11.0-test-suite-unit/            README.md (4 subtasks)                        ← testing (unit)
├── 12.0-test-suite-integration/     README.md (3 subtasks)                        ← testing (integration)
└── 13.0-documentation-ci/           README.md (5 subtasks)                        ← documentation & closeout
```

Per-task READMEs:
[01.0](/docs/roadmap/0005-harness-backends/01.0-harness-settings/README.md) ·
[02.0](/docs/roadmap/0005-harness-backends/02.0-claude-code-settings/README.md) ·
[03.0](/docs/roadmap/0005-harness-backends/03.0-claude-code-tool/README.md) ·
[04.0](/docs/roadmap/0005-harness-backends/04.0-claude-code-auth/README.md) ·
[05.0](/docs/roadmap/0005-harness-backends/05.0-claude-code-events/README.md) ·
[06.0](/docs/roadmap/0005-harness-backends/06.0-openhands-settings/README.md) ·
[07.0](/docs/roadmap/0005-harness-backends/07.0-openhands-client-process/README.md) ·
[08.0](/docs/roadmap/0005-harness-backends/08.0-openhands-tool/README.md) ·
[09.0](/docs/roadmap/0005-harness-backends/09.0-openhands-events/README.md) ·
[10.0](/docs/roadmap/0005-harness-backends/10.0-harness-composition-cli/README.md) ·
[11.0](/docs/roadmap/0005-harness-backends/11.0-test-suite-unit/README.md) ·
[12.0](/docs/roadmap/0005-harness-backends/12.0-test-suite-integration/README.md) ·
[13.0](/docs/roadmap/0005-harness-backends/13.0-documentation-ci/README.md)

## Per-task detail

_Filled in as tasks complete. "Done" tracks implementation, not spec-writing._

### Task 01.0 — Harness Settings & Selection Contract

**Status:** ⬜ Not started

_Delivers `harness/config.py` (`HarnessSettings`: selector + nested per-family
settings, C1) and `harness/exceptions.py` (`HarnessConfigError`,
`HarnessUnavailableError`). Implements the C2 selection/ambiguity resolution at
settings-construction time. Foundation every other task depends on for settings
shape._

### Task 02.0 — Claude Code Settings & Config

**Status:** ⬜ Not started

_Delivers `claude_code/config.py` (`ClaudeCodeSettings`, C5/C6): binary path,
read-only `allowed_tools`, non-bypassing `permission_mode`, `max_turns`,
`request_timeout_s`, mandatory disposable `scratch_cwd`, and the
`CLAUDE_CODE_ENABLED` presence signal. Rejects `--dangerously-skip-permissions`._

### Task 03.0 — Claude Code Subprocess Tool

**Status:** ⬜ Not started

_Delivers `claude_code/tool.py` + `claude_code/process.py`: one-shot
`claude -p … --output-format stream-json` per `delegate()`, argv-safety
(task via stdin/temp file, never argv), NDJSON stream parse, real token
accounting from the terminal `result` message (C6, C9), budget pre-check, and
dry-run short-circuit._

### Task 04.0 — Claude Code Subscription/Login Authentication

**Status:** ⬜ Not started

_Delivers the `auth_mode` field on `ClaudeCodeSettings` (`auto` / `api_key` /
`subscription`, C7), the settings-construction-time rejection of an ambiguous
`ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` + `subscription` combination, the
`--bare`-never-in-subscription-mode rule, `CLAUDE_CODE_OAUTH_TOKEN` support as
the CI-friendly credential path, and a startup auth-probe in
`claude_code/tool.py`/`process.py` surfaced through `aegis code-intel check`
and distinguished from config errors via `ClaudeCodeUnavailableError`. Depends
on Task 03.0 (extends the same subprocess invocation path). Ships
`auth_mode="auto"` as the default; `subscription` mode is opt-in pending the
licensing confirmation noted above._

### Task 05.0 — Claude Code Events & Exceptions

**Status:** ⬜ Not started

_Delivers `claude_code/events.py` (the `claude_code.*` `DomainEvent` taxonomy
including `auth_failed`, C10) and `claude_code/exceptions.py` (typed
config/unavailable/permission/auth errors)._

### Task 06.0 — OpenHands Settings & Config

**Status:** ⬜ Not started

_Delivers `openhands/config.py` (`OpenHandsSettings`, C5/C8): `server_url`
presence signal, Docker-sandboxed runtime mode by default, allowlist, timeouts,
`auto_start`._

### Task 07.0 — OpenHands Client & Process Lifecycle

**Status:** ⬜ Not started

_Delivers `openhands/client.py` (sole importer of the OpenHands HTTP/WS client,
C3) and `openhands/process.py` (sidecar lifecycle mirroring `OpenClaudeProcess`
/ 0004 C6)._

### Task 08.0 — OpenHands Tool Implementor

**Status:** ⬜ Not started

_Delivers `openhands/tool.py` (`OpenHandsTool`, the `CodeIntelBackend`):
Action/Observation event stream → `CodeResult`, budget, dry-run (C8, C9)._

### Task 09.0 — OpenHands Events & Exceptions

**Status:** ⬜ Not started

_Delivers `openhands/events.py` (the `openhands.*` `DomainEvent` taxonomy, C10)
and `openhands/exceptions.py`._

### Task 10.0 — Harness Composition Root & CLI

**Status:** ⬜ Not started

_Delivers `harness/composition.py` (`create_code_intel_backend`, the sole C4
branch across all three backends); deletes `openclaude/composition.py`; makes
`aegis code-intel check` backend-agnostic (reports which backend is active,
including Claude Code's resolved auth mode); adds `claude_code_agent` /
`openhands_agent` roles to `agents.yaml` (C11); and performs the
`Settings.openclaude` → `Settings.harness.openclaude` breaking rename (C12).
Depends on all of 01.0–09.0._

### Task 11.0 — Test Suite — Unit

**Status:** ⬜ Not started

_Per-backend mock suites; per-package isolation grep/pytest tests extending the
0004 `openclaude-isolation` pattern; the C2 selection-ambiguity matrix; the C7
auth-mode matrix (ambiguous-credential rejection, `--bare` exclusion,
`CLAUDE_CODE_OAUTH_TOKEN` precedence, no-secret-in-logs assertions). Written
incrementally alongside 01.0–10.0._

### Task 12.0 — Test Suite — Integration

**Status:** ⬜ Not started

_Live per-backend suites, skipped by default, gated on each backend's presence
signal + binary/Docker availability (matching 0004's skip-guard pattern); the
Claude Code subscription-mode variant additionally skipped without a live
`claude login` session or `CLAUDE_CODE_OAUTH_TOKEN`._

### Task 13.0 — Documentation & CI

**Status:** ⬜ Not started

_Per-backend setup + config-reference docs (mirroring `docs/config/openclaude-setup.md`
and `docs/config/openclaude-config-reference.md`), the operator-facing
`harness-selection.md`, the Docker-on-Windows prerequisite in the root
`README.md`, the C7 licensing caveat in `docs/config/claude-code-setup.md`, and CI
isolation/coverage gate extensions. Closes the milestone._
