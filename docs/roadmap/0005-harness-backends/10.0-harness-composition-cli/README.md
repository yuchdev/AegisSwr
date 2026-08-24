# Task 10.0 — Harness Composition Root & CLI

**Parent milestone:** [Milestone 0005 — Code Intelligence Harness & Multi-Backend Support](/docs/roadmap/0005-harness-backends/plan.md)
**Status:** ⬜ Not started

## Scope

Wire every backend built by Tasks 01.0–09.0 into a single neutral composition
root and expose the resulting choice through the operator-facing CLI. This is the
**integration** task that turns three independent backend packages
(`openclaude/`, `claude_code/`, `openhands/`) plus the harness settings
(`harness/config.py`, Task 01.0) into one running selection surface.

Concretely, this task:

1. **Creates `harness/composition.py`** — the generalised C4 composition factory
   that reads `HarnessSettings.active_backend` (resolved per C2 in Task 01.0) and
   is the **one and only** place in the codebase that branches on which backend
   is active. The OpenClaude assembly logic **moves verbatim** out of the deleted
   `openclaude/composition.py`; the Claude Code and OpenHands branches are added
   alongside it. `harness/composition.py` becomes the only module permitted to
   import more than one backend family (C3).
2. **Deletes `openclaude/composition.py`** — its sole purpose (housing the C4
   branch) transfers to `harness/composition.py`; the rest of the `openclaude/`
   package is untouched. Its 0004 composition-root unit tests are re-targeted to
   `harness/composition.py` (Task 11.0).
3. **Performs the `Settings.openclaude` → `Settings.harness` breaking rename**
   (C12): the top-level `Settings` gains a single
   `harness: HarnessSettings = Field(default_factory=…)` field and the standalone
   `openclaude` field is removed. Every consumer of `settings.openclaude` migrates
   to `settings.harness.openclaude`.
4. **Adds `claude_code_agent` and `openhands_agent` roles to `agents.yaml`**
   (C11), each mirroring the existing `openclaude_agent` stanza and gated on that
   backend's own presence signal.
5. **Makes `aegis code-intel check` backend-agnostic** (C4): it reports **which**
   backend is active (or "unavailable") for every C2 selection outcome, and for
   `claude_code` additionally reports the resolved auth mode (C7).

This task builds no new backend behaviour — every `delegate()` path, every
sidecar/subprocess lifecycle, every settings class already exists after Tasks
01.0–09.0. Task 10.0 only composes and surfaces them.

**Naming decision (C4 "settle in task 10.0").** The factory keeps the 0004 name
`build_code_agent` rather than adopting `create_code_intel_backend`. Rationale is
recorded in subtask 01; in short, the factory returns a `CodeAgent` (not a
`CodeIntelBackend`), so the 0004 name describes the return type accurately and
keeps the migration surface to a module-path change only.

## Subtasks

| # | Name | Status | Blocks |
|---|------|--------|--------|
| 01 | [`harness/composition.py` factory + delete `openclaude/composition.py`](01-harness-composition-factory.md) | ⬜ Not started | 02, 04; Task 11.0 |
| 02 | [`Settings.harness` nesting (C12 breaking rename)](02-settings-harness-nesting.md) | ⬜ Not started | 01, 04; Task 11.0 |
| 03 | [`agents.yaml` `claude_code_agent` / `openhands_agent` roles](03-agents-yaml-roles.md) | ⬜ Not started | - |
| 04 | [`aegis code-intel check` backend-agnostic CLI](04-code-intel-check-cli.md) | ⬜ Not started | - |

**Intra-task ordering.** 02 (the settings rename) lands first or together with
01, because `harness/composition.py` consumes `HarnessSettings` and the CLI in 04
consumes `settings.harness`. 01 is the substance of the task; 04 depends on both
01 and 02. 03 (`agents.yaml`) is independent inert config and can land in any
order. All four must land together to keep the tree importable (the deletion in
01 breaks the CLI import until 04 is updated).

## Key constraints

- **The backend-selection branch lives in exactly one place** —
  `build_code_agent` in `harness/composition.py` (generalised C4). No other
  module branches on which backend is active. Verifiable by grep.
- **`harness/composition.py` is the only module that imports more than one
  backend family** (all three: `openclaude`, `claude_code`, `openhands`). No
  backend package imports a sibling (C3, grep-enforced, Task 11.0/13.0).
- **`aegis_swr/core/`, `aegis_swr/views/`, and `aegis_swr/code_intel/` import
  none** of `aegis_swr.openclaude`, `aegis_swr.claude_code`,
  `aegis_swr.openhands`, or `grpc` (C3).
- **`code_intel/backend.py`, `agent.py`, `budget.py` stay byte-for-byte
  unchanged**; `CodeResult.token_estimate` keeps its name and `int` type (C9).
- The OpenClaude assembly logic in the new factory is the **verbatim** move from
  the deleted `openclaude/composition.py` — not a rewrite (C4).
- `dry_run` is **orthogonal** to backend selection: the graph is fully
  constructed and the backend registered, but no sidecar is entered and no
  outbound call is made (C4, C13). For `openclaude`/`openhands` this means the
  sidecar `__aenter__` is skipped; for `claude_code` there is no sidecar to skip.
- The `Settings.openclaude` → `Settings.harness.openclaude` rename is a
  **deliberate breaking change** (C12): `settings.py`, the CLI subcommand, and
  every test reading `settings.openclaude` migrate; `settings.openclaude` no
  longer resolves afterward.
- `agents.yaml` roles are inert config parsed only by `RouterConfig`; they carry
  **no** credentials/secrets (C11 / security rules).
- `Optional[T]` from `typing`, never `T | None`; `from __future__ import
  annotations` in every new file; loguru + `SensitiveFilter` on every sink; no
  secret/credential/payload text in any log line, exception, or CLI output (C13).
- `ruff` (E,F,I,UP,B,SIM; line length 100) and `python scripts/replace_optional.py
  --check` stay clean.

## Files

```
src/aegis_swr/
├── harness/
│   └── composition.py            ← NEW: build_code_agent(...) — the sole C4 branch across all three families
├── openclaude/
│   └── composition.py            ← DELETED (logic moved verbatim to harness/composition.py)
├── config/
│   ├── settings.py               ← UPDATED: Settings.openclaude → Settings.harness (nested) (C12)
│   └── agents.yaml               ← UPDATED: + claude_code_agent, + openhands_agent roles (C11)
└── cli/
    └── commands.py               ← UPDATED: `aegis code-intel check` becomes backend-agnostic (C4)

tests/                            ← Task 11.0 re-targets openclaude/composition tests to harness/composition;
                                     adds selection-matrix + CLI-output assertions (out of scope here)
```
