# Milestone 0005 — Code Intelligence Harness & Multi-Backend Support — Status

Tracks progress against [plan.md](/docs/roadmap/0005-harness-backends/plan.md).
Updated as each task lands.

## Current status

| Task | Name                                          | Status         | Tests |
|------|-----------------------------------------------|----------------|-------|
| 01.0 | Harness Settings & Selection Contract         | ✅ Complete    | `tests/unit/harness/test_exceptions.py`, `tests/unit/harness/test_config.py` |
| 02.0 | Claude Code Settings & Config                 | ✅ Complete    | `tests/unit/claude_code/test_config.py` |
| 03.0 | Claude Code Subprocess Tool                   | ⬜ Not started | —     |
| 04.0 | Claude Code Subscription/Login Authentication | ⬜ Not started | —     |
| 05.0 | Claude Code Events & Exceptions               | ⬜ Not started | —     |
| 06.0 | OpenHands Settings & Config                   | ✅ Complete    | `tests/unit/openhands/test_config.py` |
| 07.0 | OpenHands Client & Process Lifecycle          | ⬜ Not started | —     |
| 08.0 | OpenHands Tool Implementor                    | ⬜ Not started | —     |
| 09.0 | OpenHands Events & Exceptions                 | ⬜ Not started | —     |
| 10.0 | Harness Composition Root & CLI                | ⬜ Not started | —     |
| 11.0 | Test Suite — Unit                             | ⬜ Not started | —     |
| 12.0 | Test Suite — Integration                      | ⬜ Not started | —     |
| 13.0 | Documentation & CI                            | ⬜ Not started | —     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** **in progress — the configuration layer is complete.**
This milestone extends Milestone 0004 (OpenClaude Integration) in its final,
post-remediation state (see
[ADR 0003](/docs/adr/0003-code-intel-composition-root.md)). The full task →
subtask decomposition is complete, and **all three configuration-category tasks
(01.0, 02.0, 06.0) have landed in `src/`** — `harness/`, `claude_code/`, and
`openhands/` now exist as settings-only packages with the C2 selection contract
fully implemented and tested. The remaining ten tasks (the runtime tools,
lifecycle, events, composition root, and docs) are still `⬜ Not started`.

Suite at the close of the configuration layer: **1148 passed, 4 skipped, 90.20%
total coverage** (`uv run pytest -q --cov=aegis_swr`); ruff clean; custom flake8
X-rules clean.

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

- **C3 was amended to allowlist `harness/config.py` (2026-08-24, Task 01.0).**
  C3 originally named `harness/composition.py` as the *only* module permitted to
  import more than one backend family, which C1's nested-settings requirement
  makes impossible — `HarnessSettings` cannot compose three families without
  importing three settings classes. The boundary that actually matters is
  *runtime* isolation, so `harness/config.py` is now permitted **settings-class
  imports only** (no tool/process/client, hence no `grpc` and no OpenHands client
  library). Task 13.0's CI grep check must encode that distinction rather than a
  blanket single-module rule. See the inline amendment note in plan.md C3.

## Decomposition tree

Full task → subtask decomposition is complete (mirroring how Milestone 0004 was
decomposed before implementation). Tasks 01.0, 02.0 and 06.0 are implemented in
`src/`; the remaining ten task READMEs and their subtask files are at planning
granularity only, all states
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

**Status:** ✅ Complete (2026-08-24) — all three subtasks.

_Delivered `harness/exceptions.py` (`HarnessConfigError`, a `ValueError` for
construction-time config-shape ambiguity; `HarnessUnavailableError`, a plain
`Exception` for composition-time capability failure — deliberately separate
hierarchies, `typing`-only leaf module) and `harness/config.py` (`HarnessBackend`
str-enum; `HarnessSettings` composing the `AEGIS_CODE_INTEL_BACKEND` selector with
all three nested per-family settings via `default_factory`, plus the
`presence_signals` / `active_backend` properties and the ambiguity
`model_validator` implementing the full C2 truth table)._

**Implementation decisions of record:**

- **Subtasks were implemented in dependency order 03 → 01 → 02, not table
  order.** Subtask 03's `Blocks` column names 01 and 02 (`config.py` imports the
  exception types), so building the leaf first avoided writing and then
  discarding a forward-declared placeholder.
- **`harness/__init__.py` re-exports only the `typing`-only exception types**, and
  deliberately not `HarnessSettings` (which would pull `pydantic` into the package
  namespace) — mirroring how `openclaude/__init__.py` withholds
  `OpenClaudeTool`/`Process`/`GrpcClient` to keep `grpc` out (C3). Subtask 01's
  spec previously said "empty, versioned"; that wording was corrected to match
  this established package convention.
