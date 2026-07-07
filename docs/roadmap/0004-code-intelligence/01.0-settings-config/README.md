# Task 01.0 — OpenClaude Settings & Config

**Parent milestone:** [Milestone 0004 — OpenClaude Integration](/docs/roadmap/0004-code-intelligence/plan.md)
**Status:** ⬜ Not started

## Scope

This task establishes the entire configuration surface for the OpenClaude
integration. It creates the `aegis/openclaude/` package and
`aegis/openclaude/config.py` containing `OpenClaudeSettings`, a Pydantic
`BaseSettings` subclass whose fields are sourced entirely from environment
variables per contract C1 of the milestone. Validation rejects unknown
`allowed_tools` entries and malformed `grpc_url` values by raising
`OpenClaudeConfigError` (forward-declared in this task, formally defined in
Task 05.0). `OpenClaudeSettings` is the single object injected into
`OpenClaudeProcess` and `OpenClaudeTool`; no other module reads OpenClaude env
vars from `os.environ`.

This task also adds the `openclaude_agent` role to `aegis/config/agents.yaml`,
extends `RouterConfig` to parse and honour the new optional `enabled_when` key,
and wires `openclaude: OpenClaudeSettings` into the top-level settings object
that `app.py` composes.

> This task does **not** define any code-navigation abstraction
> (`CodeBackend`/`CodeAgent`/`CallBudget`). That minimal scaffolding belongs to
> `aegis/code_intel/` and is stood up in
> [Task 06.0](/docs/roadmap/0004-code-intelligence/06.0-app-wiring/README.md)
> per the milestone's Architecture section — Task 01.0 is configuration only.

## Assumptions

OpenClaude is installed as a **global npm package**
(`npm install -g @gitlawb/openclaude@latest`), not vendored into the
repository. It is treated as an opaque, versioned black-box service reached
over gRPC — Aegis SWR depends only on its published API contract (C2), never
on its internals or source layout. Consequences:

- Prerequisite: Node.js + npm on the host. `npm install -g
  @gitlawb/openclaude@latest` places an `openclaude` binary on `PATH`.
- `OpenClaudeSettings.process_binary` (`OPENCLAUDE_BINARY`) defaults to the
  bare command name `"openclaude"`, resolved via `PATH` — there is no in-repo
  vendored copy to point at.
- `poetry install` triggers the npm install automatically via a Poetry
  build-script hook (`scripts/postinstall_openclaude.py`, wired through
  `pyproject.toml`'s `[tool.poetry.build]` — see subtask 01), so the coding
  agent is available immediately after setting up the Python environment.
  The hook never fails `poetry install` outright: a missing Node.js/npm
  toolchain only blocks managed-mode (`auto_start=True`) launches, not the
  Python install itself — external-mode operators pointing at an
  already-running sidecar don't need the local binary at all.
- Version pinning is intentionally loose (`@latest`): OpenClaude is consumed
  as a black-box service behind the stable gRPC contract in C2, so this
  milestone does not pin an exact CLI version. Operators who need
  reproducible installs can override the npm spec when they run the install
  manually.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [`OpenClaudeSettings` Pydantic class](01-openclaude-settings.md) | ⬜ Not started | 03, 04, 03.0, 04.0, 05.0, 06.0 |
| 02 | [`agents.yaml` `openclaude_agent` role](02-agents-yaml-role.md) | ⬜ Not started | 03 |
| 03 | [`RouterConfig` `enabled_when` extension](03-router-config-enabled-when.md) | ⬜ Not started | - |
| 04 | [Settings composition in top-level config](04-settings-composition.md) | ⬜ Not started | 06.0 |

Subtasks 01 and 02 have no interdependency and may proceed in parallel.
Subtask 03 depends on subtask 02 (it parses the role that 02 adds). Subtask 04
depends on subtask 01 (it composes the settings object 01 defines).

## Key constraints

- All new code uses `Optional[T]` from `typing`, never `T | None`; and
  `from __future__ import annotations` at the top of every file (C9).
- `ruff` must be clean with zero new `# type: ignore` lines.
- Every new public class and function must have an RST-style docstring.
- `OpenClaudeConfigError` forward-declared in subtask 01 must be
  import-compatible with the canonical definition that Task 05.0 places in
  `exceptions.py` — downstream code must not require an import path change
  when 05.0 lands.
- No import of `OpenClaudeSettings` appears in `aegis/core/` or `aegis/ui/`
  (C3).

## Files created or modified by this task

```
aegis/
├── config/
│   └── agents.yaml              ← modified: openclaude_agent role (subtask 02)
├── openclaude/
│   ├── __init__.py              ← NEW (subtask 01, empty)
│   └── config.py                ← NEW (subtask 01)
└── router/
    └── config.py                ← modified: enabled_when (subtask 03)

scripts/
└── postinstall_openclaude.py    ← NEW (subtask 01): npm install -g hook

pyproject.toml                   ← modified (subtask 01): [tool.poetry.build] wiring

tests/openclaude/
└── unit/
    └── test_config.py           ← NEW: subtask 01 and 03 acceptance tests
```
