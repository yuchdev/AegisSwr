# 04 - Package `__init__.py`

**Parent task:** 02.0 Router Foundation Types
**State:** ⬜ Not started
**Depends on:** 01, 02, 03
**Blocks:** -

## Objective

Create `aegis/router/__init__.py` with a clean public API that re-exports the
types most commonly needed by callers: `ModelRouter`, `RouterConfig`, the four
event classes, and the three exception classes. This lets callers write
`from aegis.router import ModelRouter` instead of the full module path.

## File: `aegis/router/__init__.py`

```python
from __future__ import annotations

# Public API - import order follows dependency order
from aegis.router.exceptions import (
    AllProvidersExhausted,
    ConfigValidationError,
    RouterException,
)
from aegis.router.events import (
    RouterCallCompleted,
    RouterCallFailed,
    RouterCallStarted,
    RouterFallbackUsed,
)
from aegis.router.config import (
    AgentConfig,
    ProviderConfig,
    RetryPolicy,
    RouterConfig,
)

# ModelRouter imported last (depends on all of the above)
from aegis.router.router import ModelRouter

__all__ = [
    "ModelRouter",
    "RouterConfig",
    "AgentConfig",
    "ProviderConfig",
    "RetryPolicy",
    "RouterCallStarted",
    "RouterCallCompleted",
    "RouterCallFailed",
    "RouterFallbackUsed",
    "RouterException",
    "ConfigValidationError",
    "AllProvidersExhausted",
]
```

## Constraints

- `LiteLLMClient` is **not** re-exported here - it is an internal
  implementation detail of `aegis/router/client.py`.
- No `import litellm` in this file.
- The import of `ModelRouter` must come **last** to avoid circular imports
  (router.py imports from config, events, exceptions, and client).

## Success criteria

- [ ] `from aegis.router import ModelRouter` resolves.
- [ ] `from aegis.router import RouterConfig, RouterCallCompleted` resolves.
- [ ] `from aegis.router import AllProvidersExhausted` resolves.
- [ ] `LiteLLMClient` is **not** in `__all__` or directly importable from
      `aegis.router`.
- [ ] `python -c "import aegis.router; print('ok')"` succeeds.
