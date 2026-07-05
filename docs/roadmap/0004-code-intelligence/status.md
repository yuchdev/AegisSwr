# Milestone 0005 — OpenClaude Integration — Status

Tracks progress against [plan.md](/docs/roadmap/0004-code-intelligence/plan.md).
Updated as each task lands.

## Current status

| Task | Name                         | Status         | Tests |
|------|------------------------------|----------------|-------|
| 01.0 | OpenClaude Settings & Config | ⬜ Not started  | -     |
| 02.0 | gRPC Proto & Client          | ⬜ Not started  | -     |
| 03.0 | Process Lifecycle Manager    | ⬜ Not started  | -     |
| 04.0 | OpenClaudeTool Implementor   | ⬜ Not started  | -     |
| 05.0 | Event Types & Exceptions     | ⬜ Not started  | -     |
| 06.0 | App Wiring & agents.yaml     | ⬜ Not started  | -     |
| 07.0 | Test Suite — Unit            | ⬜ Not started  | -     |
| 08.0 | Test Suite — Integration     | ⬜ Not started  | -     |
| 09.0 | Documentation & CI           | ⬜ Not started  | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** task-level decomposition complete; implementation not
started. Each of the nine tasks has a `README.md` carrying its scope, subtask
list, and constraints; the numbered subtask specs are **deferred** and not yet
written. No `aegis/openclaude/` or `aegis/code_intel/` module exists yet;
`app.py` has no code-backend registration path; `agents.yaml` has no
`openclaude_agent` role.

## Notes & decisions

- **Supersedes Milestone 0004 (decided 2026-07-05).** OpenClaude is promoted
  from an optional fallback `CodeTool` to the central Code Intelligence
  mechanism. The bespoke tool-per-capability design in 0004 (`gtags` / `zoekt` /
  `tree-sitter` indices, six hand-built tools, a custom `ReActLoop`) is
  cancelled as duplicate effort — OpenClaude's own internal agentic loop
  provides the same navigation via `Bash`. Consequently 0005 now depends only
  on 0003, becomes the sole backend behind `aegis/code_intel/`, and stands up a
  minimal generic scaffolding (a `CodeBackend` contract, a `CodeAgent` entry
  point, and boundary-level `CallBudget` accounting) folded into task 06.0. The
  trade-off is accepted knowingly: token accounting degrades to a boundary
  estimate and correlation becomes model-driven rather than deterministic (see
  plan.md Background and [topology-notes.md](/docs/roadmap/0004-code-intelligence/topology-notes.md)).
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

The milestone is decomposed to the **task level**: 9 tasks, each with a
`README.md` carrying its scope, subtask names, and constraints. Numbered
subtask spec files are **not yet created** — the tree below shows the current
on-disk state; subtask names are tracked in each `README.md`'s `## Subtasks`
table (and mirrored in Per-task detail below) as forward-looking names only.

```
docs/roadmap/0004-code-intelligence/
├── plan.md                                       ← milestone spec (tasks, contracts C1–C9)
├── status.md                                     ← this tracker
├── topology-notes.md                             ← integration-topology analysis
├── 01.0-settings-config/README.md                ← configuration
├── 02.0-grpc-proto-client/README.md              ← infrastructure (gRPC isolation)
├── 03.0-process-lifecycle/README.md              ← infrastructure (subprocess mgmt)
├── 04.0-openclaude-tool/README.md                ← infrastructure (CodeTool impl)
├── 05.0-events-exceptions/README.md              ← infrastructure (EventBus types)
├── 06.0-app-wiring/README.md                     ← integration (+ code_intel scaffolding)
├── 07.0-test-suite-unit/README.md                ← testing (unit)
├── 08.0-test-suite-integration/README.md         ← testing (integration)
└── 09.0-documentation-ci/README.md               ← documentation & milestone closeout
```

Each task's `README.md` lists the planned subtask breakdown (3-6 subtasks per
task, ~38 planned in total); numbered `{NN}-{subtask-slug}.md` files are
written when that task is picked up for implementation, not before.

## Per-task detail

_Filled in as tasks complete. Subtask names below are the planned breakdown
from each task's README.md — not yet materialised as individual spec files._

### Task 01.0 — OpenClaude Settings & Config

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `OpenClaudeSettings` Pydantic class      | ⬜   |
| 02      | `agents.yaml` `openclaude_agent` role    | ⬜   |
| 03      | `RouterConfig` `enabled_when` extension  | ⬜   |
| 04      | Settings composition in top-level config | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 02.0 — gRPC Proto & Client

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `openclaude.proto` schema                | ⬜   |
| 02      | `make proto-gen` target                  | ⬜   |
| 03      | `OpenClaudeGrpcClient` implementation    | ⬜   |
| 04      | `health_check()` + timeout handling      | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 03.0 — Process Lifecycle Manager

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | External mode `__aenter__` / `__aexit__` | ⬜   |
| 02      | Managed mode subprocess start/stop       | ⬜   |
| 03      | Port-0 free-port selection               | ⬜   |
| 04      | stderr forwarding to `logger`            | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 04.0 — OpenClaudeTool Implementor

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | Tool skeleton + `input_schema`           | ⬜   |
| 02      | Stream processing + content accumulation | ⬜   |
| 03      | Permission request handling + allowlist  | ⬜   |
| 04      | Budget pre-check + truncation            | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 05.0 — Event Types & Exceptions

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | Seven event dataclasses                  | ⬜   |
| 02      | Three exception types                    | ⬜   |
| 03      | EventBus registry update                 | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 06.0 — App Wiring & agents.yaml

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `app.py` composition root update         | ⬜   |
| 02      | `--dry-run` path with `grpc_url` set     | ⬜   |
| 03      | `agents.yaml` `openclaude_agent` update  | ⬜   |
| 04      | `README.md` / `docs/setup.md` update     | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 07.0 — Test Suite — Unit

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `conftest.py` fixtures                   | ⬜   |
| 02      | `test_config.py`                         | ⬜   |
| 03      | `test_grpc_client.py`                    | ⬜   |
| 04      | `test_process.py`                        | ⬜   |
| 05      | `test_tool.py` (100% branch required)    | ⬜   |
| 06      | `test_events.py`                         | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 08.0 — Test Suite — Integration

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `integration/conftest.py` + skip guards  | ⬜   |
| 02      | `test_process_lifecycle.py`              | ⬜   |
| 03      | `test_grpc_stream.py`                    | ⬜   |
| 04      | `test_tool_live.py`                      | ⬜   |
| 05      | `test_allowlist_enforcement.py`          | ⬜   |

**Delivered:** —
**Test coverage:** —

---

### Task 09.0 — Documentation & CI

**Status:** ⬜ Not started

| Subtask | Description                              | Done |
|---------|------------------------------------------|------|
| 01      | `docs/openclaude-setup.md`               | ⬜   |
| 02      | `docs/openclaude-config-reference.md`    | ⬜   |
| 03      | CI `grep` boundary check extension       | ⬜   |
| 04      | CI coverage gate extension               | ⬜   |
| 05      | Milestone closeout + `CHANGELOG.md`      | ⬜   |

**Delivered:** —
**Test coverage:** —
