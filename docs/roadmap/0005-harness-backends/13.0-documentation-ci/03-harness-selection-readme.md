# 03 - harness-selection.md + root README.md update

**Parent task:** 13.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 01.0 (`HarnessSettings` selector + C1/C2 resolution), 10.0 (backend-agnostic `aegis code-intel check`, `Settings.harness` nesting, C4/C12); documents the operator-facing surface those tasks deliver.
**Blocks:** none

## Objective

Author `docs/harness-selection.md` — the single operator-facing rendering of the
**C2 selection/ambiguity contract**: how the harness decides which of the three
backends (OpenClaude, Claude Code, OpenHands) is active, and exactly what happens
in each ambiguous or unavailable case. Also update the repo-root `README.md`
system-requirements area with the **Docker-on-Windows** prerequisite (for the
OpenHands backend) and a **backend-selection pointer** into this new doc.

This doc has no direct OpenClaude counterpart (single-backend Milestone 0004 had
nothing to select), but it follows the same operator-doc density and cross-link
discipline as the OpenClaude setup/reference pair.

## File: `docs/harness-selection.md`

Outline (section headings + what each covers):

### 1. Overview
- One paragraph: exactly **one** Code Intelligence backend is active at a time —
  **no fallback chain** (user-confirmed, generalising 0004's C4). Selection is
  driven by `AEGIS_CODE_INTEL_BACKEND` plus each family's **presence signal**, and
  resolved at **settings-construction time** (C1/C2). Link to the three per-backend
  setup guides and to the [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).

### 2. The selector and the presence signals
- `AEGIS_CODE_INTEL_BACKEND` — `openclaude` | `claude_code` | `openhands` | unset
  (unset = auto-select from presence signals).
- Presence-signal table (a "presence signal" = a family's configured-and-non-empty
  enabling variable):

| Backend | Presence signal | Notes |
|---------|-----------------|-------|
| OpenClaude | `OPENCLAUDE_GRPC_URL` set | unchanged from 0004 |
| Claude Code | `CLAUDE_CODE_ENABLED=true` | explicit opt-in; PATH presence is **not** a signal |
| OpenHands | `OPENHANDS_SERVER_URL` set | mirrors OpenClaude's URL-presence pattern |

### 3. The selection truth table (verbatim from C2)
Reproduce the C2 truth table exactly, as an operator-facing table:

| `AEGIS_CODE_INTEL_BACKEND` | Presence signals set | Outcome |
|----------------------------|----------------------|---------|
| unset | zero | No backend registered; capability unavailable (unchanged from 0004 C4). |
| unset | exactly one | That backend is auto-selected. Preserves 0004's guarantee — an `OPENCLAUDE_GRPC_URL`-only deployment needs zero further changes. |
| unset | more than one | **`HarnessConfigError` at settings-construction time** — fail loud, never silently pick one. |
| set to *X* | *X*'s signal present | *X* is selected. |
| set to *X* | *X*'s signal absent | **`HarnessUnavailableError` at composition/health-check time** (a runtime capability failure, not a config-shape error). |

### 4. The two failure modes explained
- `HarnessConfigError` — construction-time, **config-shape** ambiguity (more than
  one signal, no selector). How to fix: set `AEGIS_CODE_INTEL_BACKEND` explicitly,
  or unset the extra signals.
- `HarnessUnavailableError` — composition/health-check-time, an
  **explicitly-selected** backend is not reachable/enabled. How to fix: set that
  backend's presence signal / start its sidecar / install its binary.
- Note both carry only the offending field/backend names and the signals seen —
  **never** any secret or payload text (C2/C13).

### 5. Verifying the active backend
- `aegis code-intel check` (backend-agnostic, C4) reports **which** backend is
  active — or "unavailable" — for every selection outcome, including Claude Code's
  resolved `auth_mode`. Show the expected one-line outputs for: unavailable,
  each of the three backends selected, and each of the two error cases.

### 6. Preserving the 0004 guarantee
- Restate plainly: an existing `OPENCLAUDE_GRPC_URL`-only deployment (selector
  unset, exactly one signal) auto-selects OpenClaude and needs **zero** changes.

### 7. Cross-links
- The three setup guides (code spans for the two authored in subtasks 01/02;
  live link for [`docs/openclaude-setup.md`](/docs/openclaude-setup.md)), the three
  config references, and the [Milestone 0005 plan](/docs/roadmap/0005-harness-backends/plan.md).

## Root `README.md` update

Targeted edits only — do not rewrite the file:

### A. System-requirements area
- Add a **Docker-on-Windows** line: for the **OpenHands** backend only, Docker
  (Docker Desktop / a Docker engine) must be available on the Windows host, since
  the OpenHands runtime is Docker-sandboxed by default (C8). Make clear it is
  **not** required for OpenClaude or Claude Code.
- Keep the existing Windows-only / Python 3.12 / `cdb.exe` requirements intact.

### B. Backend-selection pointer
- Add a short "Code Intelligence backends" note naming the three selectable
  backends and pointing at [`docs/harness-selection.md`](/docs/harness-selection.md)
  (selection contract) and the three per-backend setup guides.

## Implementation notes
- Plain Markdown tables and code fences; no RST `:param:` notation.
- The truth table must match C2 exactly — transcribe, do not paraphrase the
  outcomes.
- All env var names must match `.env.example` and the C1/C2 tables.
- README edits are additive and surgical; preserve the existing structure.
- Add `docs/harness-selection.md` to the `docs/README.md` index (coordinate with
  `docs-updater`).

## Constraints
- C2 in [plan.md](/docs/roadmap/0005-harness-backends/plan.md) is authoritative; the truth table and both error semantics must
  match it exactly.
- Renders with zero broken internal links (`python scripts/check_doc_links.py docs/`).
- Absolute-from-repo-root links with a leading `/`; no relative chains.
- The README must state Docker-on-Windows is OpenHands-only, not a global new
  requirement.
- No design here may cause a secret or payload to appear in an error message.

## Success criteria
- [ ] `docs/harness-selection.md` created with sections 1–7 above.
- [ ] The C2 selection truth table is reproduced exactly (all five rows).
- [ ] Both failure modes (`HarnessConfigError` vs `HarnessUnavailableError`)
      explained with their timing and fix, and the no-secret-in-message note.
- [ ] `aegis code-intel check` outputs shown for every selection outcome.
- [ ] Root `README.md` gains the Docker-on-Windows line (OpenHands-only) in the
      system-requirements area.
- [ ] Root `README.md` gains a backend-selection pointer to
      `docs/harness-selection.md` and the per-backend setup guides.
- [ ] `docs/harness-selection.md` linked from `docs/README.md`.
- [ ] `python scripts/check_doc_links.py docs/` passes.
