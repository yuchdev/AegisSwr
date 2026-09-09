# 0005 - Adopt the standalone `flake8-lint` package as the single lint engine, run via CLI and/or pytest adapters

> **Status:** Proposed
>
> **Date:** 2026-09-08
>
> **Supersedes:** _(none)_
>
> **Superseded by:** _(none)_

## Context

Aegis SWR ships a hand-built, in-place static-analysis prototype that enforces
the project's coding-standard rules (`docs/dev/python_coding_standard.md`). It
has two halves and one blind spot:

1. **The rule engine — `src/flake8_project_rules/`.** `rules.py` implements 12
   AST checks (`X001`-`X012`, with `X003` reserved and disabled). `plugin.py`
   wraps them in a Flake8-plugin *shape*, but `flake8` is **not** a declared
   dependency and no entry point is registered anywhere in `pyproject.toml`. In
   practice the "plugin" is never invoked by a real `flake8` run — the only
   caller is test code.

2. **A bespoke test harness — `tests/flake8_lint/`.** `config.py` hand-rolls a
   TOML loader for a private `[tool.flake8_lint_tests]` pyproject section
   (`include`/`exclude`/`select`/`ignore`/`allow_noqa`/`noqa_allowed`/
   `noqa_forbidden`) plus its own file-discovery / `covered_dirs` logic.
   `test_project_lint.py` walks the tree and asserts the project is clean;
   `test_plugin_direct.py` runs per-rule detection against
   `tests/flake8_lint/samples/*.py`. These two tests are the *only* way the lint
   logic ever executes.

3. **The blind spot:** there is **no standalone lint CLI**. A lint failure can
   only surface as a pytest failure, so it is entangled with — and can be masked
   by — unrelated test breakage, and it cannot be run as an independent CI gate.
   There is also no clean way to add a project-specific rule, and no extension
   contract for one.

Independently, a sibling project at `~/Projects/Flake8Lint` (its own repo, **not**
part of AegisSwr) has already generalised this exact idea into a reusable package
`flake8_lint`. It is the "finished" version of the prototype:

- `rules.py` + `registry.py` — the same `X001`-`X012` checks (`X003` reserved),
  but registered through a `RuleRegistry` that also accepts **arbitrary** custom
  codes matching `^[A-Z][A-Z0-9]*\d{3}$` (uppercase alpha-numeric prefix +
  exactly three digits). Invalid and duplicate codes fail fast
  (`InvalidRuleCodeError`, `DuplicateRuleCodeError`).
- Three provider-loading paths in `resolve_registry(...)`: (1) built-ins,
  (2) project-local modules named in config as `rule_modules = ["pkg.lint_rules"]`,
  each exposing `register_rules(registry)`, and (3) installed packages exposing a
  `flake8_lint.rules` entry-point group.
- `config.py` — typed config with a defined precedence: `--config PATH` >
  `flake8_lint.toml` > `pyproject.toml [tool.flake8_lint]` > legacy
  `pyproject.toml [tool.flake8_lint_tests]` (read as a **deprecated fallback with
  a warning**) > defaults.
- `api.py` — the one execution boundary: `check_tree()` / `check_file()` /
  `check_source()` / `lint_paths()` returning structured `RuleViolation` /
  `LintResult`.
- `cli.py` — a ruff-like `flake8-lint check [paths]` command
  (`--select` / `--ignore` / `--no-noqa` / `--rule-module` / `--no-rule-plugins`
  / `--output-format text|json`) with exit codes **0** clean, **1** violations,
  **2** tool/config error.
- `plugin.py` — a thin Flake8 AST adapter (`ProjectRulesPlugin`) over the same
  `api.py` engine, so a real `flake8` invocation also gets the built-in X-rules.
  It does *not* claim to auto-discover installed providers through flake8 — the
  CLI/API remain authoritative for provider resolution.
- `testing.py` — `assert_lint_clean(*paths)`, an explicit **opt-in** pytest
  helper. Installing the package never auto-runs lint during ordinary pytest.
