# Task 01.0 — OpenClaude Settings & Config

**Parent milestone:** [Milestone 0005 — OpenClaude Integration](/docs/roadmap/0005-openclaude/plan.md)
**Status:** ⬜ Not started

## Scope

Establish the configuration surface for the OpenClaude integration. Create the
`aegis/openclaude/` package (`__init__.py`) and `aegis/openclaude/config.py`
containing `OpenClaudeSettings`, a Pydantic `BaseSettings` subclass whose fields
are sourced entirely from environment variables per contract C1. Validation
must reject an unknown `allowed_tools` entry and a malformed `grpc_url`
(`host:port` shape) by raising `OpenClaudeConfigError` (defined in task 05.0).
`OpenClaudeSettings` is the single object injected into `OpenClaudeProcess` and
`OpenClaudeTool`; no other module reads OpenClaude env vars from `os.environ`.

This task also adds the `openclaude_agent` role to `aegis/config/agents.yaml`
(provider `openclaude`, model unset — the model is OpenClaude's concern —
`timeout_s`, and a new optional `enabled_when: OPENCLAUDE_GRPC_URL` key), and
extends `RouterConfig` in `aegis/router/config.py` to parse and honour
`enabled_when` on any role: when the named env var is absent the role is omitted
from the validated config rather than raising. Finally, it wires an
`openclaude: OpenClaudeSettings` field into the top-level settings object that
`app.py` composes.

## Assumptions

OpenClaude is vendored into the repository as a **git submodule** (path TBD,
e.g. `third_party/openclaude/`), not installed globally via `npm install -g`.
Consequences for this task:

- `OpenClaudeSettings.process_binary` (`OPENCLAUDE_BINARY`) defaults to the
  in-repo submodule's built entry point rather than assuming `openclaude` is
  already on `PATH`. The exact default path is finalised when the submodule is
  added; until then the field stays overridable so external-mode operators
  running their own OpenClaude install are unaffected.
- Checkout/CI must run `git submodule update --init --recursive` before any
  managed-mode (`auto_start=True`) test or launch can resolve the binary.
- The submodule's own build step (Node.js install + build) is a prerequisite
  documented in task 09.0, not reproduced here.

## Subtasks

| # | Name | Status |
|---|------|--------|
| 01 | `OpenClaudeSettings` Pydantic class | ⬜ Not started |
| 02 | `agents.yaml` `openclaude_agent` role | ⬜ Not started |
| 03 | `RouterConfig` `enabled_when` extension | ⬜ Not started |
| 04 | Settings composition in top-level config | ⬜ Not started |

## Key constraints

- All fields sourced from env vars per C1; defaults produce `grpc_url=None`
  (backend not registered) when nothing is set.
- `enabled_when` is ignored by the router itself (OpenClaude is not routed
  through LiteLLM); it exists only to suppress validation errors when the env
  var is absent. `RouterConfig.from_yaml()` must not raise when
  `OPENCLAUDE_GRPC_URL` is unset.
- Default `allowed_tools = Read,Grep,Glob,Bash`; default
  `bash_allowlist = gtags,global,semgrep,rg,find,cat`. Relaxing either requires
  an explicit override and an ADR.
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations`; `mypy --strict` clean with no new ignores (C9).
