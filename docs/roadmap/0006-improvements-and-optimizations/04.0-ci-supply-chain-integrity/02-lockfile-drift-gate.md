# 02 — Dedicated fast-failing lockfile-drift gate

**Parent task:** [04.0 CI Supply-Chain Integrity](README.md)
**State:** ⬜ Not started
**Depends on:** none (land with/before subtask 01 — see task README sequencing)
**Blocks:** none

## Objective

Even with every `uv sync` pinned to `--locked` (subtask 01), a drifted lockfile
surfaces as a failure in *whichever* job happens to run `uv sync` first — and
with the matrix/relevance wiring in `ci.yml`, that can be an opaque,
dependency-resolution-flavoured error in, say, `openhands-integration` rather
than an obvious "your lockfile is stale" message. Add a single, dedicated,
fast step that checks drift explicitly and runs **early in the `lint` job**, so
the first and clearest symptom of drift is one labelled red step that takes
seconds.

## Implementation approach

Add a step at the **top** of the `lint` job's `steps` (ci.yml:22-36), before the
`ruff`/`flakeforge` work, after `setup-uv`:

```yaml
      - uses: astral-sh/setup-uv@v4
      - name: "Lockfile drift gate (uv.lock in sync with pyproject.toml)"
        # Fast fail: if uv.lock is stale, report it here in seconds with a clear
        # label instead of as an opaque resolution error in a downstream job.
        run: uv lock --check
```

`uv lock --check` verifies the lockfile is current against `pyproject.toml`
*without* installing anything and exits non-zero on drift — the cheapest possible
drift probe. (If a given `uv` version prefers `uv sync --locked --dry-run` for a
no-install check, either is acceptable; `uv lock --check` is the most direct.)

Placement notes:

- Put it in `lint` specifically because `lint` is already the fastest matrixed
  job and gates nothing expensive; a drift failure there blocks the merge
  immediately via required-checks without waiting on the test matrix.
- Keep the job's existing `needs: assess` /
  `if: needs.assess.outputs.run_ci == 'true'` guard — a docs-only change that
  does not touch manifests still skips it, consistent with every sibling job.
- This complements the existing `dep_audit.py` PostToolUse hook, which runs a
  CVE/licence advisory on manifest *edits* locally but does **not** check
  lock/manifest *currency* — the drift gate fills that specific gap in CI.

## Exclusions

- The gate checks *drift only*; it does not run `pip-audit`/CVE scanning (that is
  the `/dep-audit` skill + `dep_audit.py` hook's job — do not duplicate it here).
- It does not auto-fix: a red gate instructs the developer to run `uv lock` and
  commit; CI never mutates the lockfile.

## Test plan

- CI is the test: the step is green when `uv.lock` matches `pyproject.toml`.
- Negative proof (PR description, not committed): hand-add a dependency to
  `pyproject.toml` without `uv lock`, push, and confirm the **drift gate step**
  (not a downstream job) is the one that reddens, with its labelled name visible
  in the checks list. Revert.
- Confirm the step runs before `ruff check` in the `lint` job's step order so it
  is the earliest failure.
</content>
