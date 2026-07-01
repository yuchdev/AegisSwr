# 04 — CI pipeline additions

**Parent task:** 07.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 05.0 (test suite complete)
**Blocks:** 05

## Objective

Add router-specific CI jobs to the project's CI pipeline
(`.github/workflows/ci.yml` or equivalent). Three new jobs:

1. **Unit + mock tests** — no API keys, always runs.
2. **LiteLLM isolation lint** — named standalone job so drift is visible.
3. **Integration tests** — skipped (not failed) when keys are absent.

## CI additions

```yaml
# .github/workflows/ci.yml (additions)

jobs:
  # ... existing jobs ...

  router-unit-tests:
    name: "Router: unit + mock tests"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install poetry && poetry install
      - run: poetry run pytest tests/router/ -v --tb=short
        env:
          ANTHROPIC_API_KEY: ""    # explicitly empty — unit tests must pass without keys

  router-litellm-isolation:
    name: "Lint: litellm must only appear in router/client.py"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          count=$(grep -rl "litellm" aegis/ | grep -v "aegis/router/client.py" | wc -l)
          if [ "$count" -gt 0 ]; then
            echo "ERROR: litellm referenced outside aegis/router/client.py:"
            grep -rl "litellm" aegis/ | grep -v "aegis/router/client.py"
            exit 1
          fi

  router-integration-tests:
    name: "Router: integration tests (skipped without keys)"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install poetry && poetry install
      - run: poetry run pytest -m integration tests/integration/ -v --tb=short
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          VLLM_BASE_URL: ${{ secrets.VLLM_BASE_URL }}
          VLLM_API_KEY: ${{ secrets.VLLM_API_KEY }}
```

## pyproject.toml additions

Register the `integration` marker so pytest doesn't warn about unknown marks:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests that require real API keys (skipped in CI without secrets)",
]
```

## Constraints

- The isolation lint job must have a **named step** (`name:`) so it appears
  in the PR checks as `"Lint: litellm must only appear in router/client.py"`.
- `router-unit-tests` runs with `ANTHROPIC_API_KEY: ""` to prove the unit
  suite does not depend on keys.
- `router-integration-tests` must be **skipped** (exit 0) when secrets are
  empty — this is handled by `pytest.mark.skipif` in the tests themselves.

## Success criteria

- [ ] Three new CI job definitions added to the pipeline.
- [ ] `integration` marker registered in `pyproject.toml`.
- [ ] `router-litellm-isolation` job name matches the title in this file.
- [ ] CI passes on a branch with no API secrets set (integration tests skip).
