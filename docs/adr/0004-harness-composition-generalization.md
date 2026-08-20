# 0004 - Code-intelligence composition root generalised into a neutral `harness/` package

> **Status:** Proposed
>
> **Date:** 2026-08-19
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

Milestone 0004 (OpenClaude Integration) stood up the Code Intelligence subsystem
with exactly one backend. [ADR 0003](/docs/adr/0003-code-intel-composition-root.md)
resolved a post-implementation review by moving the single composition factory
(`build_code_agent`) into `src/aegis_swr/openclaude/composition.py` — the package
that owns all of that factory's dependencies — because the backend-agnostic
scaffolding in `src/aegis_swr/code_intel/` is expressly forbidden from importing
`openclaude` (contract C3). ADR 0003's contract C4 codified the single-branch
invariant: `settings.grpc_url is not None` is the one and only conditional that
registers a backend, and it lives in exactly one place.

That placement was correct **for one backend**. Milestone 0005 introduces two
more first-class backends behind the unchanged `CodeIntelBackend` ABC:

- **`claude_code`** — the installed `claude` CLI (the "stock Claude Code" that
  0004 was chosen *over*, now promoted to a backend of its own), run as a
  one-shot subprocess per delegation.
- **`openhands`** — a Docker-sandboxed OpenHands sidecar over REST/WS.

With more than one backend, the ADR 0003 placement breaks down. If
`openclaude/composition.py` retained the composition factory, it would have to
import `claude_code` and `openhands` to branch across them — i.e. **one backend
package would depend on its sibling backend packages.** That inverts the
repository's Factory-Strategy convention (each family owns only its own
`create_*` factory and never reaches sideways) and violates the spirit of the C3
isolation boundary that ADR 0003 relied on. The composition branch must move out
of any single backend package into a neutral layer.

A second force is the **selection contract**. 0004's C4 assumed a single
backend, so "which backend?" was a single boolean. Milestone 0005 confirmed
(with the user) a **single-active-backend, no-fallback** model with a richer
resolution: an explicit `AEGIS_CODE_INTEL_BACKEND` selector, per-family presence
signals, auto-selection when exactly one signal is present, and — a new failure
mode that could not exist with one backend — a **loud error when the selection
is ambiguous** (selector unset and more than one signal set). That resolution
logic needs a home too, and the natural home is the same neutral layer.

## Decision

1. **Introduce a neutral `aegis_swr/harness/` package** whose sole
   responsibility is backend *selection* and *composition*. It contains
   `config.py` (`HarnessSettings`: the `AEGIS_CODE_INTEL_BACKEND` selector plus
   the nested per-family settings, and the selection/ambiguity resolution),
   `composition.py` (the generalised composition factory), and `exceptions.py`
   (`HarnessConfigError`, `HarnessUnavailableError`).

2. **Move the C4 composition branch out of `openclaude/composition.py` into
   `harness/composition.py`**, generalising it from a single
   `grpc_url is not None` boolean to a branch over the resolved active backend.
   The OpenClaude assembly logic moves **verbatim**; it is not rewritten. The
   Claude Code and OpenHands assembly branches are added alongside it.
   `harness/composition.py` becomes the **only** module in the codebase permitted
   to import more than one backend family.

3. **Delete `src/aegis_swr/openclaude/composition.py`.** Its sole purpose —
   housing the C4 branch — transfers to step 2. The `openclaude/` package is
   otherwise unchanged.

