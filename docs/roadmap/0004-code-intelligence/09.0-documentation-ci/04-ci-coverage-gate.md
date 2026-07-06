# 04 - CI coverage gate extension

**Parent task:** 09.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 07.0 (unit suite, incl. 100% branch on `tool.py`), 08.0 (integration suite + skip guards); wires their execution and gates into CI.
**Blocks:** none

## Objective

Wire the OpenClaude test suites into CI as **enforced gates**, not documented
targets. On every PR the `tests/openclaude/unit/` suite runs with zero external
dependencies and a hard coverage gate (≥ 90% overall unit coverage on
`aegis.openclaude`, 100% branch coverage on `aegis/openclaude/tool.py`);
`tests/openclaude/integration/` is gated behind an `OPENCLAUDE_INTEGRATION`
signal so it is skipped on PRs by default and can run on main/nightly. A coverage
regression must fail the pipeline.

## CI config (`.github/workflows/ci.yml` — new named jobs)

```yaml
  openclaude-unit-coverage:
    name: "OpenClaude: unit + coverage gate (>=90%, 100% on tool.py)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install poetry && poetry install --with dev
      - name: "Unit tests + overall coverage gate"
        run: |
          poetry run pytest tests/openclaude/unit/ \
            --cov=aegis.openclaude --cov-report=term-missing \
            --cov-fail-under=90
        env:
          # Prove the unit suite needs no external deps / server / binary
          OPENCLAUDE_GRPC_URL: ""
          OPENCLAUDE_INTEGRATION: ""
      - name: "100% branch coverage on tool.py"
        run: |
          # Separate, stricter gate scoped to tool.py; --cov-branch enables branch metrics.
          poetry run pytest tests/openclaude/unit/test_tool.py \
            --cov=aegis.openclaude.tool --cov-branch \
            --cov-report=term-missing --cov-fail-under=100

  openclaude-integration:
    name: "OpenClaude: integration (gated on OPENCLAUDE_INTEGRATION)"
    # Skipped on PRs by default; runs on main pushes / nightly schedule.
    if: >-
      github.event_name != 'pull_request' &&
      (github.ref == 'refs/heads/master' || github.event_name == 'schedule')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install poetry && poetry install --with dev
      - name: "Integration tests (skip when signal/binary absent)"
        run: poetry run pytest tests/openclaude/integration/ -v --tb=short
        env:
          OPENCLAUDE_INTEGRATION: "1"
          OPENCLAUDE_GRPC_URL: ${{ secrets.OPENCLAUDE_GRPC_URL }}
          OPENCLAUDE_BINARY: ${{ secrets.OPENCLAUDE_BINARY }}
```

To make integration a schedule-eligible workflow, add a `schedule:` trigger
(e.g. nightly cron) alongside the existing `push`/`pull_request` triggers.

## pyproject.toml additions

Register markers and default coverage config so behaviour is reproducible
locally and in CI:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: OpenClaude live-process tests; skipped unless OPENCLAUDE_INTEGRATION is set",
]

[tool.coverage.run]
branch = true
```

The integration tests must self-skip (via `pytest.mark.skipif` on
`OPENCLAUDE_INTEGRATION` / binary presence) so that even if the job runs without
the signal it reports **skipped, not failed** (Global acceptance criterion).

## Implementation notes
- The overall `--cov-fail-under=90` and the scoped `--cov-fail-under=100` on
  `tool.py` are the two hard gates; a drop below either turns the pipeline red.
- Keep the two coverage runs as separate steps so the failure message names which
  gate broke.
- Existing repo coverage config (`.github/workflows/coverage.yml`) gates the whole
  project at 85%; this job is additive and scoped to `aegis.openclaude` — do not
  lower the existing global gate.
- Real on-disk package is `aegis_swr` under `src/`; if so, use
  `--cov=src/aegis_swr/openclaude` etc. when implementing (see flagged inconsistency).
- Defer authoring the tests and skip guards themselves to `testing-expert`
  (tasks 07.0 / 08.0).

## Constraints
- The coverage gate must be enforced in CI configuration (fails the pipeline on
  regression), not merely documented as a target.
- `tests/openclaude/unit/` must pass with `OPENCLAUDE_GRPC_URL` unset and no
  OpenClaude binary on `PATH` (zero external dependencies).
- `tests/openclaude/integration/` is skipped on PRs by default; only main/nightly
  may run it, and it must skip (not fail) when the signal/binary is absent.
- `asyncio`/live-process concerns stay inside integration; unit stays hermetic.

## Success criteria
- [ ] Named CI job runs `tests/openclaude/unit/` on every PR with no external deps.
- [ ] Overall unit coverage gate `--cov-fail-under=90` on `aegis.openclaude` enforced.
- [ ] 100% branch coverage gate on `aegis/openclaude/tool.py` enforced as a
      separate failing step.
- [ ] `tests/openclaude/integration/` gated behind `OPENCLAUDE_INTEGRATION`,
      skipped on PRs, eligible on main/nightly.
- [ ] `integration` marker + `branch = true` registered in `pyproject.toml`.
- [ ] Verified: a deliberate coverage regression turns the pipeline red.
