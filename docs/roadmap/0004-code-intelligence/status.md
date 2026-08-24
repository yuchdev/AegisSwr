# Milestone 0004 — OpenClaude Integration — Status

Tracks progress against [plan.md](/docs/roadmap/0004-code-intelligence/plan.md).
Updated as each task lands.

## Current status

| Task | Name                         | Status         | Tests |
|------|------------------------------|----------------|-------|
| 01.0 | OpenClaude Settings & Config | ✅ Complete | `tests/unit/openclaude/test_config.py` (26), `tests/unit/router/` (24) |
| 02.0 | gRPC Proto & Client          | ✅ Complete     | `tests/unit/openclaude/grpc/test_client.py` (35) |
| 03.0 | Process Lifecycle Manager    | ✅ Complete     | `tests/unit/openclaude/test_process.py` (51) |
| 04.0 | OpenClaudeTool Implementor   | ✅ Complete     | `tests/unit/openclaude/test_tool.py` (63, 100% branch), `tests/unit/code_intel/` (20) |
| 05.0 | Event Types & Exceptions     | ✅ Complete     | `tests/unit/openclaude/test_events.py` (67), `test_exceptions.py` (13), `test_package_api.py` (14) |
| 06.0 | App Wiring & agents.yaml     | ✅ Complete | `openclaude/composition.py` (build_code_agent); `aegis code-intel check` CLI subcommand |
| 07.0 | Test Suite — Unit            | ✅ Complete | `tests/unit/openclaude/` (269), `tests/unit/code_intel/` (20), `tests/unit/openclaude/test_composition.py`, `tests/unit/test_cli_code_intel.py` (8); `tool.py` 100% branch |
| 08.0 | Test Suite — Integration     | ✅ Complete | `tests/integration/openclaude/` (10 live tests, skipped without binary + `OPENCLAUDE_INTEGRATION`) |
| 09.0 | Documentation & CI           | ✅ Complete | CI: `openclaude-isolation`, `openclaude-unit-coverage`, `openclaude-integration` jobs |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** **milestone complete — all nine tasks (01.0–09.0) ✅.**
`src/aegis_swr/openclaude/` (config, tool, process, events, exceptions,
grpc/client + committed proto stubs, composition.py) and
`src/aegis_swr/code_intel/` (backend, agent, budget) are implemented and tested.
`src/aegis_swr/openclaude/composition.py` holds `build_code_agent`, the sole
place the `OPENCLAUDE_GRPC_URL` branch (C4) lives; the orphan `app.py` was
deleted in the post-review remediation (see [ADR 0003](/docs/adr/0003-code-intel-composition-root.md)).
`agents.yaml` carries the finalised `openclaude_agent` role. Full unit suite green
(824 passed pre-remediation at 89.19% total;
`tool.py` 100% branch); integration suite skips cleanly without a sidecar; CI
enforces module isolation plus the OpenClaude coverage gates. Enabling code
intelligence requires only setting `OPENCLAUDE_GRPC_URL`.

**Note on `check_doc_links.py`:** the Task 09.0 "Delivered" section below
originally claimed zero link problems. In fact, the two OpenClaude docs were
placed in `docs/specs/` while every inbound link (root `README.md`,
`docs/README.md`, cross-links within the docs themselves) pointed at `docs/`.
This was corrected in the docs remediation pass: both files were moved to `docs/`
via `git mv`, resolving all OpenClaude-related dangling links.

_History (decomposition-pass state, retained for context):_ full task → subtask
decomposition was completed before implementation; each of the nine tasks has a
`README.md` and numbered subtask spec files (39 total). The subtask docs are
written against a module root of `aegis/...`; the real package is
`src/aegis_swr/...` (see "Package path mismatch" below) — every file path was
translated at implementation time.

**Decomposition review found several cross-cutting design gaps that should be
resolved before implementation starts** (not fixed in this pass — they are
genuine architecture decisions, not typos):

- **Package path mismatch.** Every task in this milestone (and 0003 before it)
  is written against a module root of `aegis/...`; the real package is
  `src/aegis_swr/...`. This is pre-existing across the roadmap tree, not new to
  0004, but it means every file path in every subtask doc needs translating at
  implementation time.
- **`CodeBackend` name collision.**
  **[Resolved post-review, 2026-07-10]** The code-intelligence
  `CodeBackend` in `src/aegis_swr/code_intel/backend.py` has been renamed to
  `CodeIntelBackend`, eliminating the ambiguity with the unrelated VCS
  `CodeBackend` in `src/aegis_swr/backends/base.py`. See
  [ADR 0003](/docs/adr/0003-code-intel-composition-root.md).
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
  **[Resolved by Task 02.0, 2026-07-08]** Task 01.0 added the explicit
  `OpenClaudeSettings.use_tls: bool` field (env `OPENCLAUDE_USE_TLS`, default
  `False`); `OpenClaudeGrpcClient._ensure_channel()` selects
  `grpc.aio.secure_channel` vs `insecure_channel` from that flag (no scheme
  parsing of `grpc_url`). A loguru WARNING now fires when `use_tls=False` and
  the host is non-loopback, flagging plaintext prompt transmission (per the
  security review — MEDIUM, mitigated warn-not-reject).
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
  **[05.0 → 02.0 edge resolved by Task 02.0, 2026-07-08]** rather than block on
  the unbuilt 05.0, `src/aegis_swr/openclaude/exceptions.py` was forward-declared
  (base `OpenClaudeError` + `OpenClaudeUnavailableError`), mirroring how Task 01.0
  forward-declared `OpenClaudeConfigError` in `config.py`. **Forward-contract
  obligation on Task 05.0:** subtask 04 needed `retriable`/`status_code`, so the
  ctor is a superset `(message, grpc_url=None, *, retriable=True, status_code=None)`
  of 05.0's pinned `(message, grpc_url=None)`. When 05.0 lands
  (`05.0-events-exceptions/02-exception-types.md`) it MUST preserve those keyword
  fields and base off `OpenClaudeError`, or `client.py._translate_status()` breaks.

