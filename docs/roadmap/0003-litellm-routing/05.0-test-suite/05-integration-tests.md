# 05 - Integration tests

**Parent task:** 05.0 Test Suite
**State:** ⬜ Not started
**Depends on:** 04.0 (ModelRouter complete), 06.0/04 (NullClient available)
**Blocks:** -

## Objective

Write `tests/integration/test_router_integration.py` - real provider calls
that verify end-to-end flow from `ModelRouter.complete()` to a real model
response. Tests are unconditionally **skipped** (not failed) when the
corresponding API key is absent.

## Test list

```python
import os
import pytest

pytestmark = pytest.mark.integration

def _has_key(env_var: str) -> bool:
    return bool(os.environ.get(env_var))


@pytest.mark.skipif(not _has_key("ANTHROPIC_API_KEY"), reason="No ANTHROPIC_API_KEY")
async def test_anthropic_claude_completes_successfully(router_from_yaml):
    """Real call to claude-haiku (cheapest). Verifies non-empty response."""

@pytest.mark.skipif(not _has_key("DEEPSEEK_API_KEY"), reason="No DEEPSEEK_API_KEY")
async def test_deepseek_completes_successfully(router_from_yaml):
    """Real call to deepseek-chat with a minimal forensic prompt."""

@pytest.mark.skipif(not _has_key("VLLM_BASE_URL"), reason="No VLLM_BASE_URL")
async def test_self_hosted_vllm_completes_successfully(router_from_yaml):
    """Real call to the self-hosted vLLM endpoint."""

@pytest.mark.skipif(
    not _has_key("ANTHROPIC_API_KEY") or not _has_key("DEEPSEEK_API_KEY"),
    reason="Needs both ANTHROPIC_API_KEY and DEEPSEEK_API_KEY",
)
async def test_fallback_to_deepseek_when_anthropic_fails(router_with_bad_anthropic_key):
    """Invalid Anthropic key → fallback to DeepSeek; RouterFallbackUsed emitted."""

async def test_router_events_emitted_on_real_call(router_from_yaml):
    """RouterCallStarted and RouterCallCompleted emitted with correct run_id."""

async def test_all_providers_exhausted_on_bad_keys(router_with_all_bad_keys):
    """Router with invalid keys raises AllProvidersExhausted with .tried populated."""
```

## `tests/integration/conftest.py` fixtures

```python
@pytest.fixture
def router_from_yaml(tmp_path):
    """Builds ModelRouter from a minimal agents.yaml using real env vars.
    Uses cheapest available model (claude-haiku-4-5 or deepseek-chat)."""

@pytest.fixture
def router_with_bad_anthropic_key(tmp_path, monkeypatch):
    """Sets ANTHROPIC_API_KEY to 'invalid-key' so Anthropic calls fail."""

@pytest.fixture
def router_with_all_bad_keys(tmp_path, monkeypatch):
    """Sets all provider API keys to 'invalid-key'."""
```

## Constraints

- `pytest.mark.integration` must be registered in `pyproject.toml` or
  `pytest.ini` under `[tool.pytest.ini_options] markers`.
- Run with: `pytest -m integration tests/integration/ -v --tb=short`
- CI runs them only if keys are present:
  ```yaml
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
    VLLM_BASE_URL: ${{ secrets.VLLM_BASE_URL }}
  ```
- The `router_from_yaml` fixture uses `claude-haiku-4-5-20251001` for Anthropic
  (cheapest model) to minimize integration test cost.

## Success criteria

- [ ] All 6 test functions present.
- [ ] `pytest tests/router/` (unit suite) passes without API keys.
- [ ] `pytest -m integration` skips all tests when no keys are set.
- [ ] `test_all_providers_exhausted_on_bad_keys` does not require real API keys
      (uses monkeypatched invalid keys so it always runs).
