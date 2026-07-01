# 01 - test_config.py

**Parent task:** 05.0 Test Suite
**State:** ⬜ Not started
**Depends on:** 02.0/01 (config dataclasses)
**Blocks:** -

## Objective

Write `tests/router/test_config.py` - full coverage of `RouterConfig.from_yaml()`
and its validation contract (rules R1–R4 from `01.0/03-config-validation.md`).
All tests pass with no network access and no API keys set.

## Test list

```python
def test_from_yaml_resolves_env_vars(tmp_path, monkeypatch):
    """${ANTHROPIC_API_KEY} is resolved from environment."""

def test_from_yaml_missing_env_var_lists_all_missing(tmp_path):
    """ConfigValidationError message lists ALL missing vars, not just the first."""

def test_from_yaml_missing_provider_reference_raises(tmp_path):
    """Agent referencing an undefined provider key raises ConfigValidationError."""

def test_from_yaml_is_idempotent(tmp_path, monkeypatch):
    """Calling from_yaml twice on the same file returns equal RouterConfig objects."""

def test_agent_for_role_missing_raises_key_error_with_helpful_message(tmp_path, monkeypatch):
    """KeyError message includes the requested role and the available roles."""

def test_frozen_dataclasses_are_immutable(tmp_path, monkeypatch):
    """Attempt to mutate ProviderConfig, AgentConfig, RouterConfig raises FrozenInstanceError."""

def test_optional_fields_have_correct_defaults(tmp_path, monkeypatch):
    """agents.yaml entries without fallback/timeout/retry use documented defaults."""

def test_empty_api_key_env_var_is_valid(tmp_path, monkeypatch):
    """VLLM_API_KEY='' (empty string) is valid - only unset vars raise R1."""
```

## Shared fixture pattern

```python
import pytest
from pathlib import Path
from aegis.router.config import RouterConfig
from aegis.router.exceptions import ConfigValidationError

MINIMAL_YAML = """
providers:
  anthropic:
    api_key: ${TEST_KEY}
agents:
  triage:
    model: anthropic/claude-haiku-4-5-20251001
    role: evidence_classifier
"""

@pytest.fixture
def yaml_file(tmp_path):
    def _make(content: str) -> Path:
        p = tmp_path / "agents.yaml"
        p.write_text(content)
        return p
    return _make
```

## Constraints

- Use `monkeypatch.setenv` / `monkeypatch.delenv` for environment manipulation.
- `tmp_path` for all YAML files - never write to the real `aegis/config/`.
- No network calls; no litellm import in this file.

## Success criteria

- [ ] All 8 test functions present and passing.
- [ ] `test_from_yaml_missing_env_var_lists_all_missing` verifies the error
      message contains **both** missing var names when two are missing.
- [ ] `test_optional_fields_have_correct_defaults` checks `fallback=()`,
      `timeout_s=30.0`, `retry.attempts=2`, `retry.backoff_s=1.0`.
