# Code Intelligence Backend Selection Guide

Operator-facing guide to how Aegis SWR chooses **which** Code Intelligence
backend is active — OpenClaude, Claude Code, or OpenHands — and what happens
when that choice is ambiguous or unavailable.

> **Status.** The multi-backend harness described here is specified by
> [Milestone 0005](/docs/roadmap/0005-harness-backends/plan.md) but not yet
> implemented (`aegis_swr/harness/`, `aegis_swr/claude_code/`, and
> `aegis_swr/openhands/` do not exist in `src/` yet — see
> [status.md](/docs/roadmap/0005-harness-backends/status.md)). Today, only the
> [OpenClaude backend](/docs/config/openclaude-setup.md) from Milestone 0004
> exists, selected the way section 6 below describes. This guide documents the
> target behavior so it is ready to publish unchanged once Task 10.0 lands.

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
`docs/config/claude-code-setup.md` (not yet written) ·
`docs/config/openhands-setup.md` (not yet written).

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
Expected one-line outputs, once Task 10.0 lands:

```text
$ aegis code-intel check                     # no signals set
code-intel: unavailable (no backend configured)

$ aegis code-intel check                     # OPENCLAUDE_GRPC_URL set, selector unset
code-intel: openclaude (auto-selected)

$ aegis code-intel check                     # CLAUDE_CODE_ENABLED=true, selector unset
code-intel: claude_code (auto-selected, auth_mode=auto)

$ aegis code-intel check                     # OPENHANDS_SERVER_URL set, selector unset
code-intel: openhands (auto-selected)

$ aegis code-intel check                     # two signals set, selector unset
error: HarnessConfigError — ambiguous backend selection (signals seen: openclaude, claude_code)

$ aegis code-intel check                     # AEGIS_CODE_INTEL_BACKEND=openhands, signal absent
error: HarnessUnavailableError — backend 'openhands' selected but OPENHANDS_SERVER_URL is not set
```

## 6. Preserving the 0004 guarantee

An existing deployment that only sets `OPENCLAUDE_GRPC_URL` (selector unset,
exactly one presence signal) auto-selects OpenClaude under the harness exactly
as it did before Milestone 0005 — **zero further changes** are required. This
is also today's actual behavior: with no harness yet implemented, OpenClaude
is Aegis SWR's only Code Intelligence backend, selected the same way.

## 7. Cross-links

- [OpenClaude setup guide](/docs/config/openclaude-setup.md) and
  [OpenClaude configuration reference](/docs/config/openclaude-config-reference.md)
  — the one backend that exists today.
- `docs/config/claude-code-setup.md` / `docs/config/claude-code-config-reference.md`
  and `docs/config/openhands-setup.md` / `docs/config/openhands-config-reference.md`
  — the two additional backends specified by Milestone 0005 (not yet written).
- [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md) — the
  authoritative contract (C1–C13) this guide summarizes for operators.