4. **Keep `code_intel/` byte-for-byte unchanged.** The `CodeIntelBackend` ABC,
   `CodeAgent`, `CallBudget`, and the `CodeResult` shape (including
   `token_estimate`'s field name and `int` type) stay backend-agnostic. Claude
   Code's *real* token counts and OpenClaude's *estimated* ones both flow through
   the same `token_estimate` field, so the contract does not change even though
   its provenance improves.

5. **Nest backend settings under `Settings.harness`.** The top-level
   `Settings.openclaude` field becomes `Settings.harness.openclaude` (with
   `Settings.harness.claude_code` and `Settings.harness.openhands` alongside).
   This is a deliberate breaking rename, accepted under the same tolerance the
   codebase applied to ADR 0003's `CodeBackend` → `CodeIntelBackend` rename.

6. **Make `aegis code-intel check` backend-agnostic.** The CLI subcommand
   introduced by ADR 0003 stops referencing OpenClaude specifically; it reports
   **which** backend is active (or that the capability is unavailable) for every
   selection outcome, calling the harness composition factory.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| Keep the factory in `openclaude/composition.py`; import the siblings from there | Smallest diff; no new package | `openclaude/` would import `claude_code`/`openhands`, coupling backend packages to each other and breaking Factory-Strategy + the C3 spirit | Structurally wrong — a backend package must not depend on its siblings |
| Put the branch in `code_intel/composition.py` | Keeps composition near the scaffolding it feeds | `code_intel/` is forbidden from importing any concrete backend (C3, CI-enforced) — the same hard constraint ADR 0003 already faced | Hard constraint — C3 is a CI-enforced boundary |
| Put the branch directly in `cli/commands.py` | No new module | The CLI layer would import all three gRPC/subprocess/HTTP backends directly, coupling the presentation layer to every backend implementation | Violates layer separation; ADR 0003 already rejected the analogous "move to `cli/`" for one backend |
| A plugin/entry-point registry (backends self-register via `importlib.metadata`) | Fully open/extensible; no central branch | Over-engineered for three in-tree backends; defeats the single-visible-branch auditability that C4 exists to guarantee; harder to reason about for a security review | Premature generality; the fleet needs an auditable single branch, not dynamic discovery |
| Add a fallback chain across backends instead of single-active | Resilience if one backend is down | Multiplies cost and non-determinism across agentic harnesses; the user explicitly did not want it; a failed forensic navigation should surface, not silently retry on a different model | Out of scope by explicit user decision (single-active, no fallback) |

## Consequences

### Positive

- **The C4 single-branch invariant is preserved and strengthened.** There is
  still exactly one place that decides which backend is active; it is now in a
  neutral package rather than inside one of the competing backends.
- **Factory-Strategy and C3 isolation both hold cleanly.** Each backend package
  imports only its own dependencies; only `harness/` imports across families;
  `code_intel/` imports no concrete backend. The 0004 grep isolation job extends
  naturally to a per-package check.
- **Adding a backend is localised.** A fourth backend is a new package plus one
  new branch in `harness/composition.py` and one new nested settings field —
  no change to `code_intel/` or the existing backends.
- **The 0004 closing guarantee survives.** An `OPENCLAUDE_GRPC_URL`-only
  deployment (selector unset, one signal) auto-selects OpenClaude with zero
  further changes.
- **Ambiguity fails loud.** Selector unset with more than one presence signal
  raises `HarnessConfigError` at settings-construction time — a real safety
  improvement over silently picking a backend, and a failure mode that could not
  even occur under 0004.

### Negative

- **Breaking rename `Settings.openclaude` → `Settings.harness.openclaude`.** Any
  code or test reading `settings.openclaude` must migrate. The field is internal
  with no stable external API; the migration is enumerated in Milestone 0005
  task 09.0.
- **`openclaude/composition.py` deletion re-targets tests.** The 0004
  composition-root unit tests move to `harness/composition.py`; the coverage
  obligation (≥90% module, 100% branch on each tool's `delegate`) is unchanged.
- **A new package to review.** `harness/` is small but is now the single most
  security-relevant selection surface; it warrants a `security-auditor` pass
  because it is the one place that decides whether a host-permission backend
  (Claude Code) or a sandboxed one (OpenHands) is activated.
- **Two host-permission backends now exist.** Claude Code, like OpenClaude, runs
  with host OS permissions (only OpenHands is sandboxed). The residual-risk
  posture is unchanged from 0004 for those two, but the explicit-opt-in presence
  signal (`CLAUDE_CODE_ENABLED`, never PATH-presence) is the mitigation that
  keeps activation deliberate.

### Future scope

Analysis-agent consumption of `CodeAgent` results (feeding code-intelligence
into the forensic debate) remains future scope, exactly as ADR 0003 left it.
`CodeAgent.investigate` is unchanged and remains the intended entry point. A
plugin/entry-point registry could still be adopted later if out-of-tree backends
ever become a requirement; this ADR deliberately defers that generality.

## Validation / Rollout

- Extended CI isolation job(s): grep confirms `harness/composition.py` is the
  only importer of more than one backend family; no backend package imports a
  sibling; `core/`, `views/`, and `code_intel/` import no concrete backend or
  `grpc`.
- Per-backend unit-coverage gates mirroring 0004's OpenClaude gates (≥90%
  module, 100% branch on each new tool's `delegate`).
- Selection matrix tests (Milestone 0005 C2): unset+zero → unavailable;
  unset+one → auto-selected; unset+many → `HarnessConfigError`; explicit+absent
  → `HarnessUnavailableError`.
- `aegis code-intel check` reports the active backend (or unavailable) for every
  selection outcome and opens no connection/spawns no process under `--dry-run`.
- Regression guarantee: an `OPENCLAUDE_GRPC_URL`-only environment behaves exactly
  as it did after Milestone 0004 (OpenClaude auto-selected, zero changes).

## Links

- **Roadmap milestone:** [Milestone 0005 plan.md](/docs/roadmap/0005-harness-backends/plan.md)
- **Milestone status:** [Milestone 0005 status.md](/docs/roadmap/0005-harness-backends/status.md)
- **Extends:** [ADR 0003 - Code intelligence composition root](/docs/adr/0003-code-intel-composition-root.md)
- **Prior milestone:** [Milestone 0004 status.md](/docs/roadmap/0004-code-intelligence/status.md)