See each task's numbered subtask files for where these are flagged inline.

## Notes & decisions

- **Supersedes Milestone 0004 (decided 2026-07-05).** OpenClaude is promoted
  from an optional fallback `CodeTool` to the central Code Intelligence
  mechanism. The bespoke tool-per-capability design in 0004 (`gtags` / `zoekt` /
  `tree-sitter` indices, six hand-built tools, a custom `ReActLoop`) is
  cancelled as duplicate effort — OpenClaude's own internal agentic loop
  provides the same navigation via `Bash`. Consequently 0004 now depends only
  on 0003, becomes the sole backend behind `aegis/code_intel/`, and stands up a
  minimal generic scaffolding (a `CodeIntelBackend` contract, a `CodeAgent` entry
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
  milestone modifies one existing file (`agents.yaml`), extends one existing
  module (`aegis/router/config.py` for `enabled_when`), and stands up two new
  thin packages: `aegis/openclaude/` (gRPC client, process, tool, events,
  exceptions, and `composition.py` holding `build_code_agent`) and
  `aegis/code_intel/` (`CodeIntelBackend` contract, `CodeAgent`, `CallBudget`).
  The composition root lives in `openclaude/composition.py` and is exposed via
  the `aegis code-intel check` CLI subcommand; `app.py` was deleted
  post-review (see [ADR 0003](/docs/adr/0003-code-intel-composition-root.md)).
  No existing router or agent behaviour is modified. If `OPENCLAUDE_GRPC_URL` is
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
  `uv run python scripts/proto_gen.py` regenerates them (the Makefile was
  removed; CI verifies the committed files match by re-running generation and
  diffing).
- **`enabled_when` in agents.yaml** is a minimal, non-breaking extension to
  `RouterConfig`. The field is ignored by the router itself (OpenClaude is not
  routed through LiteLLM); it exists only to suppress validation errors when
  the env var is absent.

## Decomposition tree (as built)

The milestone is decomposed to the **full subtask level**: 9 tasks, each with
a `README.md` (scope, linked subtask table, constraints) and its numbered
subtask spec files (39 total) — matching the granularity of Milestones
0001-0003. All subtasks are now complete.

```
docs/roadmap/0004-code-intelligence/
├── plan.md                                       ← milestone spec (tasks, contracts C1–C9)
├── status.md                                     ← this tracker
├── 01.0-settings-config/          (4 subtasks)   ← configuration
├── 02.0-grpc-proto-client/        (4 subtasks)   ← infrastructure (gRPC isolation)
├── 03.0-process-lifecycle/        (4 subtasks)   ← infrastructure (subprocess mgmt)
├── 04.0-openclaude-tool/          (4 subtasks)   ← infrastructure (CodeIntelBackend impl)
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

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`openclaude.proto` schema](02.0-grpc-proto-client/01-proto-schema.md) | ✅   |
| 02      | [`make proto-gen` target](02.0-grpc-proto-client/02-proto-gen-makefile.md) | ✅   |
| 03      | [`OpenClaudeGrpcClient` implementation](02.0-grpc-proto-client/03-grpc-client.md) | ✅   |
| 04      | [`health_check()` + timeout handling](02.0-grpc-proto-client/04-health-check-timeouts.md) | ✅   |

**Delivered:**
- `src/aegis_swr/openclaude/grpc/proto/openclaude.proto` — the authoritative C2
  wire contract (proto3, package `aegis.openclaude.v1`): `FrameType` enum,
  `AgentMessage`, `PromptRequest`, single server-streaming `AgentService.Query`.
- `Makefile` `proto-gen` target + committed generated stubs
  (`openclaude_pb2.py`, `openclaude_pb2_grpc.py`). Stubs are generated with
  `--proto_path=src` so cross-stub imports are **package-qualified**
  (`from aegis_swr.openclaude.grpc.proto import openclaude_pb2`), avoiding the
  flat-import trap with no hand-edits. `grpcio-tools==1.82.1` pinned exact
  (dev-only) for byte-reproducible codegen; regeneration is idempotent.
- `src/aegis_swr/openclaude/grpc/client.py` — `OpenClaudeGrpcClient` (the sole
  C3 gRPC boundary), `AgentFrame` (frozen typed projection), `FrameKind` enum.
  Lazy channel (insecure vs `secure_channel` via `settings.use_tls`),
  `from_channel()` test seam, async-generator `query()` (stops after first
  terminal `DONE`/`ERROR`), `health_check()` (double-bounded by
  `asyncio.wait_for` + gRPC `timeout=`, **never raises**), `_translate_status`
  (gRPC `UNAVAILABLE`/`DEADLINE_EXCEEDED` → retriable `OpenClaudeUnavailableError`;
  other codes → non-retriable), idempotent `close()`, async-CM support.
- `src/aegis_swr/openclaude/exceptions.py` — forward-declared `OpenClaudeError`
  + `OpenClaudeUnavailableError` (see the 05.0 forward-contract obligation above).

**Key decisions & gate outcomes:**
- **C3 isolation holds** — `import grpc` / `openclaude_pb2*` confined to
  `openclaude/grpc/` (grep-enforced; CI check formalised in Task 09.0).
- **C9 log-safety** — no prompt/response/`run_id`-correlated payload in any log
  sink or exception message; only lifecycle facts + gRPC status-code *names*.
- **Distinct failure modes** — a gRPC *status error* → `OpenClaudeUnavailableError`
  (transport); a terminal `ERROR` *frame* → yielded `AgentFrame` (logical), kept
  separate so retry decisions aren't corrupted.
- **`health_check()` is subtask 04's** — subtask 03 left a `NotImplementedError`
  stub (honest present-but-unimplemented) rather than a silently-wrong `False`.
- **/dep-audit: CLEAN** — grpcio/protobuf/grpcio-tools all Apache-2.0/BSD-3, no
  active CVEs at resolved versions; floors hardened to `grpcio>=1.68.1`,
  `protobuf>=7.0` to exclude known-vulnerable sub-ranges. Report in `docs/reviews/`.
- **/pr-review: APPROVE** (2 rounds) — feature LGTM after fixing a `health_check`
  "never-raises" contract gap (typed `except Exception` backstop + 2 tests);
  security PASS after adding the non-loopback plaintext WARNING. Threat model:
  `docs/security/2026-07-08-openclaude-grpc-client.md`.

**Deferred / follow-ups (not blocking):**
- Client-side response-size / `max_response_tokens` cap → **Task 04.0** (spec
  assigns budget/token accounting there); a `grpc.max_receive_message_length`
  channel-option hardening is a candidate at that time.
- 05.0 must land `OpenClaudeUnavailableError` as a compatible superset (above).
- LOW: `_is_loopback_host` treats any `127.*`-prefixed *hostname* (e.g.
  `127.example.com`) as loopback, suppressing the plaintext warning; tighten to
  require a numeric octet after `127.` (operator-supplied trusted config, contrived).

**Test coverage:** `tests/unit/openclaude/grpc/test_client.py` — 35 tests
(streaming, terminal-frame invariants, tool→None projection, protocol-violation
handling, TLS selection, plaintext warning, `health_check` true/false matrix,
retriable mapping, close idempotency, C9 log-safety). `client.py` at 99.33%.
Full unit suite: **586 passed, 88.34% total** (≥85% gate).

---

### Task 03.0 — Process Lifecycle Manager

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [External mode `__aenter__` / `__aexit__`](03.0-process-lifecycle/01-external-mode.md) | ✅   |
| 02      | [Managed mode subprocess start/stop](03.0-process-lifecycle/02-managed-mode.md) | ✅   |
| 03      | [Port-0 free-port selection](03.0-process-lifecycle/03-port-selection.md) | ✅   |
| 04      | [stderr forwarding to `logger`](03.0-process-lifecycle/04-stderr-forwarding.md) | ✅   |

**Delivered:**
- `src/aegis_swr/openclaude/process.py` — `OpenClaudeProcess`, the sole C6 process
  lifecycle owner: an async context manager over `OpenClaudeSettings` + the
  `EventBus`. **External mode** (`auto_start=False`, default) health-checks the
  configured endpoint and emits `OpenClaudeConnected`/`OpenClaudeDisconnected`
  without starting a process. **Managed mode** (`auto_start=True`) spawns the
  sidecar via `asyncio.create_subprocess_exec` (never `Popen`/shell), waits for
  the gRPC port with `asyncio.sleep` backoff, and terminates SIGTERM→grace→SIGKILL
  on exit. `grpc_url` is readable only inside the `async with` block (else
  `RuntimeError`). Port-`0` `grpc_url` resolves a concrete free port once at entry
  (single source of truth: child bind flag == caller `grpc_url` == readiness
  probe). Child `stderr` drains line-by-line to `logger.debug` under
  `SensitiveFilter`; `stdout` is `DEVNULL`.
- `src/aegis_swr/openclaude/events.py` — **forward-declared** `OpenClaudeConnected`
  / `OpenClaudeDisconnected` (frozen dataclasses). See the 05.0 forward-contract
  obligation below.

**Key decisions & gate outcomes:**
- **EventBus integration (forward decision for 05.0):** the events **subclass the
  live `core.events.DomainEvent`** — NOT the plain-dataclass/`event_type`-string
  shape 05.0's spec text describes (that shape targeted Milestone 0003's router
  bus, which was never built). `EventBus.publish()` dispatches only `DomainEvent`
  subclasses via `__mro__`, so a plain dataclass would be silently dropped. The
  05.0 canonical field set (`run_id`, `grpc_url`, `mode`, `timestamp` /
  `run_id`, `reason`, `timestamp`) and the `event_type` `ClassVar` are preserved.
  **Task 05.0 obligation:** canonicalise `events.py` by keeping the `DomainEvent`
  base + these field names (do not revert to the stale plain-dataclass shape).
- **Always-terminate / no-orphan (C6):** every managed exit path — clean exit,
  port-never-opens, a raising `OpenClaudeConnected` subscriber, and task
  cancellation — cancels the stderr forwarder and terminates the sidecar before
  the exception leaves `__aenter__` (guards catch `BaseException` to cover
  `CancelledError`, then re-raise). `OpenClaudeConnected`/`Disconnected` are each
  emitted exactly once (idempotency flag).
- **C9 log-safety:** child stderr is treated as untrusted and forwarded only via
  `logger.debug` (line as a bound arg, never folded into a template or exception);
  no raw payload/stderr in any log or error body; events carry only ids/status
  strings/timestamps.
- **/security threat model** (`docs/security/2026-07-09-openclaude-managed-mode-spawn.md`):
  argv is fail-closed (`_validate_argv_token`, `\A…\Z`-anchored, both `allowed_tools`
  and `bash_allowlist`, joined single-token `--flag=csv`); loopback-only bind
  enforced before spawn; binary from `settings.process_binary` only; explicit safe
  `cwd`. Port-0 TOCTOU is documented + surfaced as `OpenClaudeUnavailableError`.
- **/pr-review: APPROVE** — feature verdict resolved (a claimed blocking
  `LimitOverrunError` gap was verified a false positive — `StreamReader.readline()`
  re-raises over-long lines as `ValueError`, which is caught; added
  `asyncio.LimitOverrunError` to the catch defensively anyway + a `kill()`
  `OSError` guard). Security **ADVISORY** (no CRITICAL): fixed the `_ARGV_TOKEN_RE`
  `$`→`\Z` trailing-newline gap; **deferred follow-up:** the sidecar currently
  inherits the full parent environment (no scoped `env=`) — flagged for an
  `app-architect`/`incident-analyst` note, out of Task 03.0 scope.
- **Coverage:** full unit suite **637 passed**, total **88.69 %**; `process.py`
  **96.03 %**, `events.py` **100 %**.

**Test coverage:** `tests/unit/openclaude/test_process.py` (51 tests): external/managed
entry-exit, exactly-once events, `grpc_url` guard, always-terminate on every failure
path (incl. cancellation), SIGTERM→SIGKILL escalation + reap, port-0 single-source-of-truth,
argv fail-closed (incl. trailing-newline), loopback-only, binary-path validation, stderr
drain at DEBUG + per-line-error resilience, external-mode no-forwarder no-op.

---

### Task 04.0 — OpenClaudeTool Implementor

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [Tool skeleton + input schema](04.0-openclaude-tool/01-tool-skeleton.md) | ✅   |
| 02      | [Stream processing + content accumulation](04.0-openclaude-tool/02-stream-processing.md) | ✅   |
| 03      | [Permission request handling + allowlist](04.0-openclaude-tool/03-permission-allowlist.md) | ✅   |
| 04      | [Budget pre-check + truncation](04.0-openclaude-tool/04-budget-truncation.md) | ✅   |

**Delivered:**
- `src/aegis_swr/openclaude/tool.py` — `OpenClaudeTool`, the sole
  `CodeIntelBackend` (C4). `delegate(task, ctx)` runs ordered gates (C5): budget
  pre-check (zero gRPC calls if insufficient) → `dry_run` short-circuit
  (`[dry-run]`/0 tokens, zero calls) → stream. `_consume_stream` dispatches
  `AgentFrame`s by `FrameKind` via a handler map, accumulating `TEXT_CHUNK` and
  counting tool/frame events. On `DONE` it truncates to `max_response_tokens`,
  charges `max(1, len(text)//4)` (post-stream, success only), and emits the sole
  token-bearing `OpenClaudeStreamCompleted`. Permission gate, `ERROR`-frame and
  gRPC-error handling, and a defensive `except Exception` guarantee no exception
  escapes (C9). **100% branch coverage.**
- **`src/aegis_swr/code_intel/` scaffolding slice** (`backend.py`, `budget.py`,
  `agent.py`, `__init__.py`) — the minimal, backend-agnostic contract
  (`CodeIntelBackend` ABC, `CodeResult`, `CodeTaskContext`, `CallBudget`,
  `CodeAgent`) that Task 06.0 owns; built forward to unblock 04.0. C3-clean
  (imports neither `openclaude` nor `grpc`). **Composition wiring is deferred to
  Task 06.0** (it needs this `OpenClaudeTool`, so it cannot precede it).

**Key decisions & gate outcomes:**
- **Built to the canonical 06.0 contract, not the stale 04.0 spec wording:** public
  method is `delegate(task, ctx: CodeTaskContext) -> CodeResult` (not `run`);
  `CodeResult` is `(content, token_estimate, available, truncated, metadata)` with
  **per-call failures encoded in `metadata`** (`{ok, error, retriable}`), not
  `text`/`ok`/`retriable` fields; `ctx.run_id` is a `UUID` (→ `str()` for
  `query()`/events); frame types come from the client (`AgentFrame`/`FrameKind`);
  events use the real 05.0 signatures. Budget is a ctor-injected collaborator
  (`self._budget`). The contract class is `CodeIntelBackend` (not `CodeBackend` —
  see the name-collision design gap above, resolved post-review).
- **X002 exemption (sanctioned):** `delegate`'s defensive `except Exception` (C9
  no-exception-escapes) is a must-never-raise resilience boundary, so
  `openclaude/tool.py` joins `core/events.py`/`grpc/client.py` in
  `[tool.flake8_lint_tests].exclude`. Returns a typed failure; re-raises nothing.
- **/pr-review: APPROVE (after fixes).** Feature REQUEST_CHANGES → resolved: a
  typed `_DONE` sentinel replaced a `-> Optional[CodeResult]`/`"DONE"` annotation
  lie; the dead `budget` param was removed from `CodeAgent.investigate` (budget is a
  backend construction-time collaborator — per-investigation scoping finalized in
  06.0). Security ADVISORY (2 MEDIUM, no CRITICAL): threat model at
  `docs/security/2026-07-09-openclaude-tool-permission-gate.md`.
- **Permission-gate hardening (C7):** the tool-side allowlist check inspected only
  the first token, so `"rg; curl evil"` auto-approved. Hardened `_is_allowlisted`
  to deny any command with shell metacharacters (`; & | $ \` newline ( ) { } < >`)
  or a path-qualified first token; the full bypass matrix is now DENIED (regression
  tested). Documented as **defense-in-depth + observability** — the authoritative
  read-only control is the sidecar's `--bash-allowlist` launch flag (Task 03.0
  managed mode); this gate has no approval back-channel.
