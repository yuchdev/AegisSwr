# 03 - exceptions.py - exception hierarchy

**Parent task:** 02.0 Router Foundation Types
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03.0, 04.0

## Objective

Implement `aegis/router/exceptions.py` - the three exception classes used
throughout the router module.

## File: `aegis/router/exceptions.py`

```python
from __future__ import annotations
from typing import Optional


class RouterException(Exception):
    """Wraps any provider or network error from LiteLLMClient.

    :param message: Human-readable description of the failure.
    :param cause: The underlying exception (set as __cause__ by the client).
    """


class ConfigValidationError(Exception):
    """Raised when agents.yaml fails validation.

    Used for: missing env vars, undefined provider references, malformed fields.
    The message always lists all violations at once, not just the first.
    """


class AllProvidersExhausted(RouterException):
    """Raised when every model in the primary + fallback chain has failed.

    :param role: The agent role that was being resolved.
    :param tried: Ordered list of model strings that were attempted.
    :param errors: Parallel list of error messages for each attempted model.
    """

    def __init__(self, role: str, tried: list[str], errors: list[str]) -> None:
        self.role = role
        self.tried = tried
        self.errors = errors
        super().__init__(
            f"All providers exhausted for role '{role}'. "
            f"Tried: {tried}. Errors: {errors}"
        )
```

## Design notes

- `AllProvidersExhausted` subclasses `RouterException` so callers can catch
  the full failure at either level of specificity.
- `ConfigValidationError` is a separate hierarchy (not under `RouterException`)
  because it represents a startup configuration problem, not a runtime call
  failure.
- `tried` and `errors` are plain lists (not tuples) on `AllProvidersExhausted`
  because they are built up incrementally during the retry/fallback loop.

## Constraints

- No `litellm` import.
- `from __future__ import annotations` at the top.

## Success criteria

- [ ] Three exception classes present: `RouterException`, `ConfigValidationError`,
      `AllProvidersExhausted`.
- [ ] `AllProvidersExhausted` stores `.role`, `.tried`, `.errors` as instance
      attributes.
- [ ] `AllProvidersExhausted` is a subclass of `RouterException`.
- [ ] `ConfigValidationError` is **not** a subclass of `RouterException`.
