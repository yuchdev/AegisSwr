# Milestone 0004 — OpenClaude Integration — Status

Tracks progress against [plan.md](/docs/roadmap/0004-code-intelligence/plan.md).
Updated as each task lands.

## Current status

| Task | Name                         | Status         | Tests |
|------|------------------------------|----------------|-------|
| 01.0 | OpenClaude Settings & Config | ✅ Complete | `tests/unit/openclaude/test_config.py` (26), `tests/unit/router/` (24) |
| 02.0 | gRPC Proto & Client          | ⬜ Not started  | -     |
| 03.0 | Process Lifecycle Manager    | ⬜ Not started  | -     |
| 04.0 | OpenClaudeTool Implementor   | ⬜ Not started  | -     |
| 05.0 | Event Types & Exceptions     | ⬜ Not started  | -     |
| 06.0 | App Wiring & agents.yaml     | ⬜ Not started  | -     |
| 07.0 | Test Suite — Unit            | ⬜ Not started  | -     |
| 08.0 | Test Suite — Integration     | ⬜ Not started  | -     |
| 09.0 | Documentation & CI           | ⬜ Not started  | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** full task → subtask decomposition complete;
implementation not started. Each of the nine tasks has a `README.md` carrying
its scope, a linked subtask table, and constraints, plus numbered subtask spec
files (39 total) with concrete file/class/method targets and success criteria.
No `aegis/openclaude/` or `aegis/code_intel/` module exists yet; `app.py` has
no code-backend registration path; `agents.yaml` has no `openclaude_agent`
role.

**Decomposition review found several cross-cutting design gaps that should be
resolved before implementation starts** (not fixed in this pass — they are
genuine architecture decisions, not typos):

- **Package path mismatch.** Every task in this milestone (and 0003 before it)
  is written against a module root of `aegis/...`; the real package is
  `src/aegis_swr/...`. This is pre-existing across the roadmap tree, not new to
  0004, but it means every file path in every subtask doc needs translating at
  implementation time.
- **`CodeBackend` name collision.** `src/aegis_swr/backends/base.py` already
  defines an unrelated `CodeBackend` (the VCS/git-history backend). Task 06.0's
  new code-intelligence `CodeBackend` contract reuses the same name in a
  different module — a real import-confusion risk; consider renaming the new
  one (e.g. `CodeIntelBackend`).
- **Method name/shape drift for the delegation entry point.** plan.md's
  Architecture diagram specifies `delegate(task) → CodeResult`; Tasks 04.0 and
  07.0 use `run(task, ctx)` with a `ToolContext` that no task formally defines.
  Task 06.0 (which owns `aegis/code_intel/backend.py`) needs to settle the
  method name, signature, and the context type's home before 04.0/07.0 can be
  implemented as written.
- **TLS/secure-channel selection has no backing settings field.** Task 02.0
  says the gRPC channel goes secure "when the URL is `https`"; Task 01.0's
  `OpenClaudeSettings.grpc_url` validator explicitly *rejects* scheme-prefixed
  URLs. Neither a URL scheme nor a `use_tls`-style field currently exists to
  drive this — C1 needs an explicit TLS field, or the milestone should commit
  to insecure-only for now.
- **Permission-enforcement ownership conflict (C2 vs Task 04.0).** C2 places
  allowlist enforcement for `PERMISSION_REQ` frames in the gRPC client; Task
  04.0's subtasks (following its own README, which is authoritative per this
  decomposition pass) place it in `OpenClaudeTool`. Pick one owner.
- **EventBus integration model unconfirmed.** The live `EventBus`
  (`src/aegis_swr/core/events.py`) dispatches by `DomainEvent` subclass +
  `type[DomainEvent]`; the Milestone 0003 pattern this milestone's event specs
  follow assumes bus dispatch by an `event_type` string on a plain frozen
  dataclass. As written, the new `OpenClaude*` events may not actually be
  deliverable on the real bus without subclassing `DomainEvent`.
