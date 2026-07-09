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
  `uv run python scripts/proto_gen.py` regenerates them; CI verifies the
  committed files match by re-running generation and diffing.
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

**Status:** ✅ Complete

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | [`openclaude.proto` schema](02.0-grpc-proto-client/01-proto-schema.md) | ✅   |
| 02      | [`proto_gen.py` script](02.0-grpc-proto-client/02-proto-gen-makefile.md) | ✅   |
| 03      | [`OpenClaudeGrpcClient` implementation](02.0-grpc-proto-client/03-grpc-client.md) | ✅   |
| 04      | [`health_check()` + timeout handling](02.0-grpc-proto-client/04-health-check-timeouts.md) | ✅   |

**Delivered:**
- `src/aegis_swr/openclaude/grpc/proto/openclaude.proto` — the authoritative C2
  wire contract (proto3, package `aegis.openclaude.v1`): `FrameType` enum,
  `AgentMessage`, `PromptRequest`, single server-streaming `AgentService.Query`.
- `scripts/proto_gen.py` + committed generated stubs
  (`openclaude_pb2.py`, `openclaude_pb2_grpc.py`). Stubs are generated with
  `--proto_path=src` so cross-stub imports are **package-qualified**
  (`from aegis_swr.openclaude.grpc.proto import openclaude_pb2`), avoiding the
  flat-import trap with no hand-edits. `grpcio-tools==1.82.1` pinned exact
  (dev-only) for byte-reproducible codegen; regeneration is idempotent.
  Invoke via `uv run python scripts/proto_gen.py`.
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
- `src/aegis_swr/openclaude/tool.py` — `OpenClaudeTool`, the sole `CodeBackend`
  (C4). `delegate(task, ctx)` runs ordered gates (C5): budget pre-check (zero gRPC
  calls if insufficient) → `dry_run` short-circuit (`[dry-run]`/0 tokens, zero
  calls) → stream. `_consume_stream` dispatches `AgentFrame`s by `FrameKind` via a
  handler map, accumulating `TEXT_CHUNK` and counting tool/frame events. On `DONE`
  it truncates to `max_response_tokens`, charges `max(1, len(text)//4)` (post-stream,
  success only), and emits the sole token-bearing `OpenClaudeStreamCompleted`.
  Permission gate, `ERROR`-frame and gRPC-error handling, and a defensive
  `except Exception` guarantee no exception escapes (C9). **100% branch coverage.**
- **`src/aegis_swr/code_intel/` scaffolding slice** (`backend.py`, `budget.py`,
  `agent.py`, `__init__.py`) — the minimal, backend-agnostic contract (`CodeBackend`
  ABC, `CodeResult`, `CodeTaskContext`, `CallBudget`, `CodeAgent`) that Task 06.0
  owns; built forward to unblock 04.0. C3-clean (imports neither `openclaude` nor
  `grpc`). **`app.py` composition wiring is deferred to Task 06.0** (it needs this
  `OpenClaudeTool`, so it cannot precede it).

**Key decisions & gate outcomes:**
- **Built to the canonical 06.0 contract, not the stale 04.0 spec wording:** public
  method is `delegate(task, ctx: CodeTaskContext) -> CodeResult` (not `run`);
  `CodeResult` is `(content, token_estimate, available, truncated, metadata)` with
  **per-call failures encoded in `metadata`** (`{ok, error, retriable}`), not
  `text`/`ok`/`retriable` fields; `ctx.run_id` is a `UUID` (→ `str()` for
  `query()`/events); frame types come from the client (`AgentFrame`/`FrameKind`);
  events use the real 05.0 signatures. Budget is a ctor-injected collaborator
  (`self._budget`).
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