- `docs/custom-rules.md` + `README.md` fully document all of the above, including
  a worked custom-rule example (`ACME001`).

The forces at play: we already maintain this logic **twice** (in-tree prototype
and sibling package), the prototype has no real CLI and no extension story, and
the coding-standard gate is currently invisible except as a pytest side effect.
This ADR decides how AegisSwr consumes the generalised engine and how it runs it.

## Decision

Adopt the standalone `flake8-lint` package as AegisSwr's **single lint engine**,
and treat the three run modes as independently-chosen **adapters over that one
engine and one config section**, not as three separate implementations.

1. **One engine, one config, one registry.** All lint execution in AegisSwr
   routes through `flake8_lint.api`, resolves the same `[tool.flake8_lint]`
   config, and builds the same `RuleRegistry` via `resolve_registry(...)`. There
   is exactly one source of truth for "what is a violation here".

2. **Three run modes, chosen per context — preferably both of the first two:**

   - **CLI** (ruff-like): `flake8-lint check .` as its own CI step, asserting on
     exit codes `0`/`1`/`2`.
   - **pytest**: keep a lint-gate test, but reduce it to a single
     `assert_lint_clean("src", "tests")` call into the shared engine — opt-in,
     never auto-running on package import.
   - **Both**: because both modes resolve the *same* config and the *same*
     registry, running the CLI in CI **and** keeping the pytest assertion locally
     yields guaranteed-identical results. There is no drift between "what blocks
     CI" and "what pytest reports". Nothing in the design forces exactly one mode;
     AegisSwr chooses both.

3. **Rule extensibility via a `USERNNN` convention — no engine change.** The
   registry already accepts any `PREFIX + 3 digits` code
   (`^[A-Z][A-Z0-9]*\d{3}$`), so no code is needed to enable custom rules. The
   AegisSwr convention is:

   - `X0NN` stays **reserved for rules shipped inside the `flake8-lint` package
     itself**.
   - `USER` is **reserved for AegisSwr-project-local rules**, defined in a new
     `src/aegis_swr/lint_rules.py` exposing `register_rules(registry)` and
     assigning codes `USER001`, `USER002`, … one per project-specific check.

   Wired in once via `pyproject.toml`:

   ```toml
   [tool.flake8_lint]
   rule_modules = ["aegis_swr.lint_rules"]
   ```

   Both CLI and pytest pick up USER-rules automatically because they resolve the
   registry identically. `# noqa: USER001` and `select = ["USER"]` (prefix match)
   work exactly like the X-codes do today.

   **No USER-rules exist yet.** `X001`-`X012` currently cover AegisSwr's policy;
   this is groundwork for the next project-specific check, not an immediate rule
   addition. `src/aegis_swr/lint_rules.py` is created only when there is an actual
   check to add.

4. **Migration (this ADR authorises the plan; `python-expert` executes it):**

   1. Add `flake8-lint` as a **dev dependency** — a path or git (pinned) reference
      for now, since the sibling package is not published to any index yet.
   2. Rename `[tool.flake8_lint_tests]` → `[tool.flake8_lint]` in
      `pyproject.toml`. The legacy section is still read as a deprecated fallback
      (with a warning), so this is not a hard break — but the rename should happen
      as part of this rollout rather than living permanently on the fallback path.
   3. Replace `tests/flake8_lint/test_project_lint.py`'s hand-rolled AST walk with
      a single `assert_lint_clean("src", "tests")`, and drop
      `tests/flake8_lint/config.py`'s duplicate include/exclude/select/discovery
      logic — the package's `config.py` now owns it.
   4. Delete `src/flake8_project_rules/` entirely (superseded) and
      `tests/flake8_lint/test_plugin_direct.py`'s per-rule detection tests (now
      owned by the `flake8-lint` package's own suite). Keep only what AegisSwr
      needs project-locally — USER-rule tests, once any exist.
   5. Add `src/aegis_swr/lint_rules.py` only when a real AegisSwr-specific check
      is needed.
   6. Update CI to run `flake8-lint check .` as its **own** step, separate from
      `pytest`, so a lint failure is visible independently and does not hide
      behind (or duplicate) a test failure.

