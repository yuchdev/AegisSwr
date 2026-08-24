# Task 02.0 — Claude Code Settings & Config

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

This task establishes the entire configuration surface for the **Claude Code**
backend (the installed `claude` CLI). It creates the `aegis_swr/claude_code/`
package and `aegis_swr/claude_code/config.py` containing `ClaudeCodeSettings`, a
Pydantic `BaseSettings` subclass whose fields are sourced entirely from
environment variables per milestone contract **C5** (the backend
settings-shape convention) and **C6 item 4** (the Claude Code field set). The
class mirrors `OpenClaudeSettings`' proven shape exactly: a per-family
`env_prefix` (`CLAUDE_CODE_`), an `EnvSettingsSource` subclass plus a
`mode="before"` coercion validator for CSV parsing of `list[str]` fields,
`field_validator`s that raise the backend's own typed config error (unwrapped
from Pydantic's `ValidationError` in `__init__`), and **presence-signal-as-
falsy-default** so an absent configuration means "backend not configured"
rather than a construction crash.

Per **C6 items 3-4** this task also encodes the backend's no-sandbox security
posture into settings-time validation: `allowed_tools` defaults to a read-only
set (`Read,Grep,Glob`), write-capable tools default off, `permission_mode`
defaults to a non-bypassing mode and **rejects any bypass-permissions value**
(anything that would produce `--dangerously-skip-permissions`), and a
**mandatory disposable `scratch_cwd`** is validated whenever the backend is
enabled. Together with the one-shot subprocess isolation added in Task 03.0,
these three settings are the *only* guards standing in for the sandbox that
Claude Code does not have.

> This task is **configuration only**. It does not spawn the `claude`
> subprocess, construct any argv, parse NDJSON, or perform token accounting —
> that is [Task 03.0](/docs/roadmap/0005-harness-backends/plan.md) (the
> subprocess tool). It also does **not** compose `ClaudeCodeSettings` into
> `HarnessSettings` — that nesting is owned by
> [Task 01.0](/docs/roadmap/0005-harness-backends/plan.md) (C1), which composes
> this class by name once it exists. There is no direct code dependency on
> 01.0; the two proceed in parallel.

## Additive-extension guarantee (Task 04.0)

`ClaudeCodeSettings` is deliberately scoped so that
[Task 04.0](/docs/roadmap/0005-harness-backends/plan.md) can add the
`auth_mode` field (`CLAUDE_CODE_AUTH_MODE`; `auto` | `api_key` | `subscription`,
per **C7**) **additively** — one new field plus its own validator — with **no
restructuring** of the fields or validators defined here. Concretely:

- No field defined in this task cross-validates against a not-yet-existing
  `auth_mode`. The `permission_mode` and `scratch_cwd` validators are
  auth-mode-agnostic.
- The `__init__` `ValidationError`-unwrap and the `settings_customise_sources`
  CSV env source are written once here and are reused unchanged by 04.0's new
  validator.
- `ClaudeCodeConfigError` (forward-declared here, see below) is the same error
  type 04.0's `auth_mode` validator will raise for the ambiguous-credential
  rejection — no new base type is introduced.

## Forward-declared exception

`ClaudeCodeConfigError` is **forward-declared in subtask 01** exactly as
Milestone 0004 Task 01.0 subtask 01 forward-declared `OpenClaudeConfigError`.
It is a temporary same-name placeholder living in `config.py` so this task's
validators can raise a domain error without depending on a not-yet-written
module. [Task 05.0](/docs/roadmap/0005-harness-backends/plan.md) supplies the
**canonical definition** in `aegis_swr/claude_code/exceptions.py` and replaces
the placeholder with a re-export alias
(`from aegis_swr.claude_code.exceptions import ClaudeCodeConfigError as ClaudeCodeConfigError`),
mirroring how `openclaude/config.py` re-exports its canonical error today.
**No downstream import path changes** when 05.0 lands: code importing
`aegis_swr.claude_code.config.ClaudeCodeConfigError` continues to resolve to
the same object.

## Subtasks

| #  | Document                                                                          | Status         | Blocks                     |
|----|-----------------------------------------------------------------------------------|----------------|----------------------------|
| 01 | [`ClaudeCodeSettings` class shape](01-claude-code-settings.md)                    | ⬜ Not started | 02 (this task), 03.0, 05.0 |
| 02 | [`permission_mode` & disposable `scratch_cwd`](02-permission-mode-scratch-cwd.md) | ⬜ Not started | 03.0                       |

Subtask 01 establishes the class, the CSV env source, the `__init__` unwrap,
and the `binary_path` / `enabled` / `allowed_tools` / `max_turns` /
`request_timeout_s` fields. Subtask 02 adds the two security-guard fields
(`permission_mode`, `scratch_cwd`) and their validators onto the same class, so
**subtask 02 depends on subtask 01** (it extends the class 01 defines). Both
subtasks land in the same `config.py` file.

## Dependencies

- **Depends on:** Task 01.0 (sibling, **no direct code dependency**).
  `HarnessSettings` composes `ClaudeCodeSettings` by name via `default_factory`
  once this class exists (C1); the two tasks proceed in parallel.
- **Blocks:** Task 03.0 (the subprocess tool reads `binary_path`,
  `allowed_tools`, `permission_mode`, `max_turns`, `request_timeout_s`, and
  `scratch_cwd` to construct the invocation) and Task 05.0 (the events/
  exceptions track supplies the canonical `ClaudeCodeConfigError`).

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `ClaudeCodeSettings()` with no env vars set must construct without raising and produce `enabled=False` (backend not configured) — presence-signal-as-falsy default (C5).
- The mandatory-`scratch_cwd` validation must bite **only when `enabled=True`**, so the not-configured object stays constructible (C5).
- `permission_mode` **rejects** any bypass-permissions value at settings-validation time; no settings value may ever produce `--dangerously-skip-permissions` (C6 item 3).
- No secret, credential, or incident-payload text ever reaches a log sink or an exception message; validator warnings/errors name only field names and offending non-secret values (C13).
- No import of `ClaudeCodeSettings` appears in `aegis_swr/core/`, `aegis_swr/views/`, or `aegis_swr/code_intel/` (C3).

## Files created or modified by this task

```
src/aegis_swr/
└── claude_code/
    ├── __init__.py        ← NEW (subtask 01, empty)
    └── config.py          ← NEW (subtask 01 + 02): ClaudeCodeSettings, ClaudeCodeConfigError (forward-declared)

tests/unit/
└── claude_code/
    └── test_config.py     ← NEW: subtask 01 + 02 acceptance tests
```
