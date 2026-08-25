# Code Intelligence Backend Selection Guide

Operator-facing guide to how Aegis SWR chooses **which** Code Intelligence
backend is active — OpenClaude, Claude Code, or OpenHands — and what happens
when that choice is ambiguous or unavailable.

## 1. Overview

Exactly **one** Code Intelligence backend is active at a time — there is no
fallback chain (user-confirmed; this generalizes Milestone 0004's contract C4,
"no sibling backends to fall back to," to "exactly one active backend at a
time; the others are simply not registered"). Which backend is active is
driven by one selector environment variable plus each backend family's own
**presence signal**, and the choice is resolved once, at settings-construction
time (contracts C1/C2 of the
[Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md)).

Per-backend setup guides:
[OpenClaude](/docs/config/openclaude-setup.md) ·
[Claude Code](/docs/config/claude-code-setup.md) ·
[OpenHands](/docs/config/openhands-setup.md).

## 2. The selector and the presence signals

| Variable                   | Role                                                                  |
|-----------------------------|------------------------------------------------------------------------|
| `AEGIS_CODE_INTEL_BACKEND` | The selector: `openclaude` \| `claude_code` \| `openhands` \| unset. Unset means auto-select from presence signals (section 3). |

A **presence signal** is a backend family's own configured-and-non-empty
enabling variable:

| Backend       | Presence signal            | Notes                                              |
|---------------|------------------------------|-----------------------------------------------------|
| OpenClaude    | `OPENCLAUDE_GRPC_URL` set   | Unchanged from Milestone 0004.                     |
| Claude Code   | `CLAUDE_CODE_ENABLED=true`  | Explicit opt-in; being on `PATH` is **not** a signal. |
| OpenHands     | `OPENHANDS_SERVER_URL` set  | Mirrors OpenClaude's URL-presence pattern.         |

## 3. The selection truth table

Reproduced verbatim from contract C2 of the
[Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md):

| `AEGIS_CODE_INTEL_BACKEND` | Presence signals set | Outcome |
|----------------------------|----------------------|---------|
| unset | zero | No backend registered; capability unavailable (unchanged from 0004 C4). |
| unset | exactly one | That backend is auto-selected. **Preserves 0004's guarantee** — an `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes. |
| unset | more than one | **`HarnessConfigError` at settings-construction time.** Fail loud, never silently pick one. |
| set to family *X* | *X*'s signal present | *X* is selected. |
| set to family *X* | *X*'s signal absent | **`HarnessUnavailableError`** raised at composition / health-check time (not at settings construction — the operator explicitly asked for *X*, so this is a runtime capability failure, not a config-shape error). |

## 4. The two failure modes explained

- **`HarnessConfigError`** — construction-time, a **config-shape** ambiguity
  (more than one presence signal, no selector set). Fix: set
  `AEGIS_CODE_INTEL_BACKEND` explicitly to the backend you want, or unset the
  extra signals so only one remains.
- **`HarnessUnavailableError`** — composition- / health-check-time, an
  **explicitly-selected** backend that isn't actually reachable or enabled.
  Fix: set that backend's presence signal, start its sidecar, or install its
  binary.

Both exceptions carry only the offending field/backend names and the set of
signals seen — **never** a secret or incident-payload value (contracts C2 and
C13).

## 5. Verifying the active backend

`aegis code-intel check` is backend-agnostic (contract C4): it reports which
backend is active — or "unavailable" — for every selection outcome above,
including Claude Code's resolved auth mode when that backend is selected.
Expected outputs (dry-run, the default) for every C2 selection outcome, and their
exit codes:

| Scenario | Output (approximate) | Exit code |
|---|---|---|
| No signals set | `Code intelligence unavailable (no backend active; no presence signal set).` | 0 |
| `OPENCLAUDE_GRPC_URL` set, selector unset | `Code intelligence backend active: openclaude (dry-run: sidecar not started).` | 0 |
| `CLAUDE_CODE_ENABLED=true`, selector unset | `Code intelligence backend active: claude_code (auth mode: auto) (dry-run: sidecar not started).` | 0 |
| `OPENHANDS_SERVER_URL` set, selector unset | `Code intelligence backend active: openhands (dry-run: sidecar not started).` | 0 |
| Two signals set, selector unset (`HarnessConfigError`) | `Code-intelligence configuration error: HarnessSettings.backend: multiple backend presence signals set ([...]); set AEGIS_CODE_INTEL_BACKEND to choose one` | 2 |
| `AEGIS_CODE_INTEL_BACKEND=openhands`, signal absent (`HarnessUnavailableError`) | `Code intelligence unavailable: selected backend 'openhands' is not reachable/enabled (Selected code-intelligence backend 'openhands' is not available: its presence signal is not set ...).` | 1 |

For Claude Code, the parenthetical `(auth mode: <mode>)` always reports the resolved
mode name — never a credential value (C7/C13).

Pass `--no-dry-run` to also exercise the live sidecar path (health-check or auth-probe).

## 6. Preserving the 0004 guarantee

An existing deployment that only sets `OPENCLAUDE_GRPC_URL` (selector unset,
exactly one presence signal) auto-selects OpenClaude under the harness exactly
as it did before Milestone 0005 — **zero further changes** are required.

## 7. Cross-links

- [OpenClaude setup guide](/docs/config/openclaude-setup.md) and
  [OpenClaude configuration reference](/docs/config/openclaude-config-reference.md).
- [Claude Code setup guide](/docs/config/claude-code-setup.md) and
  [Claude Code configuration reference](/docs/config/claude-code-config-reference.md).
- [OpenHands setup guide](/docs/config/openhands-setup.md) and
  [OpenHands configuration reference](/docs/config/openhands-config-reference.md).
- [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md) — the
  authoritative contract (C1–C13) this guide summarizes for operators.
