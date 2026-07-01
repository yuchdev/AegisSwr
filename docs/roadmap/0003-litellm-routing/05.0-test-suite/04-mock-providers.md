# 04 - Mock providers + test_provider_scenarios.py

**Parent task:** 05.0 Test Suite
**State:** ⬜ Not started
**Depends on:** 03 (test_router.py fixtures established)
**Blocks:** -

## Objective

Implement `tests/router/mocks/providers.py` - reusable mock provider factories
that simulate real-world provider failure modes - and
`tests/router/mocks/test_provider_scenarios.py` which exercises the router's
response to each mode.

## `tests/router/mocks/providers.py`

```python
"""
Reusable mock provider factories for testing.
Each returns a coroutine suitable as the side_effect of a mocked
LiteLLMClient.complete (the router calls this, not litellm directly).
"""
from __future__ import annotations
import asyncio
from typing import Callable
from aegis.router.exceptions import RouterException
from aegis.router.client import CompletionResponse


def make_timeout_provider(after_s: float = 0.0) -> Callable:
    """Raises asyncio.TimeoutError (wrapped as RouterException) immediately."""

def make_rate_limit_provider(fail_n_times: int = 1) -> Callable:
    """Raises RouterException simulating HTTP 429 for the first N calls, then succeeds."""

def make_context_length_provider() -> Callable:
    """Raises RouterException simulating 'context length exceeded' error."""

def make_slow_provider(latency_s: float = 0.5) -> Callable:
    """Succeeds but with artificial latency (asyncio.sleep)."""

def make_success_provider(content: str = "ok") -> Callable:
    """Always succeeds with a fixed CompletionResponse."""
```

## `tests/router/mocks/test_provider_scenarios.py`

```python
async def test_timeout_triggers_fallback():
    """Timeout on primary causes router to fall back to the next model."""

async def test_rate_limit_triggers_retry_then_succeeds():
    """429 on first attempt triggers retry; second attempt succeeds."""

async def test_context_length_skips_retry_goes_to_fallback():
    """Context-length-exceeded skips retries and goes directly to fallback."""

async def test_all_models_timeout_raises_all_providers_exhausted():
    """When every model in the chain times out, AllProvidersExhausted is raised."""

async def test_rate_limit_retry_scenario_emits_correct_events():
    """
    Scenario: 429 → retry → success.
    Expected events: Started, Failed(attempt=0), Started, Completed.
    """

async def test_flaky_provider_succeeds_within_retries():
    """A provider with 50% failure rate (deterministic seed) succeeds within 2 retries."""
```

## Constraints

- All providers mock `LiteLLMClient.complete`, not `litellm.acompletion` - the
  router never calls litellm directly.
- `asyncio.sleep` in `make_slow_provider` is real to test that the router
  awaits it correctly, but should be short (< 10 ms) to keep the test suite fast.
- No real network calls.

## Success criteria

- [ ] `providers.py` implements all 5 factory functions.
- [ ] All 6 scenario tests present and passing.
- [ ] `test_rate_limit_retry_scenario_emits_correct_events` asserts the
      exact event sequence: `[Started, Failed(attempt=0), Started, Completed]`.