- **Deferred to Task 06.0:** `app.py` composition wiring; per-investigation
  `CallBudget` lifecycle; an **external-mode runbook** requiring the operator's
  sidecar to be independently allowlisted (the tool gate is not authoritative
  there). Deferred to Task 09.0: the `openclaude.*` event-taxonomy doc table.
- **Coverage:** full unit suite **814 passed**, total **89.14 %**; `tool.py`
  **100 % branch**, `code_intel/` **100 %**.

**Test coverage:** `tests/unit/openclaude/test_tool.py` (63 tests, 100% branch on
tool.py), `tests/unit/code_intel/` (20).

---

### Task 05.0 — Event Types & Exceptions

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [Seven event dataclasses](05.0-events-exceptions/01-event-dataclasses.md) | ✅   |
| 02      | [Three exception types](05.0-events-exceptions/02-exception-types.md) | ✅   |
| 03      | [EventBus registry update](05.0-events-exceptions/03-eventbus-registration.md) | ✅   |

**Delivered:**
- `src/aegis_swr/openclaude/events.py` — the full C8 taxonomy: seven
  `@dataclass(frozen=True, kw_only=True)` events (`OpenClaudeConnected`,
  `OpenClaudeDisconnected`, `OpenClaudeToolCall`, `OpenClaudeToolResult`,
  `OpenClaudePermissionDenied`, `OpenClaudeStreamCompleted`,
  `OpenClaudeStreamError`), each with `run_id`, a UTC `timestamp`, and an
  `event_type` `ClassVar` sentinel. `OpenClaudeStreamCompleted` is the sole
  carrier of `token_estimate` (C8). This discharges the Task 03.0
  forward-declaration obligation (the two lifecycle events were forward-declared
  there; this task adds the five stream events and unifies the shape).
