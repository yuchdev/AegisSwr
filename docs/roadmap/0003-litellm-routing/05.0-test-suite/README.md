# Task 05.0 - Test Suite

**Parent milestone:** [Milestone 0003 - LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Write and verify the full test suite for the `aegis/router/` module across
three levels:

1. **Unit tests** (`tests/router/`) - all external I/O mocked, no API keys.
2. **Mock-provider tests** (`tests/router/mocks/`) - provider failure-mode
   simulation (timeouts, rate limits, context-length errors).
3. **Integration tests** (`tests/integration/test_router_integration.py`) -
   real provider calls, skipped unless the corresponding API key is set.

Tests are written **incrementally alongside** Tasks 02.0–04.0, not after.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [test_config.py](01-test-config.md) | ⬜ Not started | - |
| 02 | [test_client.py](02-test-client.md) | ⬜ Not started | - |
| 03 | [test_router.py](03-test-router.md) | ⬜ Not started | - |
| 04 | [mock providers + test_provider_scenarios.py](04-mock-providers.md) | ⬜ Not started | - |
| 05 | [integration tests](05-integration-tests.md) | ⬜ Not started | - |

## Key constraints

- All unit tests pass with `ANTHROPIC_API_KEY=""` - zero network calls.
- Integration tests use `pytest.mark.integration` and `pytest.mark.skipif`
  guards - they are **skipped** (not failed) when keys are absent.
- The litellm isolation grep test lives in `test_client.py` and is also wired
  into CI as a standalone lint step.
- `pytest-asyncio` mode is `asyncio_mode = "auto"` (no per-test `@pytest.mark.asyncio`
  decorator required).

## Test layout

```
tests/
└── router/
    ├── __init__.py
    ├── conftest.py               ← shared fixtures (event_bus, router config stubs)
    ├── test_config.py
    ├── test_client.py
    ├── test_router.py
    └── mocks/
        ├── __init__.py
        ├── providers.py          ← reusable mock provider factories
        └── test_provider_scenarios.py

tests/integration/
    ├── __init__.py
    ├── conftest.py               ← router_from_yaml, bad-key fixtures
    └── test_router_integration.py
```