- **Contract C3 was amended** (see plan.md C3's inline amendment note): its
  original text named `harness/composition.py` as the *only* module permitted to
  import more than one backend family, which C1's own nested-settings requirement
  contradicts. `harness/config.py` is now explicitly allowlisted for
  **settings-class imports only** — no runtime/tool/process/client imports, so no
  `grpc` or client library enters the shared namespace. Task 13.0's CI grep check
  must encode that distinction.
- **`active_backend` returns a bare family `str`**, never the `HarnessBackend`
  member, and `presence_signals` is the single source of truth read off the
  already-constructed nested settings objects — never re-derived from
  `os.environ`.
- **`HarnessUnavailableError` is never raised by `HarnessSettings`.** Per C2 the
  set-selector-with-absent-signal case does not raise at construction; it is
  Task 10.0's composition-time concern.

**Tests:** `tests/unit/harness/test_exceptions.py` (10) and
`tests/unit/harness/test_config.py` (33) — all five C2 truth-table rows including
the `OPENCLAUDE_GRPC_URL`-only Milestone 0004 backward-compatibility guarantee, a
multi-signal ambiguity case involving the boolean `claude_code` signal, an
all-three-signals case, C13 payload-freedom assertions, an AST leaf-module
import-purity scan, and AST C3 guards (no `core`/`views`/`code_intel` import of
`harness.config`; no backend package importing a sibling). Coverage:
`harness/exceptions.py` 100%, `harness/config.py` 94.57%, `harness/__init__.py`
100%.

**Reviews:** `subtask-verifier` PASS on subtask 02, PARTIAL→resolved on 01 and 03
(both deviations fixed). `feature-reviewer` **LGTM**, no blocking issues.
`security-auditor` gate **PASS**, no CRITICAL/HIGH — threat model at
[docs/security/2026-08-24-harness-code-intel-config.md](/docs/security/2026-08-24-harness-code-intel-config.md).

### Task 02.0 — Claude Code Settings & Config

**Status:** ✅ Complete (2026-08-24) — both subtasks. Implemented ahead of its
own loop iteration, as a scoped decision during Task 01.0: `HarnessSettings`
composes `ClaudeCodeSettings` by `default_factory`, and the full class was built
rather than a stub so the C2 selection logic could be exercised against real
objects.

_Delivered `claude_code/config.py` (`ClaudeCodeSettings`, C5/C6): `binary_path`,
the `CLAUDE_CODE_ENABLED` presence signal, read-only `allowed_tools`
(`Read,Grep,Glob`; `Write`/`Edit` warn), `max_turns`, `request_timeout_s`,
non-bypassing `permission_mode`, and the mandatory-when-enabled disposable
`scratch_cwd`. Mirrors `OpenClaudeSettings`' proven machinery per C5 — per-family
`env_prefix`, a CSV `EnvSettingsSource` subclass, `mode="before"` coercion
validators, and the `ValidationError`-unwrap in `__init__`. `ClaudeCodeConfigError`
is forward-declared here; Task 05.0 supplies the canonical definition in
`claude_code/exceptions.py` via a re-export alias with no import-path change.
`auth_mode` is deliberately absent — Task 04.0 extends this class additively._

**Security-review fixes applied in-task:** the `scratch_cwd` validator's three
error reasons no longer interpolate the resolved absolute path (it can carry the
home directory and username), matching the value-free style of the repo-root
branch and the C13 field-names-only rule; and `enabled` gained a `mode="before"`
coercion so an empty/whitespace value — an unset CI secret expands to `""` —
falls back to `False` instead of raising a raw pydantic `bool_parsing` error.
That second fix is load-bearing beyond availability: `CLAUDE_CODE_ENABLED` is the
C2 presence signal `HarnessSettings` reads, so an empty value previously broke the
contract that a zero-config `HarnessSettings()` always constructs.

**Tests:** `tests/unit/claude_code/test_config.py` (32) — defaults, empty-env
coercion, CSV env parsing, the full bypass-permission reject matrix (including the
bare `bypass` spelling and mixed casing), the `scratch_cwd` validation matrix, and
regression tests for both security fixes. Coverage: `claude_code/config.py`
93.67%.

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

**Status:** ✅ Complete (2026-08-24) — both subtasks. Implemented ahead of its own
loop iteration for the same reason as Task 02.0: `HarnessSettings` composes
`OpenHandsSettings` by `default_factory`, so the real class was built rather than
a stub.

_Delivered `openhands/config.py` (`OpenHandsSettings`, C5/C8): the
`OPENHANDS_SERVER_URL` presence signal, `runtime_mode` defaulting to the
Docker-sandboxed runtime, `allowed_tools`, `connect_timeout_s`,
`request_timeout_s`, `auto_start`, and the subtask-02
`allow_unsandboxed_runtime` override. Mirrors `OpenClaudeSettings`' machinery per
C5. `OpenHandsConfigError` is forward-declared here; Task 09.0 supplies the
canonical definition in `openhands/exceptions.py`._

**Two deliberate divergences from the OpenClaude template, both recorded so later
tasks don't "correct" them:**

- **`server_url` requires an `http(s)://` scheme** — the inverse of
  `OpenClaudeSettings.grpc_url`, which rejects a scheme and wants bare
  `host[:port]`. OpenHands is REST/WS, not gRPC.
- **`runtime_mode` needs an explicit `validation_alias="OPENHANDS_RUNTIME"`**,
  because Pydantic's `env_prefix` would otherwise derive `OPENHANDS_RUNTIME_MODE`
  — not the variable name C8 specifies.

**C8 sandbox posture:** enforced by a cross-field `model_validator(mode="after")`
rather than a field default alone, so it fires even when `runtime_mode` arrives
via the environment. A non-sandboxed runtime requires both an explicit runtime
value *and* `allow_unsandboxed_runtime=True`, and logs a loud warning when
overridden; relaxing this permanently requires an ADR per C8.

**Security-review fix applied in-task:** `auto_start` and
`allow_unsandboxed_runtime` gained `mode="before"` coercion so an empty/whitespace
env value (unset CI secret) falls back to `False` rather than raising a raw
pydantic `bool_parsing` error. The fail-safe direction is preserved — an empty
value can never flip the sandbox override permissive.

**Tests:** `tests/unit/openhands/test_config.py` (28) — defaults, empty-env→`None`
coercion, scheme-required URL validation, CSV env parsing, the full
sandbox-enforcement matrix from both the constructor and env paths, and regression
tests for the bool-coercion fix. Coverage: `openhands/config.py` 96.43%.

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