## Alternatives Considered

| Alternative | Pros | Cons | Reason rejected |
|-------------|------|------|-----------------|
| **Status quo** — keep `src/flake8_project_rules/` + the bespoke pytest-only harness as-is | Zero migration cost; already green | No standalone CLI (lint only surfaces as a pytest failure, maskable by unrelated breakage); config/discovery logic now duplicated across two repos forever; no clean custom-rule extension story | Freezes the blind spot and doubles maintenance; the generalised engine already exists |
| **Wire the existing `flake8_project_rules` up as a *real* flake8 plugin** — add `flake8` as a dependency and register the entry point, rather than adopting the sibling package | Reuses code already in-tree; gains a real runner (`flake8`) without a new dependency on an unreleased sibling; single-repo, no cross-repo coordination | Pulls in the full flake8 runtime + its own config surface (`setup.cfg`/`.flake8`/`tox.ini` selection semantics) that must be reconciled with our TOML config; still no ruff-like standalone `check` sub-CLI with our own 0/1/2 exit contract; still no typed `RuleRegistry`, no `USERNNN` extension contract, no fail-fast on invalid/duplicate codes; leaves the sibling package as a permanent divergent fork of the same rules | Solves the "no runner" symptom but not the duplication or extensibility root cause; would still diverge from the finished engine |
| **Publish `flake8-lint` to an internal package index now**, then depend on a released version | Clean, versioned dependency; normal pinning; no path/VCS reference in `pyproject.toml`; decouples the two repos' release cadence | Requires standing up / choosing an internal index and a release process before any of this lands; premature for a single first consumer; adds ceremony to every rule tweak during the initial co-evolution period | Deferred, not rejected — revisit once the engine stabilises and/or a second consumer appears (see Consequences / Validation) |
| **Adopt the sibling package but run it via pytest *only*** (drop the CLI step) | Smallest CI change; one gate | Recreates the current blind spot — lint stays entangled with the test run and cannot be a standalone, independently-visible gate; loses the 0/1/2 exit-code contract in CI | Contradicts the core motivation (an independent, visible lint gate) |
| **Adopt the sibling package but run it via CLI *only*** (drop the pytest assertion) | One gate; simplest local story | Loses the in-`pytest` local ergonomics contributors already rely on; developers who only run `pytest` locally would not see lint failures until CI | Rejected in favour of "both", which the shared engine makes free of drift |

## Consequences

### Positive

- **Single source of truth for lint.** CLI and pytest resolve the identical
  config and registry through one `api.py` boundary — "what blocks CI" and "what
  pytest reports" cannot diverge.
- **The lint gate becomes independently visible.** `flake8-lint check .` runs as
  its own CI step with a real `0`/`1`/`2` exit contract; a lint failure no longer
  hides behind or masquerades as a test failure.
- **Duplication is eliminated.** `src/flake8_project_rules/` and the hand-rolled
  `tests/flake8_lint/config.py` discovery/selection logic are deleted; AegisSwr
  stops maintaining a second copy of rules that already live in the package.
- **A first-class extension story.** `USERNNN` rules drop into
  `src/aegis_swr/lint_rules.py` behind one `rule_modules` entry, picked up by both
  run modes automatically, with `# noqa: USER001` and prefix `select`/`ignore`
  working exactly as for X-codes. Invalid or duplicate codes fail fast.
- **Fewer moving parts than a real flake8 plugin.** No flake8 runtime, no
  competing `.flake8`/`setup.cfg` config surface — one TOML section governs
  everything.
- **Non-breaking config migration.** The legacy `[tool.flake8_lint_tests]`
  section is still honoured as a deprecated fallback, so the rename is safe to
  land incrementally.

### Negative

