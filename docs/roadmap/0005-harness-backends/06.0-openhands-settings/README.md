# Task 06.0 — OpenHands Settings & Config

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

This task establishes the entire configuration surface for the OpenHands
backend. It creates the `aegis_swr/openhands/` package and
`aegis_swr/openhands/config.py` containing `OpenHandsSettings`, a Pydantic
`BaseSettings` subclass whose fields are sourced entirely from environment
variables per milestone contracts **C5** (backend settings-shape convention)
and **C8** (OpenHands backend contract). It mirrors the proven shape of
`OpenClaudeSettings` (Milestone 0004 C1) and `ClaudeCodeSettings` (Task 02.0):
a per-family `env_prefix`, CSV env parsing for `list[str]` fields, typed
config-error `field_validator`s unwrapped from Pydantic's `ValidationError` in
`__init__`, and **presence-signal-as-`None`-default** so an absent variable
means "backend not configured" rather than a construction crash.

`OpenHandsSettings` is the single object injected into `OpenHandsProcess`,
`OpenHandsClient`, and `OpenHandsTool` (Tasks 07.0, 08.0); no other module
reads `OPENHANDS_*` env vars from `os.environ`. Validation rejects unknown
`allowed_tools` entries, malformed `server_url` values, and — decisively for
this backend's security posture — a **non-Docker-sandboxed `runtime_mode`
unless an explicit override flag is also set** (subtask 02), by raising
`OpenHandsConfigError` (forward-declared in subtask 01, formally defined in
Task 09.0).

> **Docker sandbox is a design requirement, not an option (C8 item 2).**
> Aegis SWR treats every incident payload as hostile (`../CLAUDE.md` §1), and
> OpenHands was chosen precisely because it executes its navigation tools inside
> a Docker sandbox. `OpenHandsSettings` therefore **selects the sandboxed Docker
> runtime by default**; selecting a non-sandboxed runtime requires an explicit
> override plus an ADR — the same discipline OpenClaude applies to relaxing its
> tool allowlist. See subtask 02 and [plan.md](/docs/roadmap/0005-harness-backends/plan.md) C8.

> This task is **configuration only.** It does **not** import or touch the
> OpenHands HTTP/WS client library (that isolation boundary belongs to
> `openhands/client.py`, Task 07.0, C3), define the sidecar lifecycle
> (`openhands/process.py`, Task 07.0), or implement the `CodeIntelBackend`
> (`openhands/tool.py`, Task 08.0). It defines no event dataclasses (Task 09.0,
> C10).

## Assumptions

OpenHands is consumed as an **opaque, versioned black-box sidecar** reached over
REST/WS — Aegis SWR depends only on its published API contract, never on its
internals or source layout (mirrors how Milestone 0004 treats OpenClaude).
Consequences relevant to configuration:

- **Operator prerequisite: Docker is available on the host.** Because Aegis SWR
  is Windows-only (`../CLAUDE.md`), Docker-on-Windows is a new operator
  prerequisite. This task's settings assume, but do not verify, Docker
  availability — the runtime-availability check is a composition/health-check
  concern (Task 07.0). Documenting the prerequisite in the root `README.md` is
  Task 13.0's job.
- `server_url` (`OPENHANDS_SERVER_URL`) defaults to `None` — the **presence
  signal** the harness reads to auto-select this backend (C2). An unset or
  empty-string value means "OpenHands not configured", never a construction
  crash (see the empty-env coercion rule in the Constraints below).
- `runtime_mode` (`OPENHANDS_RUNTIME`) defaults to the **sandboxed Docker
  runtime**; the operator never opts *in* to the sandbox — they can only, with
  deliberate friction, opt *out* (subtask 02).

## Subtasks

| #  | Document                                                                 | Status         | Blocks                           |
|----|--------------------------------------------------------------------------|----------------|----------------------------------|
| 01 | [`OpenHandsSettings` Pydantic class](01-openhands-settings.md)           | ⬜ Not started | 02 (this task), 07.0, 08.0, 09.0 |
| 02 | [Sandbox-runtime enforcement validator](02-sandbox-runtime-validator.md) | ⬜ Not started | 07.0                             |

Subtask 01 establishes the class, its six documented fields, and the forward
declaration of `OpenHandsConfigError`. Subtask 02 depends on subtask 01: it adds
the `allow_unsandboxed_runtime` override field and the cross-field
model-validator that enforces the Docker-sandbox default. The two are separated
so the plain settings shape (01) can be reviewed independently of the security
enforcement (02).

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- `OpenHandsConfigError` forward-declared in subtask 01 must be import-compatible with the canonical definition Task 09.0 places in `openhands/exceptions.py` — downstream code must not require an import-path change when 09.0 lands (the same forward-declaration discipline Milestone 0004 Task 01.0 used for `OpenClaudeConfigError`).
- No import of `OpenHandsSettings` appears in `aegis_swr/core/`, `aegis_swr/views/`, or `aegis_swr/code_intel/` (C3). `OpenHandsSettings` is composed into `HarnessSettings` via `default_factory` (C5, wired in Task 01.0 / 10.0), never read directly by the scaffolding.
- No secret or incident-payload text (dump/log/stack, `server_url` credentials, any auth material carried in the URL) ever reaches a log sink or an exception message; validators name only the offending field, never its value (C13).

## Files created or modified by this task

```
src/aegis_swr/
└── openhands/
    ├── __init__.py                 ← NEW (subtask 01, empty)
    └── config.py                   ← NEW (subtask 01: OpenHandsSettings + fields; subtask 02: allow_unsandboxed_runtime + enforcement validator)

tests/unit/openhands/
└── test_config.py                  ← NEW: subtask 01 (field/default/CSV/URL) and subtask 02 (sandbox-enforcement) acceptance tests
```

> The `openhands/config.py` `OpenHandsConfigError` forward declaration is
> replaced by a re-export alias when Task 09.0 lands `openhands/exceptions.py`;
> the import path `aegis_swr.openhands.config.OpenHandsConfigError` keeps
> resolving to the same object with **no downstream change** — exactly as
> `aegis_swr/openclaude/config.py` does today (see its module docstring).
