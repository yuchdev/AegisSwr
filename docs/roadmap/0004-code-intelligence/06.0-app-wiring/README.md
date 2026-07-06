# Task 06.0 — App Wiring & agents.yaml

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

Stand up the minimal generic Code Intelligence scaffolding and wire OpenClaude
in as its sole backend. Because Milestone 0004 is superseded, this task creates
the thin `aegis/code_intel/` package that 0004 would otherwise have supplied:
`backend.py` (a backend-agnostic `CodeBackend` contract plus a `CodeResult`),
`agent.py` (`CodeAgent` — the entry point Code Agent calls to delegate a code
task and receive text back), and `budget.py` (`CallBudget` — boundary-level
token/cost accounting for one delegated call). This scaffolding is deliberately
small: there is no multi-tool ReAct loop, no tool registry, no index backends.

Update the `app.py` composition root to instantiate `OpenClaudeSettings` and,
**only when `grpc_url is not None`** (contract C4), construct
`OpenClaudeGrpcClient`, `OpenClaudeProcess` (as a context-managed startup/
shutdown resource), and `OpenClaudeTool`, and register the tool as the active
`CodeBackend` for `CodeAgent`. When `grpc_url` is `None`, `CodeAgent` is
constructed without a backend and reports the capability unavailable. `--dry-run`
must not start the process even with `OPENCLAUDE_GRPC_URL` set: the backend is
still registered so the full composition path is exercised, but `ctx.dry_run`
short-circuits every gRPC call. Finalise the `openclaude_agent` role in
`agents.yaml` (realistic `timeout_s`, note that model is OpenClaude's concern),
and document the minimum enabling env vars and the recommended external-mode
launch command in the top-level `README.md` / `docs/`.

The generic scaffolding above is stood up as part of the composition-root
subtask; the remaining subtasks cover the dry-run path, the `agents.yaml`
finalisation, and the README/setup update.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [`app.py` composition root update (+ `code_intel/` scaffolding)](01-code-intel-scaffolding-and-app-wiring.md) | ⬜ Not started | 02, 03, 04; Task 07.0 |
| 02 | [`--dry-run` path with `grpc_url` set](02-dry-run-path.md) | ⬜ Not started | - |
| 03 | [`agents.yaml` `openclaude_agent` update](03-agents-yaml-finalisation.md) | ⬜ Not started | - |
| 04 | [`README.md` / `docs/setup.md` update](04-readme-update.md) | ⬜ Not started | - |

## Key constraints

- The `grpc_url is not None` branch lives **only** in `app.py`; no other module
  branches on OpenClaude's presence (C4).
- `aegis/code_intel/` scaffolding contains **zero** imports of
  `aegis.openclaude` or `grpc`; the backend is injected via constructor (C3).
- `python -m aegis.app --dry-run` completes with no API keys, no
  `OPENCLAUDE_GRPC_URL`, and no OpenClaude binary on `PATH`; with
  `OPENCLAUDE_GRPC_URL` set it registers the backend but attempts no gRPC
  connection. Concretely, `--dry-run` skips `OpenClaudeProcess.__aenter__()`
  (and thus the C6 health check) entirely while still constructing and
  registering the backend — see subtask 02 for the resolution of this
  acceptance-criterion-vs-C6 tension.
- `CodeAgent` is constructible with an all-mock backend in a unit test with zero
  real processes.
- No import of `aegis.openclaude` appears in `aegis/core/` or `aegis/ui/`.
- Scaffolding stays minimal — no speculative multi-tool machinery.
