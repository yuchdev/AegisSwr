# 01 — Add the `mypy` CI job (green against the current `mypy.ini`)

**Parent task:** [02.0 Close the mypy Enforcement Gap](README.md)
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** subtasks 02–06 (they need this gate present before they can prove a
re-enabled code stays at zero in CI)

## Objective

`.github/workflows/ci.yml`'s `lint` job (ci.yml:15-36) runs `ruff check src/
tests/` (ci.yml:28) and `uv run flakeforge check .` (ci.yml:36) and nothing
else — there is no `mypy` invocation anywhere in the file. Add a dedicated
`mypy` job that runs `uv run mypy src/aegis_swr/` against the **current**
`mypy.ini` (all eleven codes in `disable_error_code` still disabled), so the
gate exists and is green from the first commit. This is the floor every later
burn-down subtask raises.

## Implementation approach

Add a new top-level job to ci.yml mirroring the existing `unit-test` job's
shape (ci.yml:47-61) so it inherits the same relevance-gate wiring and Python
matrix:

- `needs: assess` and `if: needs.assess.outputs.run_ci == 'true'` — identical
  to every other `ci.yml` job, so a docs-only change skips it via the
  `_ci-relevance-gate.yml` reusable workflow (ci.yml:12-13).
- `strategy.matrix.python-version: ["3.12", "3.13"]` — matches `lint` and
  `unit-test`; `mypy.ini` pins `python_version = 3.12` so both interpreters
  type-check against the 3.12 contract.
- Steps: `actions/checkout@v4`, `astral-sh/setup-uv@v4`, `uv sync`, then
  `uv run mypy src/aegis_swr/`.

Scope the run to `src/aegis_swr/` (not `tests/`): `strict = true` is a
shipped-code guarantee, and `tests/` legitimately contains untyped fixtures
and monkeypatching that would generate noise unrelated to this task.

### Sketch (the exact job block the implementer lands)

```yaml
  type-check:
    name: "mypy (strict; src/aegis_swr)"
    needs: assess
    if: needs.assess.outputs.run_ci == 'true'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run mypy src/aegis_swr/
```

> Note the `uv sync` here is one more unlocked call site. Coordinate with
> [Task 04.0](/docs/roadmap/0006-improvements-and-optimizations/04.0-ci-supply-chain-integrity/README.md):
> if 04.0 has already landed, this new step must use `uv sync --locked` to stay
> consistent; if this lands first, 04.0's sweep will convert it.

## Drop the four zero-violation codes in this subtask (measured 2026-10-03)

Running `mypy` with every disabled code re-enabled and nothing else disabled
(`uv run mypy --config-file <strict, no disable_error_code> src/aegis_swr/`)
found **211 errors across 7 of the 11 disabled codes**; the remaining four —
`no-any-return`, `union-attr`, `return-value`, `annotation-unchecked` — produced
**zero** diagnostics. These four have no burn-down to do: once this subtask's CI
job is in place, remove them from `mypy.ini`'s `disable_error_code` in the same
PR and confirm the job stays green. Do not give them their own burn-down
subtask — subtasks 02–06 below cover only the seven codes with a real backlog.
Re-run the zero-disable command above immediately before landing, in case new
code introduced one of these errors since this measurement.

## Baseline methodology (reused verbatim by subtasks 02–06)

Before a later subtask re-enables a code, it establishes that code's baseline by
removing it from `disable_error_code` *locally* and counting the diagnostics:

```bash
uv run mypy --enable-error-code <code> src/aegis_swr/ 2>&1 | grep -c "error:"
```

That count is the backlog the subtask must drive to zero before dropping the
code from `mypy.ini` for real. Record the starting count in the subtask's PR
description so the burn-down is auditable.

## Exclusions

- `tests/` is out of scope (see Objective). A follow-up milestone may widen the
  job; this task does not.
- The `pydantic.mypy` plugin and `enable_error_code = redundant-cast,no-redef`
  (mypy.ini:4-5) are left exactly as-is — this subtask changes CI only, not the
  config.

## Test plan

- The CI job itself is the test: it must report **success** on the current
  `mypy.ini`. If it is red on day one, a code was mis-scoped — fix the scope,
  do not weaken `mypy.ini` to make it pass.
- Add a negative smoke check to the PR description (not committed): introduce a
  deliberate type error in a scratch file under `src/aegis_swr/`, confirm the
  job reddens, then remove it — proving the gate is live, not inert.
- No `tests/` changes: this subtask adds no unit test (it is CI config); the
  burn-down subtasks that follow carry the type-correctness assertions.
</content>