- **Cross-repo coupling to a repo AegisSwr does not release.** `flake8-lint`
  lives in a sibling repo (`~/Projects/Flake8Lint`) whose release cadence AegisSwr
  does not control. Depending on it as a path/git reference introduces a real
  coordination cost: a change to shared rule behaviour now spans two repos, and an
  unpinned/floating reference could silently change what AegisSwr considers a
  violation. **Mitigation:** pin an exact commit/tag; never float on a branch (see
  Validation / Rollout).
- **Rule ownership moves out of the repo.** X-rule behaviour and its per-rule
  tests are now owned by the package's own suite; AegisSwr keeps only USER-rule
  tests. A rule regression must be diagnosed and fixed in the sibling repo, then
  re-pinned here — slower than an in-tree fix.
- **A new dev dependency on the install/CI path.** CI and every contributor's dev
  environment must resolve the path/VCS dependency (and, for git references, have
  access to that repo). This is a new failure mode for `uv sync` in constrained
  environments.
- **Two CI steps to keep honest.** Running both CLI and pytest means both must
  reference the same pinned engine; if the pins ever diverge (e.g. a stale lockfile),
  the "no drift" guarantee is only as good as the single pinned version. **Mitigation:**
  one pin in `pyproject.toml`/lockfile, asserted by CI lockfile-integrity.
- **`# noqa` policy surface moves wholesale.** `allow_noqa` / `noqa_allowed` /
  `noqa_forbidden` semantics are now the package's; the existing AegisSwr
  allow-list (currently `src/aegis_swr/core/events.py`) must be carried over
  verbatim during the rename and re-verified.

### Future scope

- Promotion from a path/git dependency to a **published, versioned** dependency on
  an internal index, once the engine stabilises or a second consumer appears.
- The first actual `USERNNN` rule (with its sample fixtures and detection tests)
  when a genuinely AegisSwr-specific policy check is identified — this ADR only
  establishes the slot and the convention.

## Validation / Rollout

- **Pin, do not float.** The `flake8-lint` dev dependency references an **exact
  commit SHA or tag**, recorded in `pyproject.toml` and the lockfile — never a
  moving branch. CI lockfile-integrity fails the build if the resolved engine
  drifts from the pin.
- **CLI gate.** `flake8-lint check .` runs as its own CI step and must exit `0`
  on a clean tree; a seeded violation must exit `1`; a malformed config must exit
  `2`. The step is ordered so its result is legible independently of `pytest`.
- **pytest parity.** `assert_lint_clean("src", "tests")` runs in the unit suite
  and must agree with the CLI on the same tree — a deliberate seeded violation
  must be caught by **both** modes (parity check), proving no config/registry
  drift.
- **Config-migration check.** After the rename, a build with only the legacy
  `[tool.flake8_lint_tests]` section still lints (fallback path) **and** emits the
  deprecation warning; a build with `[tool.flake8_lint]` present ignores the legacy
  section. The existing `noqa_allowed` entry (`core/events.py`) is verified to
  behave identically pre- and post-rename.
- **Deletion is clean.** After `src/flake8_project_rules/` and
  `test_plugin_direct.py` are removed, a repo-wide grep confirms no remaining
  importer of `flake8_project_rules`, and the full suite plus both lint modes stay
  green.
- **USER-rule readiness (no rule shipped yet).** A throwaway `USER999` fixture
  proves that a `rule_modules = ["aegis_swr.lint_rules"]` provider is resolved by
  both CLI and pytest, that `# noqa: USER999` suppresses it, and that a bad code
  (e.g. `user001` / `USER1`) fails fast via `InvalidRuleCodeError` — then the
  fixture is removed. No `USERNNN` rule is committed by this ADR.

## Links

- **Roadmap task:** [Milestone 0006 - static-analysis rule expansion (Task 01.0)](/docs/roadmap/0006-improvements-and-optimizations/plan.md)
- **Supporting specs:** [docs/dev/python_coding_standard.md](/docs/dev/python_coding_standard.md); sibling engine docs `~/Projects/Flake8Lint/docs/custom-rules.md` and `~/Projects/Flake8Lint/README.md`
- **Current prototype (to be superseded):** `src/flake8_project_rules/`, `tests/flake8_lint/`
- **Diagrams:** _(none)_
