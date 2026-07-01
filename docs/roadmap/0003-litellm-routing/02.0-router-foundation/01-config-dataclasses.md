# 01 — config.py — RouterConfig dataclasses

**Parent task:** 02.0 Router Foundation Types
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03.0, 04.0

## Objective

Implement `aegis/router/config.py` — typed, frozen dataclasses that parse
`agents.yaml` into structured config objects. This file has **no** `litellm`
dependency; it is pure Python + stdlib.

## File: `aegis/router/config.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os
import yaml

from aegis.router.exceptions import ConfigValidationError


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 2
    backoff_s: float = 1.0


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key: str                      # resolved from env; may be empty string
    base_url: Optional[str] = None    # None for providers with a hardcoded URL


@dataclass(frozen=True)
class AgentConfig:
    role: str
    model: str                        # LiteLLM model string, e.g. "anthropic/claude-sonnet-4-6"
    fallback: tuple[str, ...]         # ordered fallback model strings (tuple for hashability)
    timeout_s: float
    retry: RetryPolicy


@dataclass(frozen=True)
class RouterConfig:
    providers: dict[str, ProviderConfig]
    agents: dict[str, AgentConfig]    # keyed by role name

    @classmethod
    def from_yaml(cls, path: Path) -> RouterConfig:
        """Load and validate agents.yaml, resolving ${ENV_VAR} references.

        :param path: Path to the agents.yaml file.
        :return: Validated RouterConfig.
        :raises ConfigValidationError: if env vars are missing or provider
            references are undefined.
        """
        ...

    def agent_for_role(self, role: str) -> AgentConfig:
        """Return the AgentConfig for a role, raising KeyError with a helpful message.

        :param role: The role name (e.g. "primary_reasoning").
        :raises KeyError: if the role is not in the config, with a message
            naming available roles.
        """
        ...
```

## Implementation notes

- `${ENV_VAR}` resolution: scan all string values in `providers` for the
  `${...}` pattern; collect all missing var names first, then raise a single
  `ConfigValidationError` with the full list.
- `fallback` is stored as `tuple[str, ...]` (not `list`) so `AgentConfig`
  remains hashable (required for `frozen=True` dataclasses).
- Default field values for `AgentConfig` (when omitted from YAML):
  `fallback=()`, `timeout_s=30.0`, `retry=RetryPolicy()`.
- Provider cross-reference validation: after resolving env vars, verify each
  agent's model-string prefix matches a key in `providers`. Collect all
  violations before raising.

## Constraints

- **No `import litellm`** anywhere in this file.
- All dataclasses `frozen=True`.
- `from __future__ import annotations` at the top.
- `Optional[T]` from `typing`, never `T | None`.

## Success criteria

- [ ] `RetryPolicy`, `ProviderConfig`, `AgentConfig`, `RouterConfig` are all
      `frozen=True` dataclasses.
- [ ] `RouterConfig.from_yaml()` resolves `${ENV_VAR}` references.
- [ ] Missing env vars raise `ConfigValidationError` listing all missing names.
- [ ] Undefined provider references raise `ConfigValidationError`.
- [ ] `from_yaml()` is idempotent (two calls return equal objects).
- [ ] `agent_for_role()` raises `KeyError` with a message listing available roles.
- [ ] No `litellm` import.