- Smaller items: no `OpenClaudeGrpcClient.from_url(...)` constructor is
  defined anywhere but Task 08.0's live fixtures need one; `AgentConfig.provider`
  was missing from Task 01.0 subtask 03's original draft (fixed in this pass);
  C7's external-mode allowlist probe has no dedicated subtask; plan.md's
  dependency graph is missing a 05.0 → 02.0 edge (`client.py` imports
  `OpenClaudeUnavailableError` from 05.0).

See each task's numbered subtask files for where these are flagged inline.

## Notes & decisions

- **Supersedes Milestone 0004 (decided 2026-07-05).** OpenClaude is promoted
  from an optional fallback `CodeTool` to the central Code Intelligence
  mechanism. The bespoke tool-per-capability design in 0004 (`gtags` / `zoekt` /
  `tree-sitter` indices, six hand-built tools, a custom `ReActLoop`) is
  cancelled as duplicate effort — OpenClaude's own internal agentic loop
  provides the same navigation via `Bash`. Consequently 0004 now depends only
  on 0003, becomes the sole backend behind `aegis/code_intel/`, and stands up a
  minimal generic scaffolding (a `CodeBackend` contract, a `CodeAgent` entry
  point, and boundary-level `CallBudget` accounting) folded into task 06.0. The
  trade-off is accepted knowingly: token accounting degrades to a boundary
  estimate and correlation becomes model-driven rather than deterministic (see
  plan.md's Background and Communication-architecture sections — a planned
  standalone `topology-notes.md` was never written; the topology analysis
  lives inline in plan.md's "three viable topologies" section instead).
- **OpenClaude chosen** over stock Claude Code MCP because it supports
  user-supplied backends (any OpenAI-compatible endpoint, including the
  project's own vLLM instance on Vast.ai) via environment variables, and
  exposes a headless gRPC service that is a better fit for Aegis SWR's async
  architecture than stdio MCP transport.
- **gRPC over MCP.** The headless gRPC stream maps directly onto the
  `EventBus`, allows per-frame `OpenClaudeToolCall` / `OpenClaudeToolResult`
  emissions, and produces a mockable client stub without running a live Node.js
  process in unit tests. MCP-over-stdio would require managing subprocess
  lifetime inside async test fixtures.
- **Additive to existing modules, plus minimal new scaffolding.** This
  milestone modifies two existing files (`app.py`, `agents.yaml`), extends one
  existing module (`aegis/router/config.py` for `enabled_when`), and stands up a
  new, deliberately thin `aegis/code_intel/` package (backend contract,
  `CodeAgent`, `CallBudget`) that 0004 would otherwise have supplied. No
  existing router or agent behaviour is modified. If `OPENCLAUDE_GRPC_URL` is
  unset, no code backend is registered and code-intelligence capability is
  simply unavailable.
- **Tool allowlist is non-negotiable.** The default allowlist (`Read, Grep,
  Glob, Bash`) with a bash allowlist (`gtags, global, semgrep, rg, find, cat`)
  ensures OpenClaude cannot mutate the repository being analysed. Forensic
  analysis must be read-only. Any relaxation of the allowlist requires an
  explicit settings override and an ADR.
- **User-supplied model is OpenClaude's concern.** Aegis SWR does not
  configure OpenClaude's backend model. The user sets `CLAUDE_CODE_USE_OPENAI`,
  `OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` as OpenClaude's own
  env vars. Aegis SWR only needs `OPENCLAUDE_GRPC_URL` to locate the server.
- **Proto schema committed.** Generated `_pb2.py` files are committed to the
  repo so contributors without `grpc_tools` installed can still build and test.
  The `make proto-gen` target regenerates them; CI verifies the committed files
  match by re-running generation and diffing.
- **`enabled_when` in agents.yaml** is a minimal, non-breaking extension to
  `RouterConfig`. The field is ignored by the router itself (OpenClaude is not
  routed through LiteLLM); it exists only to suppress validation errors when
  the env var is absent.

## Decomposition tree (as built)

The milestone is decomposed to the **full subtask level**: 9 tasks, each with
a `README.md` (scope, linked subtask table, constraints) and its numbered
subtask spec files (39 total) — matching the granularity of Milestones
0001-0003. Implementation has not started; every subtask below is still ⬜.

```
docs/roadmap/0004-code-intelligence/
├── plan.md                                       ← milestone spec (tasks, contracts C1–C9)
├── status.md                                     ← this tracker
├── 01.0-settings-config/          (4 subtasks)   ← configuration
├── 02.0-grpc-proto-client/        (4 subtasks)   ← infrastructure (gRPC isolation)
├── 03.0-process-lifecycle/        (4 subtasks)   ← infrastructure (subprocess mgmt)
├── 04.0-openclaude-tool/          (4 subtasks)   ← infrastructure (CodeBackend impl)
├── 05.0-events-exceptions/        (3 subtasks)   ← infrastructure (EventBus types)
├── 06.0-app-wiring/               (4 subtasks)   ← integration (+ code_intel scaffolding)
├── 07.0-test-suite-unit/          (6 subtasks)   ← testing (unit)
├── 08.0-test-suite-integration/   (5 subtasks)   ← testing (integration)
└── 09.0-documentation-ci/         (5 subtasks)   ← documentation & milestone closeout
```

Each task directory's `README.md` links every subtask to its `{NN}-{slug}.md`
spec file. See "Notes & decisions" above for the design gaps the decomposition
pass surfaced — several subtask specs note an open question inline pending
those decisions.

## Per-task detail

_Filled in as tasks complete. Subtask names link to their spec file; "Done"
tracks implementation, not spec-writing (all specs now exist)._

### Task 01.0 — OpenClaude Settings & Config

**Status:** ✅ Complete (all four subtasks; 02 & 03 unblocked by building the minimal Milestone 0003 config slice)

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`OpenClaudeSettings` Pydantic class](01.0-settings-config/01-openclaude-settings.md) | ✅   |
| 02      | [`agents.yaml` `openclaude_agent` role](01.0-settings-config/02-agents-yaml-role.md) | ✅   |
| 03      | [`RouterConfig` `enabled_when` extension](01.0-settings-config/03-router-config-enabled-when.md) | ✅   |
| 04      | [Settings composition in top-level config](01.0-settings-config/04-settings-composition.md) | ✅   |

**Delivered:** The OpenClaude configuration surface. `src/aegis_swr/openclaude/{__init__.py,config.py}`
defines `OpenClaudeSettings` (Pydantic `BaseSettings`, `env_prefix="OPENCLAUDE_"`) with the 8 C1 fields
plus a decided `use_tls: bool` (env `OPENCLAUDE_USE_TLS`) so Task 02.0 has an explicit TLS-channel signal
(the C1 URL validator rejects scheme prefixes, so TLS could not be inferred from the URL). Validators reject
scheme-prefixed / malformed `grpc_url`, unknown tool names, out-of-range `max_response_tokens`, and
non-positive / mis-ordered timeouts, raising the forward-declared `OpenClaudeConfigError` (Task 05.0 will
re-home it to `exceptions.py`). `src/aegis_swr/config/settings.py` composes `openclaude: OpenClaudeSettings`
into the top-level `Settings` via `default_factory` (one field; no `grpc_url` branching — that stays in
Task 06.0). `scripts/postinstall_openclaude.py` is a best-effort, never-raising npm helper.

**Key implementation decisions / deviations (all confirmed with the user):**
- **02 & 03 unblocked by a minimal Milestone 0003 slice.** Both target an `agents.yaml` +
  `RouterConfig.from_yaml()` / `enabled_when` layer that Milestone 0003 specifies but had **never
  implemented in `src/`**. After confirming (a dependency investigation across 0002/0003/0004) that this
  was the *only* hard cross-milestone blocker and that 0002 needs nothing, the minimal 0003 config slice
  was built: Tasks 0003/01.0 (`src/aegis_swr/config/agents.yaml`) + 0003/02.0
  (`src/aegis_swr/router/{__init__,config,exceptions}.py` — `RouterConfig`, frozen config dataclasses,
  exception hierarchy; `events.py` and Tasks 0003/03.0–07.0 deliberately NOT built — not needed by 0004,
  and the router package carries no `litellm`/`anthropic`/`openai` import). Subtask 02 added the
  `openclaude_agent` stanza; subtask 03 extended `AgentConfig`/`from_yaml` with optional `provider` +
  `enabled_when` (roles omitting `enabled_when` parse unchanged; `openclaude_agent` is dropped when
  `OPENCLAUDE_GRPC_URL` is unset, included with `provider="openclaude"` when set). `agents.yaml` stays
  inert config (parsed only by `RouterConfig`/tests) until Task 06.0 wires it. See
  `0003-litellm-routing/status.md`. Note this resolves the concrete, deeper form of the "package path
  mismatch" gap noted above — the entire router subsystem, not just a path, was absent.
- **Path translation.** `aegis/…` → `src/aegis_swr/…`; tests → `tests/unit/openclaude/` (the repo has only
  `tests/unit/` + `tests/integration/`).
- **No Poetry hook.** The project is hatchling + uv (no `[tool.poetry]`); the spec's `[tool.poetry.build]`
  wiring would never fire, so it was omitted. `postinstall_openclaude.py` keeps `install_openclaude_cli()`
  with a `__main__` guard (`uv run python scripts/postinstall_openclaude.py`) instead of a `build()` hook.
- **Env-name aliases.** `max_response_tokens` / `connect_timeout_s` / `request_timeout_s` / `process_binary`
  bind to the documented C1 env names (`OPENCLAUDE_MAX_TOKENS` / `_CONNECT_TIMEOUT` / `_REQUEST_TIMEOUT` /
  `_BINARY`) via `validation_alias` + `populate_by_name=True` — without this they silently listened on
  pydantic-derived names and swallowed operator config.
- **CSV env parsing.** A custom `_CsvEnvSettingsSource` (+ a `mode="before"` validator) lets the `list[str]`
  fields accept comma-separated env values; pydantic-settings v2 otherwise expects JSON.
- **`scripts/replace_optional.py` is absent** from the repo (stale `CLAUDE.md` reference; the Stop hook does
  not invoke it); the `Optional[T]` convention was enforced by grep instead.

**Review:** feature-reviewer **LGTM**; security-auditor **PASS_WITH_FOLLOWUP** (no CRITICAL). Applied hardening:
`grpc_url` regex `\Z`-anchored (rejects trailing-newline smuggling), postinstall also swallows `OSError`
(honours its never-raise contract), and a warn-only `bash_allowlist` validator flags shells/interpreters/
mutators (symmetric with `allowed_tools`).

> **Security follow-up for Task 04.0 (tracked).** The C1 default `bash_allowlist` includes `find` and `cat`,
> which are **not** truly read-only (`find -exec`/`-delete` = arbitrary exec/deletion; `cat` = read any file
> incl. secrets). The default was kept as specified (status.md calls the allowlist "non-negotiable"), but the
> read-only guarantee depends on Task 04.0's Bash-argument gate rejecting `find -exec`/`-delete` and
> constraining `cat` targets. The warn-only validator here deliberately does **not** warn on `find`/`cat`
> (they are spec defaults) — enforcement, not warning, is the fix, and it lives in 04.0.

**Test coverage:** `src/aegis_swr/openclaude/config.py` 95.83% (26 tests,
`tests/unit/openclaude/test_config.py`); `src/aegis_swr/router/config.py` 100% and the
router package (24 tests, `tests/unit/router/`, built as the Milestone 0003 dependency
slice for subtasks 02/03). Full unit suite: 551 passed, 88.26% total.

---

### Task 02.0 — gRPC Proto & Client

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`openclaude.proto` schema](02.0-grpc-proto-client/01-proto-schema.md) | ⬜   |
| 02      | [`make proto-gen` target](02.0-grpc-proto-client/02-proto-gen-makefile.md) | ⬜   |
| 03      | [`OpenClaudeGrpcClient` implementation](02.0-grpc-proto-client/03-grpc-client.md) | ⬜   |
| 04      | [`health_check()` + timeout handling](02.0-grpc-proto-client/04-health-check-timeouts.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 03.0 — Process Lifecycle Manager

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [External mode `__aenter__` / `__aexit__`](03.0-process-lifecycle/01-external-mode.md) | ⬜   |
| 02      | [Managed mode subprocess start/stop](03.0-process-lifecycle/02-managed-mode.md) | ⬜   |
| 03      | [Port-0 free-port selection](03.0-process-lifecycle/03-port-selection.md) | ⬜   |
| 04      | [stderr forwarding to `logger`](03.0-process-lifecycle/04-stderr-forwarding.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 04.0 — OpenClaudeTool Implementor

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [Tool skeleton + input schema](04.0-openclaude-tool/01-tool-skeleton.md) | ⬜   |
| 02      | [Stream processing + content accumulation](04.0-openclaude-tool/02-stream-processing.md) | ⬜   |
| 03      | [Permission request handling + allowlist](04.0-openclaude-tool/03-permission-allowlist.md) | ⬜   |
| 04      | [Budget pre-check + truncation](04.0-openclaude-tool/04-budget-truncation.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 05.0 — Event Types & Exceptions

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [Seven event dataclasses](05.0-events-exceptions/01-event-dataclasses.md) | ⬜   |
| 02      | [Three exception types](05.0-events-exceptions/02-exception-types.md) | ⬜   |
| 03      | [EventBus registry update](05.0-events-exceptions/03-eventbus-registration.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 06.0 — App Wiring & agents.yaml

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`app.py` composition root update (+ `code_intel/` scaffolding)](06.0-app-wiring/01-code-intel-scaffolding-and-app-wiring.md) | ⬜   |
| 02      | [`--dry-run` path with `grpc_url` set](06.0-app-wiring/02-dry-run-path.md) | ⬜   |
| 03      | [`agents.yaml` `openclaude_agent` update](06.0-app-wiring/03-agents-yaml-finalisation.md) | ⬜   |
| 04      | [`README.md` / `docs/setup.md` update](06.0-app-wiring/04-readme-update.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 07.0 — Test Suite — Unit

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`conftest.py` fixtures](07.0-test-suite-unit/01-conftest-fixtures.md) | ⬜   |
| 02      | [`test_config.py`](07.0-test-suite-unit/02-test-config.md) | ⬜   |
| 03      | [`test_grpc_client.py`](07.0-test-suite-unit/03-test-grpc-client.md) | ⬜   |
| 04      | [`test_process.py`](07.0-test-suite-unit/04-test-process.md) | ⬜   |
| 05      | [`test_tool.py` (100% branch required)](07.0-test-suite-unit/05-test-tool.md) | ⬜   |
| 06      | [`test_events.py`](07.0-test-suite-unit/06-test-events.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 08.0 — Test Suite — Integration

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`integration/conftest.py` + skip guards](08.0-test-suite-integration/01-conftest-skip-guards.md) | ⬜   |
| 02      | [`test_process_lifecycle.py`](08.0-test-suite-integration/02-test-process-lifecycle.md) | ⬜   |
| 03      | [`test_grpc_stream.py`](08.0-test-suite-integration/03-test-grpc-stream.md) | ⬜   |
| 04      | [`test_tool_live.py`](08.0-test-suite-integration/04-test-tool-live.md) | ⬜   |
| 05      | [`test_allowlist_enforcement.py`](08.0-test-suite-integration/05-test-allowlist-enforcement.md) | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 09.0 — Documentation & CI

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`docs/openclaude-setup.md`](09.0-documentation-ci/01-setup-guide.md) | ⬜   |
| 02      | [`docs/openclaude-config-reference.md`](09.0-documentation-ci/02-config-reference.md) | ⬜   |
| 03      | [CI `grep` boundary check extension](09.0-documentation-ci/03-ci-boundary-check.md) | ⬜   |
| 04      | [CI coverage gate extension](09.0-documentation-ci/04-ci-coverage-gate.md) | ⬜   |
| 05      | [Milestone closeout + `CHANGELOG.md`](09.0-documentation-ci/05-milestone-closeout.md) | ⬜   |

**Delivered:** —
**Test coverage:** —