- `src/aegis_swr/openclaude/exceptions.py` — canonical three-type hierarchy:
  `OpenClaudeUnavailableError`, `PermissionDeniedError`, `OpenClaudeConfigError`.
  Discharges the Task 02.0 forward-declaration obligation.
- `src/aegis_swr/openclaude/__init__.py` — public re-exports of the seven events
  + three exceptions (grpc-free; C3).

**Key decisions & gate outcomes:**
- **EventBus obligation discharged (deviates from 05.0 spec text, deliberately):**
  all seven events **subclass the live `core.events.DomainEvent`**, NOT the
  plain-dataclass/`event_type`-string shape the spec describes — that shape
  targeted Milestone 0003's router bus, which was never built. `EventBus.publish()`
  dispatches only `DomainEvent` subclasses via `__mro__`, so a plain dataclass
  would reach zero subscribers. A live-bus publish/subscribe round-trip test proves
  the decision works. The `event_type` `ClassVar` is retained for `event_type`-based
  filtering.
- **Exception superset preserved (Task 02.0 obligation):**
  `OpenClaudeUnavailableError` keeps the superset ctor
  `(message, grpc_url=None, *, retriable=True, status_code=None)` because
  `grpc/client.py:279-283` sets `retriable`/`status_code`. The now-unused
  `OpenClaudeError` base was dropped (no catch sites) so the three hierarchies are
  independent, per spec.
