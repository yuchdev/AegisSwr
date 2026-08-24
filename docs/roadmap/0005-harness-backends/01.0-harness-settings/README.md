# Task 01.0 — Harness Settings & Selection Contract

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

This task establishes the neutral selection layer that every other task in the
milestone builds on. It creates the `aegis_swr/harness/` package with two files:

- `harness/config.py` — `HarnessSettings`, a Pydantic `BaseSettings` subclass
  that composes the `AEGIS_CODE_INTEL_BACKEND` selector with one nested
  per-family settings sub-object (`openclaude`, `claude_code`, `openhands`),
  and resolves the single active backend at settings-construction time
  (contracts **C1**, **C2**, **C5**).
- `harness/exceptions.py` — `HarnessConfigError` (construction-time,
  config-shape ambiguity) and `HarnessUnavailableError` (composition-time, an
  explicitly selected backend not reachable), the two typed errors the C2 truth
  table distinguishes (**C2**, **C13**).

`HarnessSettings` is the one object that knows a backend selector exists and how
to turn "selector plus presence signals" into "exactly one active backend, or
none." It never reads `os.environ` in composition or tool code; each nested
sub-settings object sources its own family's variables exactly as
`OpenClaudeSettings` already does (C1). The selection resolution runs **once**,
at construction, and is exposed as a resolved `active_backend` property (C2).

> This task deliberately does **not** mount `HarnessSettings` into the top-level
> `Settings` object. The `Settings.harness` field and the C12 breaking rename of
> `Settings.openclaude → Settings.harness.openclaude` are delivered by
> [Task 10.0](/docs/roadmap/0005-harness-backends/plan.md) together with the
> composition root. This task's scope is `HarnessSettings` and
> `harness/exceptions.py` only — the shape and the selection contract, not the
> wiring.
>
> This task also does **not** create `harness/composition.py`
> (`create_code_intel_backend`, the sole C4 branch) — that is Task 10.0. It only
> fixes the settings shape and the two exception types Task 10.0 will raise.

## Forward references

`HarnessSettings` composes `ClaudeCodeSettings` and `OpenHandsSettings` 
**by name** via `default_factory`, but those classes are defined by parallel sibling
tasks that land concurrently — `ClaudeCodeSettings` by
[Task 02.0](/docs/roadmap/0005-harness-backends/plan.md) and `OpenHandsSettings`
by [Task 06.0](/docs/roadmap/0005-harness-backends/plan.md). This is a
**documentation-only forward reference**, handled exactly as Milestone 0004's
Task 01.0 forward-declared `OpenClaudeConfigError` ahead of Task 05.0's
canonical definition: it is *not* a blocking dependency of this task's
selection-contract work. The presence-signal shape each nested settings object
must expose (`grpc_url is not None`, `enabled is True`, `server_url is not None`)
is fixed here by C2, so 02.0 and 06.0 can honor it as they land; until they do,
the composition line is a named-but-unresolved import and the harness selection
logic is exercised against a stub or against `OpenClaudeSettings` alone. Each
sub-settings class MUST mirror `OpenClaudeSettings`' proven shape (C5).

## Subtasks

| #  | Document                                                       | Status         | Blocks                                        |
|----|----------------------------------------------------------------|----------------|-----------------------------------------------|
| 01 | [`HarnessSettings` class shape](01-harness-settings.md)        | ⬜ Not started | 02 (this task); 02.0, 06.0, 10.0 (downstream) |
| 02 | [Selection & ambiguity resolution](02-selection-resolution.md) | ⬜ Not started | 10.0 (downstream)                             |
| 03 | [`harness/exceptions.py`](03-harness-exceptions.md)            | ⬜ Not started | 01, 02 (this task); 10.0 (downstream)         |

Subtask 03 (the exception leaf module) has no dependencies and should land
first or atomically with the others — subtasks 01 and 02 both import from it.
Subtask 01 defines the class and its nested composition; subtask 02 extends
that same class with the C2 resolution logic (the `model_validator` and the
`active_backend` / `presence_signals` properties). Subtasks 01 and 03 have no
interdependency and may proceed in parallel; subtask 02 depends on both.

## Key constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:` / `:ivar:` / `:return:`).
- **C2 is loud, never silent.** Selector unset with more than one presence signal raises `HarnessConfigError` at settings-construction time — the harness never silently picks one backend over another.
- **Preserve 0004's closing guarantee.** Selector unset with exactly one presence signal auto-selects that backend; an `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes and never raises.
- **No secrets or payload text in exceptions.** `HarnessConfigError` and `HarnessUnavailableError` carry only the offending field/backend names and the set of *signal names* seen — never a URL value, token, credential, or any incident payload (C13). Neither exception subclasses the other.
- `HarnessSettings` never reads `os.environ` for a family's variables; each nested settings object sources its own (C1). No import of `HarnessSettings` appears in `aegis_swr/core/`, `aegis_swr/views/`, or `aegis_swr/code_intel/` (C3) — it is referenced only by the composition root (Task 10.0) and the CLI.

## Files created or modified by this task

```
src/aegis_swr/
└── harness/
    ├── __init__.py       ← NEW (subtask 01, empty/versioned)
    ├── config.py         ← NEW (subtask 01: shape + nested composition; subtask 02: C2 resolution added to the class)
    └── exceptions.py     ← NEW (subtask 03: HarnessConfigError, HarnessUnavailableError)

tests/unit/harness/
└── test_config.py        ← NEW: subtask 01/02/03 acceptance tests (the full C2 selection matrix)
```

> `harness/composition.py` is intentionally **absent** from this tree — it is
> created by Task 10.0.
