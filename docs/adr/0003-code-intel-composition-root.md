# 0003 - Code intelligence composition root moved to `openclaude/composition.py`; `CodeIntelBackend` rename

> **Status:** Accepted
>
> **Date:** 2026-07-10
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

A post-implementation review of Milestone 0004 (OpenClaude Integration) found
two structural problems introduced during Task 06.0 (App Wiring):

1. **Orphan `app.py` composition root.** `src/aegis_swr/app.py` was created as
   a runnable module (`python -m aegis_swr.app [--dry-run]`) containing the sole
   `build_code_agent` factory — the single place where `settings.grpc_url is not
   None` (contract C4) decides whether to wire an `OpenClaudeTool` into
   `CodeAgent`. This duplicated the `cli/` composition root that already owns
   the `aegis` entry point, creating two disconnected wiring surfaces. The C4
   branch was unreachable from the real `aegis` binary, so `OPENCLAUDE_GRPC_URL`
   had no effect in practice.

2. **`CodeBackend` name collision.** `src/aegis_swr/backends/base.py` defines an
   unrelated `CodeBackend` ABC for the VCS / git-history backend (Milestone 0001,
   §6.5). Task 06.0 introduced a second `CodeBackend` in
   `src/aegis_swr/code_intel/backend.py` — a different contract (C4 delegation
   interface) with the same name in a different module. The collision posed a real
   import-confusion risk for contributors and static analysis tools. This gap was
   flagged in the Milestone 0004 decomposition review (see
   [status.md](/docs/roadmap/0004-code-intelligence/status.md)) but was not
   resolved before the initial implementation landed.

## Decision

1. **Rename `CodeBackend` (code-intel) to `CodeIntelBackend`** in
   `src/aegis_swr/code_intel/backend.py` and all of its consumers. The VCS
   backend's `CodeBackend` in `backends/base.py` is unchanged.

2. **Move `build_code_agent` to `src/aegis_swr/openclaude/composition.py`.**
   The `openclaude` package owns its own factory per the repository's
   Factory-Strategy convention; `code_intel/` is expressly prohibited from
   importing `openclaude` (contract C3 isolation), so the factory must live in
   the package that holds all its dependencies. A thin `composition.py` module
   in `openclaude/` is the natural home.

3. **Delete `src/aegis_swr/app.py`.** The module was a dead-end entry point
   that bypassed the real CLI. Its sole purpose — housing `build_code_agent` and
   its `--dry-run` smoke-test path — transfers to step 2 and step 4.

4. **Expose via `aegis code-intel check [--dry-run/--no-dry-run]`** — a
   dedicated CLI subcommand under the existing `aegis` binary. Dry-run is the
   default. This makes `OPENCLAUDE_GRPC_URL` reachable from the real entry point
   and gives operators a first-class verification command.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| Keep `app.py`; add a shim that imports it from `cli/` | Minimal diff | Perpetuates the orphan; two wiring surfaces remain; confusing for contributors | Doesn't fix the root cause |
| Move `build_code_agent` to `code_intel/composition.py` | Keeps openclaude concerns separate | `code_intel/` cannot import `openclaude` (C3 isolation violated) | Hard constraint — C3 is a CI-enforced boundary |
| Move `build_code_agent` to `cli/` directly | Single entry point | `cli/` would import `openclaude` directly, coupling the CLI layer to the gRPC backend | Violates layer separation; use a named factory module instead |

## Consequences

### Positive

- Single composition surface: `openclaude/composition.py` is the only place C4
  branching occurs; the CLI subcommand and any future callers converge there.
- `OPENCLAUDE_GRPC_URL` now takes effect when `aegis code-intel check
  --no-dry-run` is invoked — previously the C4 branch was unreachable from the
  real binary.
- C4 single-branch invariant is preserved: `settings.grpc_url is not None` is
  still the one and only conditional that registers `OpenClaudeTool`.
- `CodeIntelBackend` is unambiguous and grep-safe: no import-confusion with the
  VCS `CodeBackend` in `backends/base.py`.
- `docs/config/openclaude-setup.md` verification step is now `aegis code-intel check`,
  matching the real binary operators actually have on `PATH`.

### Negative

- Breaking change to the `app.py` module path: any script that invoked
  `python -m aegis_swr.app` must switch to `aegis code-intel check`. The
  previous command was documented only in the setup guide and README, not in any
  stable API.
- `test_app.py` unit tests that exercised `app.py` at 100% branch coverage need
  to be re-targeted to `openclaude/composition.py` and the new CLI subcommand.
  Coverage obligation is unchanged (≥90% module, 100% branch on
  `OpenClaudeTool.delegate`).

### Future scope

Analysis-agent consumption of `CodeAgent` (passing code-intelligence results
into the forensic debate) remains future scope per Milestone 0004's additive
charter. `CodeAgent.investigate` is the intended entry point; the composition
change does not alter its interface.

## Validation / Rollout

- CI `openclaude-isolation` job: grep confirms `aegis_swr.openclaude` is never
  imported by `core/`, `views/`, or `code_intel/`; `grpc`/`_pb2` outside
  `openclaude/grpc/client.py` is blocked.
- CI `openclaude-unit-coverage` job: ≥90% overall; 100% branch on
  `openclaude.tool`.
- `aegis code-intel check` (dry-run default) completes without a sidecar or
  `OPENCLAUDE_GRPC_URL` set.
- `aegis code-intel check` with `OPENCLAUDE_GRPC_URL` set does not open a gRPC
  connection in dry-run mode (C5 — no connection before the process context is
  entered).

## Links

- **Roadmap task:** [Milestone 0004 Task 06.0](/docs/roadmap/0004-code-intelligence/06.0-app-wiring/README.md)
- **Milestone status:** [Milestone 0004 status.md](/docs/roadmap/0004-code-intelligence/status.md)
- **Setup guide:** [docs/config/openclaude-setup.md](/docs/config/openclaude-setup.md)
- **Config reference:** [docs/config/openclaude-config-reference.md](/docs/config/openclaude-config-reference.md)