- **`OpenClaudeConfigError` migrated** from `config.py` to `exceptions.py`
  (canonical home) with a `config.py` re-export; identity preserved
  (`config.OpenClaudeConfigError is exceptions.OpenClaudeConfigError`), so the
  Pydantic `isinstance` unwrap path and all `except` sites are unaffected. Distinct
  from the router's `ConfigValidationError` (neither subclasses the other).
- **C3 grpc isolation:** `import aegis_swr.openclaude` pulls in no `grpc` (only
  events + exceptions re-exported; Tool/Process/Client stay behind submodules) —
  asserted by a `sys.modules` test that snapshots/restores the registry so it can't
  pollute other tests.
- **/pr-review: APPROVE** — feature **LGTM**, security **CLEAN** (C9 payload-free
  and C3 isolation both confirmed; dropping `OpenClaudeError` and the config
  re-export introduce no error-handling posture change). Two test-quality nits
  (a tautological tz assertion, a misleading comment) fixed.
- **Deferred:** the consolidated `openclaude.*` event-taxonomy **doc table**
  (subtask 03) is owned by Task 09.0 / `docs-updater` per its spec — deferred there
  so the milestone's docs stay single-sourced; the code deliverable (re-exports) is
  complete.
- **Coverage:** full unit suite **730 passed**, total **88.77 %**; `events.py`
  **100 %**, `exceptions.py` **100 %**.

