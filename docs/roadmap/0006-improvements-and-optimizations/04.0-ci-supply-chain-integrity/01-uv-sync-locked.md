# 01 — `uv sync --locked` across every workflow call site

**Parent task:** [04.0 CI Supply-Chain Integrity](README.md)
**State:** ⬜ Not started
**Depends on:** none (but see sequencing note — land with/after subtask 02)
**Blocks:** none

## Objective

Convert every unlocked `uv sync` in the workflow files to `uv sync --locked` so
CI installs exactly what `uv.lock` pins and fails loudly on drift. The nine
current call sites:

- `.github/workflows/ci.yml`: lines **30** (`lint`), **60** (`unit-test`),
  **71** (`code-intel-isolation`), **171** (`openclaude-unit-coverage`),
  **199** (`code-intel-unit-coverage`), **265** (`openclaude-integration`),
  **301** (`claude-code-integration`), **334** (`openhands-integration`).
- `.github/workflows/coverage.yml`: line **35** (`test-main-project`).

Each is the bare form `- run: uv sync` (coverage.yml:34-35 spells it
`- name: Install dependencies` / `run: uv sync`).

## Implementation approach

Replace each occurrence:

```yaml
# before
- run: uv sync
# after
- run: uv sync --locked
```

and for the named step in coverage.yml:

```yaml
- name: Install dependencies
  run: uv sync --locked
```

Mechanical, but do it site by site and re-grep afterward:

```bash
grep -rn "uv sync" .github/workflows/
```

must show `--locked` on every line and **no** bare `uv sync` remaining. If
[Task 02.0](/docs/roadmap/0006-improvements-and-optimizations/02.0-close-mypy-enforcement-gap/README.md)'s
`mypy` job has already landed, its `uv sync` is a tenth site — include it.

## Exclusions

- Do not touch `_ci-relevance-gate.yml` — it has no `uv sync`.
- Do not add `--frozen` as a substitute: `--locked` is the correct semantic here
  (verify lock is current, then install from it); `--frozen` skips the currency
  check, which weakens the guarantee this task exists to add.
- No change to `pyproject.toml` or `uv.lock`. If the sweep makes CI red because
  the lockfile is *already* drifted, that is a real finding — fix it with
  `uv lock` as a separate, clearly-labelled commit (and let subtask 02's gate be
  what surfaces it).

## Test plan

- CI is the test: after the sweep, every job that installs dependencies must
  still go green on a branch whose `uv.lock` is in sync with `pyproject.toml`.
- Negative proof (in the PR description, not committed): on a scratch branch,
  hand-edit `pyproject.toml` to add a dependency without re-locking, push, and
  confirm the `--locked` jobs now **fail** — demonstrating the guarantee is live.
  Revert the scratch edit.
- Post-change `grep -rn "uv sync" .github/workflows/` shows `--locked`
  everywhere and no bare invocation.
</content>
