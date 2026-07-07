# Milestone 0004 — OpenClaude Integration

**Package:** `aegis-swr` | **Module root:** `aegis/openclaude/`
**Depends on:** Milestone 0003 (LiteLLM Model Router; `aegis/router/` in its
final state).

This milestone integrates [OpenClaude](https://github.com/Gitlawb/openclaude)
as the **central Code Intelligence mechanism** for Aegis SWR. OpenClaude is a
fork of the Claude Code source (exposed via npm source maps on March 31, 2026,
then extended with an OpenAI-compatible provider shim) that can be pointed at
any OpenAI-compatible backend, including the project's own vLLM instance. It
runs as a headless gRPC sidecar; Aegis SWR delegates an open-ended code
navigation task to it and OpenClaude's **own internal agentic loop** (its
`Read` / `Grep` / `Glob` / `Bash` tools) does the multi-file work, calling out
to `gtags` / `semgrep` / `zoekt` CLIs via `Bash` when they are present.

After this milestone, an operator who runs a local or self-hosted
OpenAI-compatible endpoint can wire that model into Aegis SWR's code
intelligence with a single environment variable (`OPENCLAUDE_GRPC_URL`) and
zero Python changes.

> **Supersedes the original Code Intelligence Layer design.** This milestone
> was renumbered from 0005 to 0004 after the bespoke tool-per-capability design
> (`aegis/code_intel/` with `gtags` / `zoekt` / `tree-sitter` indices, six
> hand-built `CodeTool`s and a custom `ReActLoop`) was cancelled as duplicate
> effort and its plan document removed. OpenClaude's own agentic loop replaces
> it. See [status.md](/docs/roadmap/0004-code-intelligence/status.md#notes--decisions)
> for the full decision record.

---

## Background

Milestone 0004 proposed a structured, tool-per-capability code intelligence
layer: a `CodeTool` protocol with six specialised tools (symbol lookup, caller
graph, semantic search, AST slice, semgrep, crash correlator), three index
backends (`gtags`, `zoekt`, `tree-sitter`), a `TokenBudget`, and a custom
`ReActLoop` that reasons about which tool to call next. That design is sound
but expensive: it re-implements, tool by tool, the navigation loop that a
Claude-Code-class agent already performs natively.

OpenClaude collapses that effort. Instead of Aegis SWR building and
orchestrating a fleet of navigation tools, it delegates one open-ended task
string to OpenClaude and lets OpenClaude's internal loop navigate. OpenClaude 
serves as a gRPC sidecar behind a single delegation surface. 
OpenClaude-via-`Bash` can cover every capability the bespoke tools would 
have provided: symbol lookup, caller-graph traversal, semantic search, 
and AST slicing all become `Bash` invocations of the same CLIs 
the native tools would have wrapped.

The trade-off is honest and must be carried through the design, not hidden:

- **Gain.** One integration replaces fourteen tasks of bespoke tooling; the
  user's own model drives navigation; adding OpenClaude is a single env var.
- **Cost — token opacity.** OpenClaude's internal per-step token usage is not
  visible to Aegis SWR. Budget accounting degrades from per-tool exactness to a
  boundary estimate derived from streamed response length (C5).
- **Cost — non-deterministic correlation.** The crash correlator was a
  deterministic pure function in 0004; under OpenClaude the equivalent
  reasoning is model-driven and non-deterministic.
- **Cost — live-process testability.** Full-path testing needs a live Node.js
  process; mitigated by a mock-gRPC-client seam so unit tests never start one
  (C3, task 07.0).
- **Cost — wider execution surface.** `Bash` is a broader attack surface than
  purpose-built tools; mitigated by a strict tool allowlist and a `Bash`
  binary allowlist enforced at launch and probe time (C1, C7).

### OpenClaude's central role in Code Intelligence

This milestone stands OpenClaude up as the **sole backend behind
`aegis/code_intel/`**. Because 0004 no longer exists to supply generic
scaffolding, 0004 also stands up a *minimal* version of what Code Agent needs
generically: a thin, backend-agnostic `CodeBackend` contract, a `CodeAgent`
entry point that delegates a task and returns a text result, and
boundary-level token/cost accounting for the delegated call. This scaffolding
is deliberately small — there is no multi-tool selection loop on the Aegis SWR
side any more. When `OPENCLAUDE_GRPC_URL` is unset, no `CodeBackend` is
registered and code-intelligence capability is simply unavailable; there are no
sibling tools to fall back to or from.

### Why gRPC, not MCP

OpenClaude exposes a headless gRPC service with bidirectional streaming and an
inherited MCP-over-stdio mode. gRPC is chosen because its stream maps directly
onto Aegis SWR's `EventBus` (per-frame event emission without polling), its
stubs are generated from a committed proto schema (an explicit, mockable
contract that needs no live Node.js process in unit tests), and it avoids the
subprocess-lifetime complexity that stdio MCP would introduce into Aegis SWR's
async architecture. See status.md for the full decision record.

### User-supplied model contract

Aegis SWR does not manage OpenClaude's provider configuration — it treats
OpenClaude as a black box that accepts a task and returns a response stream.
The operator sets OpenClaude's own environment variables
(`CLAUDE_CODE_USE_OPENAI`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`)
before launch. Aegis SWR needs only `OPENCLAUDE_GRPC_URL` to locate the running
server. Tool quality depends heavily on the chosen model; smaller local models
struggle with long multi-step flows — a runtime concern the integration test
suite must exercise (task 08.0).

---

## Architecture

```
agents.yaml
    │  (openclaude_agent role; enabled_when OPENCLAUDE_GRPC_URL)
    ▼
aegis/code_intel/                    ← MINIMAL SCAFFOLDING (stood up here; 0004 superseded)
    backend.py      ← CodeBackend contract: delegate(task) → CodeResult; token accounting seam
    agent.py        ← CodeAgent: the entry point Code Agent calls to delegate a code task
    budget.py       ← CallBudget: boundary-level token/cost accounting for one delegated call
    │
    │  (sole CodeBackend, injected at app.py when OPENCLAUDE_GRPC_URL is set)
    ▼
aegis/openclaude/
    config.py       ← OpenClaudeSettings: env-var config, tool + bash allowlists
    tool.py         ← OpenClaudeTool: the CodeBackend implementation; delegates the task string
    process.py      ← OpenClaudeProcess: sidecar lifecycle (start / stop / health)
    events.py       ← OpenClaude* EventBus event dataclasses
    exceptions.py   ← OpenClaudeUnavailableError, PermissionDeniedError, OpenClaudeConfigError
    grpc/
        client.py   ← OpenClaudeGrpcClient: the ONLY file that imports grpc; stream → CodeResult
        proto/      ← vendored .proto + committed generated stubs
    ▼  (gRPC bidirectional stream)
OpenClaude headless sidecar (Node.js)
    └── internal agentic loop: Read / Grep / Glob / Bash (allowlisted)
          └── optional CLIs via Bash: gtags / semgrep / zoekt (if present)
                └── OpenAI-compatible backend (operator's vLLM / any endpoint)
```

**Hard isolation boundary:** `aegis/core/`, `aegis/ui/`, and `aegis/code_intel/`
must never import `aegis.openclaude` or `grpc`. The backend is injected via
constructor at the `app.py` composition root; no agent or scaffolding module
imports it directly. Enforced by a `grep` CI check (C3).

**OpenClaude process boundary:** `aegis/openclaude/process.py` is the only file
that starts, stops, or health-checks the OpenClaude Node.js subprocess.

---

## Tasks

| Task | Name                          | Category       | Output                                                                              |
|------|-------------------------------|----------------|-------------------------------------------------------------------------------------|
| 01.0 | OpenClaude Settings & Config  | configuration  | `config.py`, `agents.yaml` `openclaude_agent` role, env-var contract                |
| 02.0 | gRPC Proto & Client           | infrastructure | `grpc/proto/`, `grpc/client.py` — stub, stream adapter, mock-friendly interface     |
| 03.0 | Process Lifecycle Manager     | infrastructure | `process.py` — start/stop/health, async context manager, EventBus emissions         |
| 04.0 | OpenClaudeTool Implementor    | infrastructure | `tool.py` — the sole `CodeBackend`; budget enforcement, tool allowlist, dry-run     |
| 05.0 | Event Types & Exceptions      | infrastructure | `events.py`, `exceptions.py` — typed frozen dataclasses, EventBus integration       |
| 06.0 | App Wiring & agents.yaml      | integration    | `code_intel/` scaffolding + `app.py` composition root; backend registration; dry-run |
| 07.0 | Test Suite — Unit             | testing        | All `tests/openclaude/unit/`; mock gRPC client; 100% branch on `tool.py`            |
| 08.0 | Test Suite — Integration      | testing        | All `tests/openclaude/integration/`; live OpenClaude process; skipped when absent   |
| 09.0 | Documentation & CI            | documentation  | Setup guide, config reference, CI additions, milestone closeout                     |

Tasks 01.0 → 02.0 → 03.0 are sequential foundations. Task 04.0 depends on 02.0
and 03.0. Task 05.0 depends on 01.0 and can be written alongside 02.0. Task
06.0 depends on 04.0 and 05.0 and additionally stands up the minimal
`aegis/code_intel/` scaffolding (backend contract, `CodeAgent` entry point,
`CallBudget`) that 0004 would otherwise have supplied. Tasks 07.0 and 08.0 are
written **incrementally alongside** their corresponding implementation tasks.
Task 09.0 closes the milestone.

---

## Communication architecture: three viable topologies

### Topology A — OpenClaude as a `CodeTool` via gRPC (recommended)

```
Aegis SWR ReActLoop
  └── OpenClaudeTool (implements CodeTool protocol)
        └── gRPC stub → OpenClaude headless server
              └── provider shim → OPENAI_BASE_URL (user's vLLM)
                    └── Qwen3-235B on Vast.ai
```

OpenClaude runs as a long-lived sidecar process started by `app.py`. `OpenClaudeTool.run()` sends a prompt over gRPC, streams back the result, wraps it in `ToolResult`, charges `TokenBudget`, and emits `CodeIntelLoopStepEvent`. From Aegis SWR's perspective it is just another `CodeTool` — fully behind the protocol boundary, mockable, observable.

The permission request stream from OpenClaude's gRPC server (it asks for confirmation before destructive Bash commands) needs to be handled by your Python gRPC client. For forensic read-only analysis you would configure OpenClaude with a tool allowlist restricting it to `Read`, `Grep`, `Glob`, and your index binaries (`gtags`, `global`, `semgrep`), which eliminates the permission dialog entirely.

### Topology B — OpenClaude as an MCP server, Aegis SWR as MCP client

```
Aegis SWR ReActLoop
  └── OpenClaudeMCPTool (implements CodeTool protocol)
        └── MCP client (stdio or SSE transport)
              └── OpenClaude mcp serve (Node.js process)
                    └── provider shim → user's vLLM
```

This is the same topology as "Claude Code as tool" but now the model is user-supplied. The problems from the previous discussion (token opacity, non-deterministic correlator, EventBus blindness) apply identically here. The user-supplied backend doesn't resolve those structural issues.

### Topology C — OpenClaude as the primary orchestrator (inverted)

```
OpenClaude (user's terminal, user's model)
  └── MCP client connects to Aegis SWR MCP server
        └── aegis_swr mcp serve
              ├── tool: analyze_incident(crash, logs) → verdict
              ├── tool: get_event_log(run_id) → JSONL
              └── tool: get_budget_snapshot(run_id) → BudgetSnapshot
```

Here the roles invert: OpenClaude is the front-end the user drives, and Aegis SWR exposes itself as an MCP server with high-level forensic tools. This is interesting for a "power user" workflow where someone investigates an incident interactively through OpenClaude, using Aegis SWR's pipeline as a structured sub-capability.

---


## Shared contracts (authoritative)

These contracts are defined once here; per-task READMEs reference them.

### C1 — OpenClaude settings

All configuration lives in `OpenClaudeSettings`, a Pydantic settings class
sourced from environment variables. It is injected into `OpenClaudeProcess` and
`OpenClaudeTool` at construction; never read from `os.environ` directly inside
tool or process code.

| Field                 | Env var                      | Default        | Notes                                        |
|-----------------------|------------------------------|----------------|----------------------------------------------|
| `grpc_url`            | `OPENCLAUDE_GRPC_URL`        | `None`         | `None` = backend not registered              |
| `allowed_tools`       | `OPENCLAUDE_ALLOWED_TOOLS`   | see below      | Comma-separated Claude Code tool names       |
| `bash_allowlist`      | `OPENCLAUDE_BASH_ALLOWLIST`  | see below      | Comma-separated binary names for the Bash tool |
| `max_response_tokens` | `OPENCLAUDE_MAX_TOKENS`      | `4096`         | Hard cap on streamed response length         |
| `connect_timeout_s`   | `OPENCLAUDE_CONNECT_TIMEOUT` | `10`           | gRPC channel connect timeout                 |
| `request_timeout_s`   | `OPENCLAUDE_REQUEST_TIMEOUT` | `120`          | Per-request stream deadline                  |
| `auto_start`          | `OPENCLAUDE_AUTO_START`      | `False`        | Whether `app.py` starts the sidecar process  |
| `process_binary`      | `OPENCLAUDE_BINARY`          | `openclaude`   | Binary name or full path                     |

Default `allowed_tools`: `Read,Grep,Glob,Bash` — write tools are excluded for
forensic read-only safety. Default `bash_allowlist`:
`gtags,global,semgrep,rg,find,cat` — the navigation CLIs OpenClaude may shell
out to, ensuring it cannot execute arbitrary shell commands. Any relaxation of
either allowlist requires an explicit override and an ADR.

### C2 — gRPC stream contract

OpenClaude's gRPC service exposes a single `Query` RPC that takes a prompt plus
a run id and returns a **stream of agent-message frames**. Each frame carries a
message type, a `content` string (text chunk, tool-call JSON, tool output, or
error message), and an optional `tool` name. The frame types are:

| Frame type      | Meaning                                             |
|-----------------|-----------------------------------------------------|
| `TEXT_CHUNK`    | Incremental response text                           |
| `TOOL_CALL`     | Tool invocation (`tool` name + args JSON in content) |
| `TOOL_RESULT`   | Tool output                                         |
| `PERMISSION_REQ`| Requires confirmation before proceeding             |
| `DONE`          | Terminal frame; carries the full response text      |
| `ERROR`         | Terminal error frame                                |

`OpenClaudeGrpcClient` consumes the stream and produces a single text result:
the concatenation of all `TEXT_CHUNK` content up to `DONE`. `TOOL_CALL` and
`TOOL_RESULT` frames are translated into `OpenClaudeToolCall` /
`OpenClaudeToolResult` emissions on the `EventBus` (C8). A `PERMISSION_REQ`
frame for a command inside the `bash_allowlist` is auto-approved by the client;
one outside the allowlist raises `PermissionDeniedError` (a non-retriable
failure), emits `OpenClaudePermissionDenied`, and halts that invocation.
`PERMISSION_REQ` frames are never forwarded to a human — Aegis SWR runs
OpenClaude non-interactively. The exact message/enum/service names live in the
proto schema authored in task 02.0, not here.

### C3 — Module isolation boundary

- `aegis/core/` and `aegis/ui/` contain **zero** imports of `aegis.openclaude`
  or `grpc`.
- `aegis/code_intel/` contains **zero** imports of `aegis.openclaude` — the
  backend is injected, not imported by the scaffolding.
- `aegis/openclaude/grpc/client.py` is the only file that imports `grpc` or the
  generated `_pb2` stubs.
- `aegis/openclaude/process.py` is the only file that manages the OpenClaude
  subprocess.
- Enforced by a `grep` CI check, structurally identical to the Milestone 0003
  provider-isolation check.

### C4 — Backend registration contract

`OpenClaudeTool` is the sole `CodeBackend` implementation. It is instantiated
and registered as the active code-intelligence backend **only** when
`OpenClaudeSettings.grpc_url is not None`. That branch lives exclusively in
`app.py`; no other module branches on OpenClaude's presence. When `grpc_url` is
`None`, `CodeAgent` is constructed without a backend and code-intelligence
requests report the capability as unavailable — there are no other backends to
fall back to. Adding OpenClaude to a deployment therefore requires only setting
`OPENCLAUDE_GRPC_URL`, with no Python changes.

### C5 — Token budget interaction

Budget accounting occurs at the **delegation boundary** only. Aegis SWR cannot
observe OpenClaude's internal per-step token usage (this is the token-opacity
cost noted in Background), so the figure is a conservative boundary estimate,
not an exact count.

1. Before issuing the gRPC request, `OpenClaudeTool` performs a `CallBudget`
   pre-check against `max_response_tokens // 4`. If the budget is insufficient,
   it returns a non-retriable failure without opening a connection.
2. After the stream completes, the call is charged an estimate of
   `max(1, len(content) // 4)` tokens (the GPT-style approximation carried over
   from the router/budget convention).
3. `--dry-run` skips the gRPC call entirely and returns a `[dry-run]` result
   with a zero token estimate.
4. Accumulated `content` is truncated at `max_response_tokens`; truncation is
   flagged in the result metadata.

### C6 — Process lifecycle contract

`OpenClaudeProcess` is an async context manager exposing a ready `grpc_url`
inside the `with` block and supporting two modes:

- **External** (`auto_start=False`, default): assumes OpenClaude is already
  running; performs only a health check against the gRPC endpoint and raises
  `OpenClaudeUnavailableError` if unreachable.
- **Managed** (`auto_start=True`): launches the OpenClaude binary as a
  subprocess (via `asyncio.create_subprocess_exec`, never `subprocess.Popen` in
  an async path), waits for the gRPC port to open (up to `connect_timeout_s`
  with `asyncio.sleep` backoff), and terminates the process on context exit
  (`SIGTERM`, then `SIGKILL` after a grace period).

`OpenClaudeConnected` is emitted exactly once on successful entry and
`OpenClaudeDisconnected` exactly once on exit, in both modes. Managed mode must
always terminate the process on exit even if entry raised after the port
opened. Subprocess stderr is forwarded to the logger at `DEBUG`; stdout is
discarded (gRPC output travels on the channel, not stdout).

### C7 — Permission and tool allowlist enforcement

OpenClaude is launched with a tool allowlist and a `Bash` binary allowlist
derived from `settings.allowed_tools` and `settings.bash_allowlist`. In managed
mode Aegis SWR passes these as CLI flags at startup; in external mode the flags
are the operator's responsibility and Aegis SWR documents them (task 09.0) and
validates them at health-check time via a probe request. If a disallowed tool
or binary is exercised during the probe, `OpenClaudeUnavailableError` is raised
at startup rather than mid-incident. At runtime, a `PERMISSION_REQ` frame for a
non-allowlisted command is denied per C2. Forensic analysis is read-only; the
allowlist is the mechanism that guarantees OpenClaude cannot mutate the
repository under analysis.

### C8 — OpenClaude event taxonomy

All event types are `frozen=True` dataclasses on the existing `EventBus`,
carrying `run_id` and a UTC `timestamp` and a `ClassVar[str]` `event_type`
sentinel.

| Class                        | `event_type`                   | When emitted                                  |
|------------------------------|--------------------------------|-----------------------------------------------|
| `OpenClaudeConnected`        | `openclaude.connected`         | After successful health check / process start |
| `OpenClaudeDisconnected`     | `openclaude.disconnected`      | On process stop or connection loss            |
| `OpenClaudeToolCall`         | `openclaude.tool_call`         | On each `TOOL_CALL` frame from the stream     |
| `OpenClaudeToolResult`       | `openclaude.tool_result`       | On each `TOOL_RESULT` frame from the stream   |
| `OpenClaudePermissionDenied` | `openclaude.permission_denied` | On `PERMISSION_REQ` for a disallowed command  |
| `OpenClaudeStreamCompleted`  | `openclaude.stream_completed`  | On `DONE`; carries `token_estimate`           |
| `OpenClaudeStreamError`      | `openclaude.stream_error`      | On `ERROR` frame or gRPC status error         |

`OpenClaudeStreamCompleted` is the only event carrying the boundary token
estimate; it is never duplicated across events.

### C9 — Cross-cutting conventions (inherited from 0001–0003)

- `Optional[T]` from `typing`, never `T | None` (including in subscripts and
  `Annotated[...]`).
- `from __future__ import annotations` in every new file.
- `ruff` and `replace_optional.py --check` must stay clean.
- Every new public class/function has an RST-style docstring.
- No `grpc` import in `aegis/core/`, `aegis/ui/`, or `aegis/code_intel/`.
- `--dry-run` short-circuits `OpenClaudeTool` to a `[dry-run]` result with zero
  tokens, without opening a gRPC connection.
- `asyncio.sleep` for backoff — never `time.sleep`.
- Loguru with `SensitiveFilter` on every sink; no raw incident payload text
  (dump/log/stack) is ever logged, and the streamed response is never logged
  unredacted.
- Generated proto files (`_pb2.py`, `_pb2_grpc.py`) are committed under
  `aegis/openclaude/grpc/proto/`, regenerated via a `Makefile` target, and
  committed without extra typing-only exclusions.

---

## Dependency graph

```
Task 01.0 (Settings & Config)
   │
   ├──► Task 02.0 (gRPC Proto & Client)
   │         │
   │         └──► Task 03.0 (Process Lifecycle)
   │                    │
   │                    └──► Task 04.0 (OpenClaudeTool)
   │                               │
   └──► Task 05.0 (Events & Exceptions) ──► Task 04.0
                                                │
                              Task 04.0 + 05.0 ─┤
                                                └──► Task 06.0 (App Wiring + code_intel scaffolding)
                                                           │
                             Tasks 01–06 ─────────────────┤
                                                          ├──► Task 07.0 (Unit Tests)        ← incremental
                                                          ├──► Task 08.0 (Integration Tests) ← incremental
                                                          └──► Task 09.0 (Docs & CI)
```

**Minimum viable:** 01.0 → 02.0 → 03.0 → 04.0 → 05.0 → 06.0 → 07.0 (unit only).
**Full milestone:** all nine tasks including live integration tests and documentation.

---

## File map (target state after milestone)

```
aegis/
├── app.py                              ← updated: CodeBackend registration (gated on OPENCLAUDE_GRPC_URL)
├── config/
│   └── agents.yaml                     ← updated: openclaude_agent role
├── code_intel/                         ← NEW MINIMAL SCAFFOLDING (0004 superseded)
│   ├── __init__.py
│   ├── backend.py                      ← CodeBackend contract + CodeResult
│   ├── agent.py                        ← CodeAgent entry point
│   └── budget.py                       ← CallBudget (boundary token/cost accounting)
└── openclaude/                         ← NEW MODULE
    ├── __init__.py
    ├── config.py                       ← OpenClaudeSettings
    ├── tool.py                         ← OpenClaudeTool (the sole CodeBackend)
    ├── process.py                      ← OpenClaudeProcess (lifecycle manager)
    ├── events.py                       ← seven event dataclasses
    ├── exceptions.py                   ← three exception types
    └── grpc/
        ├── __init__.py
        ├── client.py                   ← ONLY file that imports grpc
        └── proto/
            ├── openclaude.proto
            ├── openclaude_pb2.py        ← generated; committed
            └── openclaude_pb2_grpc.py   ← generated; committed

tests/
└── openclaude/                         ← NEW
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_config.py
    │   ├── test_grpc_client.py
    │   ├── test_process.py
    │   ├── test_tool.py
    │   └── test_events.py
    └── integration/
        ├── __init__.py
        ├── conftest.py
        ├── test_process_lifecycle.py
        ├── test_grpc_stream.py
        ├── test_tool_live.py
        └── test_allowlist_enforcement.py

docs/
    ├── openclaude-setup.md             ← NEW
    └── openclaude-config-reference.md  ← NEW

Makefile                                ← updated: proto-gen target
```

---

## Global acceptance criteria

- [ ] `import grpc` appears in exactly one file: `aegis/openclaude/grpc/client.py`
- [ ] `aegis/core/`, `aegis/ui/`, and `aegis/code_intel/` contain no imports of
      `aegis.openclaude` or `grpc`
- [ ] `OpenClaudeTool` is only instantiated/registered when `OPENCLAUDE_GRPC_URL`
      is set; absent it, code-intel capability is reported unavailable
- [ ] All unit tests pass with `OPENCLAUDE_GRPC_URL` unset and no OpenClaude
      binary on `PATH`
- [ ] Integration tests are **skipped** (not failed) when binary or env var absent
- [ ] `python -m aegis.app --dry-run` completes with no API keys, no
      `OPENCLAUDE_GRPC_URL`, and no OpenClaude binary
- [ ] `python -m aegis.app --dry-run` with `OPENCLAUDE_GRPC_URL` set does not
      attempt a gRPC connection
- [ ] `OpenClaudeTool` enforces `bash_allowlist`; a non-allowlisted
      `PERMISSION_REQ` is denied without corrupting boundary budget accounting
- [ ] Token budget is charged after stream completion, not pre-charged
- [ ] Adding OpenClaude to a deployment requires only setting `OPENCLAUDE_GRPC_URL`
      — zero Python changes
- [ ] No raw incident payload or unredacted response text reaches any log sink
- [ ] All new public classes and functions have RST docstrings
- [ ] `ruff`, `replace_optional.py --check` all clean
- [ ] Coverage: ≥ 90% overall unit; 100% on `tool.py`
- [ ] Proto schema is committed; `make proto-gen` reproduces identical output