**Test coverage:** `tests/unit/openclaude/test_events.py` (67), `test_exceptions.py`
(13), `test_package_api.py` (14).

---

### Task 06.0 — App Wiring & agents.yaml

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [Composition root + `code_intel/` scaffolding](06.0-app-wiring/01-code-intel-scaffolding-and-app-wiring.md) | ✅   |
| 02      | [`--dry-run` path with `grpc_url` set](06.0-app-wiring/02-dry-run-path.md) | ✅   |
| 03      | [`agents.yaml` `openclaude_agent` update](06.0-app-wiring/03-agents-yaml-finalisation.md) | ✅   |
| 04      | [`README.md` / `docs/setup.md` update](06.0-app-wiring/04-readme-update.md) | ✅   |

**Delivered:** The composition root and its OpenClaude wiring.
`src/aegis_swr/openclaude/composition.py` holds `build_code_agent(settings, bus,
stack, *, run_id, dry_run)` — the **single** place the
`settings.grpc_url is not None` branch lives (C4). When set it constructs the
real stack (`OpenClaudeGrpcClient(settings)` →
`OpenClaudeProcess(..., client=client)` →
`OpenClaudeTool(client, settings, bus, CallBudget(max_response_tokens))`) and
injects the tool as the sole `CodeIntelBackend` into `CodeAgent`; when unset it
returns a backend-less `CodeAgent` (capability unavailable, no fallback). The
`code_intel/` scaffolding (`backend.py`, `agent.py`, `budget.py`) that this
subtask nominally creates already landed with Task 04.0 and is reused verbatim.
The composition root is exposed via the `aegis code-intel check` CLI subcommand
(dry-run by default; `--no-dry-run` for a live health-check run). **Dry-run**
(subtask 02) constructs and registers the full graph but skips
`OpenClaudeProcess.__aenter__()` — no health check, no managed spawn, no
`OpenClaudeConnected`/`Disconnected` events — and `OpenClaudeTool.delegate`
short-circuits on `ctx.dry_run` before any RPC, so no gRPC socket is opened even
with `OPENCLAUDE_GRPC_URL` set. The non-dry-run process is registered on the
caller's `AsyncExitStack`, tying `OpenClaudeDisconnected` (C6) to app lifetime.

**Post-review change:** the original implementation placed `build_code_agent` in
`src/aegis_swr/app.py` and exposed it as `python -m aegis_swr.app [--dry-run]`.
A review identified this as an orphan composition root unreachable from the real
`aegis` binary (so `OPENCLAUDE_GRPC_URL` had no effect in practice). After
remediation, `build_code_agent` lives in `openclaude/composition.py` (the
package that owns all its dependencies), `app.py` is deleted, and the entry point
is `aegis code-intel check`. See [ADR 0003](/docs/adr/0003-code-intel-composition-root.md).

**Key notes / deviations (all pre-existing roadmap translations):**
- **Real constructor signatures differ from the plan's illustrative snippet.**
  `OpenClaudeGrpcClient(settings)` (URL comes from settings, not a positional
  `url`), `OpenClaudeProcess(settings, bus, run_id, client=...)`, and
  `OpenClaudeTool(client, settings, bus, budget)` are wired as actually shipped
  by Tasks 02.0–04.0; `build_code_agent` gained a `run_id` parameter (the
  process stamps it onto lifecycle events).
- **agents.yaml** was a verification pass (subtask 03): the `openclaude_agent`
  stanza already carried `provider/model:~/timeout_s:120/enabled_when`;
  `timeout_s` confirmed equal to `OpenClaudeSettings.request_timeout_s` default
  (120), and the comment expanded to name OpenClaude's own model env vars. No
  secret on the role.
- **README** (subtask 04) gained a discoverable "Code Intelligence (OpenClaude)"
  section naming `OPENCLAUDE_GRPC_URL` as the sole enabler and forward-linking
  to `docs/config/openclaude-setup.md`.

**Test coverage:** `tests/unit/test_app.py` (8 tests) — full-suite unit
coverage of the composition root across all three paths (unavailable / dry-run /
live); `tool.py` 100% branch. Tests inject a fake gRPC client so no socket is
ever opened. Post-remediation, the tests target `openclaude/composition.py` and
the CLI subcommand rather than the deleted `app.py`.

---

### Task 07.0 — Test Suite — Unit

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`conftest.py` fixtures](07.0-test-suite-unit/01-conftest-fixtures.md) | ✅   |
| 02      | [`test_config.py`](07.0-test-suite-unit/02-test-config.md) | ✅   |
| 03      | [`test_grpc_client.py`](07.0-test-suite-unit/03-test-grpc-client.md) | ✅   |
| 04      | [`test_process.py`](07.0-test-suite-unit/04-test-process.md) | ✅   |
| 05      | [`test_tool.py` (100% branch required)](07.0-test-suite-unit/05-test-tool.md) | ✅   |
| 06      | [`test_events.py`](07.0-test-suite-unit/06-test-events.md) | ✅   |

**Delivered:** The mock-based unit suite. Because 07.0 was written
*incrementally alongside* tasks 01.0–06.0, the bulk already shipped with those
tasks and lives under `tests/unit/openclaude/` (actual layout; the roadmap's
`tests/openclaude/unit/` path was translated to match the repo's
`tests/unit/<pkg>/` convention): `test_config.py`, `grpc/test_client.py`,
`test_process.py`, `test_tool.py`, `test_events.py`, `test_exceptions.py`,
`test_package_api.py`, plus `tests/unit/code_intel/{test_backend,test_agent,test_budget}.py`.
This task added the two remaining pieces:

- **`tests/unit/test_app.py`** (8 tests) — the composition-root coverage for
  Task 06.0 (`build_code_agent` across all three paths), injecting a fake gRPC
  client so no socket opens. Post-remediation these tests target
  `openclaude/composition.py` and the `aegis code-intel check` CLI subcommand
  rather than the deleted `app.py`. **100% branch on the composition root.**
- **`tests/unit/openclaude/test_isolation.py`** (2 tests) — the pytest mirror of
  the CI `grep` boundary job (Task 09.0): asserts `grpc`/`_pb2` is imported only
  by `openclaude/grpc/client.py` (generated proto excluded) and that
  `aegis_swr.openclaude` is never imported by `core/`, `views/`, or
  `code_intel/`. Import-statement-aware, so docstring mentions don't trip it —
  mirrors the Milestone 0003 `litellm` isolation test.

**Key notes / deviations:**
- **A shared `conftest.py` was added** at `tests/unit/openclaude/conftest.py` providing
  shared unit fixtures: mock gRPC client, capturing `EventBus`, settings, contexts, and
  budgets. The injection-not-monkeypatch and no-`grpc`-import-in-tests intents are honoured.
- **Layout:** `tests/unit/openclaude/` and `tests/unit/code_intel/`, not
  `tests/openclaude/unit/` (repo convention).

**Test coverage:** `tool.py` **100% branch**; `events.py`, `exceptions.py`, and
all of `code_intel/` at 100%; `config.py` 96%, gRPC `client.py` 99%,
`process.py` 94% — comfortably past the ≥90% milestone-module gate. Full
milestone unit count: **299** (openclaude 269 incl. isolation + app/composition 8
+ ...), all passing with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude binary
on `PATH`.

---

### Task 08.0 — Test Suite — Integration

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`integration/conftest.py` + skip guards](08.0-test-suite-integration/01-conftest-skip-guards.md) | ✅   |
| 02      | [`test_process_lifecycle.py`](08.0-test-suite-integration/02-test-process-lifecycle.md) | ✅   |
| 03      | [`test_grpc_stream.py`](08.0-test-suite-integration/03-test-grpc-stream.md) | ✅   |
| 04      | [`test_tool_live.py`](08.0-test-suite-integration/04-test-tool-live.md) | ✅   |
| 05      | [`test_allowlist_enforcement.py`](08.0-test-suite-integration/05-test-allowlist-enforcement.md) | ✅   |

**Delivered:** The live integration suite under `tests/integration/openclaude/`
(repo convention; the roadmap's `tests/openclaude/integration/` path was
translated). `conftest.py` provides module-level skip guards
(`require_managed_openclaude` / `require_external_openclaude`) that emit exactly
one clean `skipped` line per module when `OPENCLAUDE_INTEGRATION` is unset or the
`openclaude` binary is absent, a disposable `stub_project` fixture (a temp-dir
Python project with a uniquely named `compute_checksum` symbol — never the Aegis
source tree), a module-scoped managed-mode `live_openclaude_process` fixture that
tears the sidecar down in a `finally` finalizer, and a connected `live_grpc_client`
closed on teardown. Test modules:

- `test_process_lifecycle.py` (3) — managed start within `connect_timeout_s`,
  `OpenClaudeConnected`/`OpenClaudeDisconnected` emitted exactly once, and no
  subprocess survives the context (via the child's `returncode`).
- `test_grpc_stream.py` (2) — a live `query()` yields ≥1 `TEXT_CHUNK` before a
  non-empty terminal `DONE` (ordering asserted); `health_check()` returns `True`.
- `test_tool_live.py` (3) — live `delegate()` returns non-empty content, exactly
  one `OpenClaudeStreamCompleted` with `token_estimate > 0`, and ≥1
  `OpenClaudeToolCall` (proving real navigation, not answers from priors).
- `test_allowlist_enforcement.py` (2) — a write-requiring task is denied under the
  default allowlist (stub bytes unchanged, `OpenClaudePermissionDenied` emitted),
  and a read-only task succeeds.

**Key notes / deviations (adapted to the shipped APIs):**
- **Real constructor/method names** replace the specs' illustrative ones:
  `OpenClaudeProcess(settings, bus, run_id)` (no `cwd=`/`event_bus=` kwargs),
  `OpenClaudeGrpcClient(settings)` + `.close()` (no `from_url`),
  `OpenClaudeTool(client, settings, bus, budget)`, `tool.delegate(task, ctx)`,
  `result.content`, and `frame.frame_type is FrameKind.TEXT_CHUNK/DONE`.
- **Denial is non-raising (C9).** The specs sketched `pytest.raises(PermissionDeniedError)`;
  the shipped `delegate` never raises, so the allowlist test asserts on the
  returned failure `CodeResult` (`metadata["error"] == "permission_denied"`,
  `retriable is False`) plus the emitted `OpenClaudePermissionDenied` event.
- **No `psutil`** (not a project dependency): the "no surviving process"
  assertion uses the managed subprocess's own `returncode` transition instead.
- **Managed cwd** is the process's fixed `_SAFE_CWD` (`tempfile.gettempdir()`),
  so navigation tasks reference the stub's absolute path rather than relying on a
  per-test working directory.

**Test coverage:** With `OPENCLAUDE_INTEGRATION` unset and no binary, the suite
reports **4 modules skipped** (never failed/errored); collection is clean. The
10 live tests run only under the `OPENCLAUDE_INTEGRATION` CI signal (Task 09.0).

---

### Task 09.0 — Documentation & CI

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`docs/config/openclaude-setup.md`](09.0-documentation-ci/01-setup-guide.md) | ✅   |
| 02      | [`docs/config/openclaude-config-reference.md`](09.0-documentation-ci/02-config-reference.md) | ✅   |
| 03      | [CI `grep` boundary check extension](09.0-documentation-ci/03-ci-boundary-check.md) | ✅   |
| 04      | [CI coverage gate extension](09.0-documentation-ci/04-ci-coverage-gate.md) | ✅   |
| 05      | [Milestone closeout + `CHANGELOG.md`](09.0-documentation-ci/05-milestone-closeout.md) | ✅   |

**Delivered:** Documentation and enforced CI gates closing the milestone.

- **Docs:** `docs/config/openclaude-setup.md` (overview, prerequisites, external +
  managed modes with the read-only allowlist launch flags, the
  `aegis code-intel check` verification step, the user-supplied-model contract
  callout, and health-check/allowlist troubleshooting) and
  `docs/config/openclaude-config-reference.md` (the eight-field `OpenClaudeSettings`
  table from C1, allowlist defaults + per-entry rationale, a worked
  `openclaude_agent` YAML example, and the seven-event C8 reference). Both are
  indexed under the "Code Intelligence" section in `docs/README.md`; the
  top-level `README.md` forward-link resolves. Both docs were moved from
  `docs/specs/` to `docs/` in the post-review remediation pass (initial
  placement was incorrect — all inbound links pointed at `docs/`, not
  `docs/specs/`). `check_doc_links.py` is clean on all touched files after the
  remediation.
- **CI (`.github/workflows/ci.yml`):**
  - `openclaude-isolation` — two hard grep rules (no `aegis_swr.openclaude`
    imports in `core/`/`views/`/`code_intel/`; no `grpc`/`_pb2` imports outside
    `openclaude/grpc/client.py`, generated proto excluded), **import-statement-aware**
    so the `grpc/__init__.py` docstring mention is not a false positive, plus a
    self-test step that drops a probe `import grpc`, asserts the guard flags it,
    and removes it — proving the guard turns red on a real violation.
  - `openclaude-unit-coverage` — runs `tests/unit/openclaude`, `code_intel`, and
    `test_app.py` with `OPENCLAUDE_GRPC_URL`/`OPENCLAUDE_INTEGRATION` empty; a
    `--cov-fail-under=90` overall gate and a separate `--cov-fail-under=100`
    branch gate scoped to `aegis_swr.openclaude.tool`.
  - `openclaude-integration` — gated to non-PR events on `master`/schedule; a
    nightly `schedule` trigger was added; the suite self-skips when the
    signal/binary are absent.
- **`pyproject.toml`:** registered the `integration` pytest marker (branch
  coverage was already enabled).
- **`CHANGELOG.md`:** new file with an `[Unreleased] — Milestone 0004` entry
  naming all nine tasks and recording the supersession of the original Code
  Intelligence Layer design and its accepted trade-offs.

**Key notes / deviations:**
- **`uv`, not `poetry`; `src/aegis_swr`, not `aegis/`.** The CI jobs use the
  repo's real toolchain (`uv sync` / `uv run pytest`) and package paths; coverage
  `--cov` targets use importable module names (`aegis_swr.openclaude.tool`) and
  clear the ini `addopts` via `-o addopts=""` so the scoped gate is not diluted by
  the global `--cov=src/aegis_swr` default.
- **Existing 85% global gate (`coverage.yml`) left intact** — the new gates are
  additive and scoped to the OpenClaude modules.
- **Global-acceptance verification (spot-checked):** `import grpc` only in
  `grpc/client.py` ✓; isolated modules clean ✓; backend registered only when
  `grpc_url` set ✓ (`test_app.py`); unit suite green with the var unset ✓
  (full unit suite green — 824 passed pre-remediation at 89.19% total);
  integration skips cleanly ✓ (4 modules skipped); `aegis code-intel check`
  completes with and without `OPENCLAUDE_GRPC_URL` set and opens no connection ✓;
  allowlist denial is non-corrupting and non-raising ✓; token charged
  post-completion ✓; `ruff` clean ✓; `tool.py` 100% branch ✓; proto stubs
  committed and reproducible via `uv run python scripts/proto_gen.py` ✓.

**Test coverage:** enforced in CI — ≥90% on the OpenClaude/code_intel/app modules
(currently 95.53%) and 100% branch on `tool.py`.

---

## Milestone complete

All nine tasks (01.0–09.0) are ✅. OpenClaude is wired as the sole, optional Code
Intelligence backend: enable with `OPENCLAUDE_GRPC_URL`, zero Python changes.
Post-review remediation (2026-07-10) resolved the composition-root orphan
(`app.py` deleted; `build_code_agent` in `openclaude/composition.py`; exposed via
`aegis code-intel check`) and the `CodeBackend` → `CodeIntelBackend` rename
(see [ADR 0003](/docs/adr/0003-code-intel-composition-root.md)). The full unit
suite is green (full unit suite green — 824 passed pre-remediation at 89.19%
total coverage; `tool.py` 100% branch), the live integration suite (10 tests)
skips cleanly without a sidecar, and CI enforces module isolation and the
OpenClaude coverage gates.
