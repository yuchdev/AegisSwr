# 02 - Three exception types

**Parent task:** 05.0 Event Types & Exceptions
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03.0, 04.0

## Objective

Implement `aegis/openclaude/exceptions.py` - the three exception types the
OpenClaude module raises: `OpenClaudeUnavailableError` (unreachable backend /
gRPC `UNAVAILABLE`/`DEADLINE_EXCEEDED`), `PermissionDeniedError` (a
non-allowlisted `PERMISSION_REQ`), and `OpenClaudeConfigError` (invalid
settings). This module is the **canonical home** for `OpenClaudeConfigError`,
which Task 01.0 forward-declared in `config.py`; landing this task moves the
definition here and turns `config.py`'s copy into a re-export, with zero
downstream import-path changes. These types carry no `grpc`/`litellm` import
(C3) and no raw payload text in any message (C9).

## File: `aegis/openclaude/exceptions.py`

```python
from __future__ import annotations

from typing import Optional


class OpenClaudeUnavailableError(Exception):
    """Raised when the OpenClaude gRPC backend cannot be reached.

    Raised by ``process.py`` when a health check fails or a managed subprocess
    never opens its port (C6), and by ``grpc/client.py`` on a channel-level
    ``UNAVAILABLE`` or ``DEADLINE_EXCEEDED`` status (C2). Signals that
    code-intelligence capability is unusable for this run; per C4 the caller
    reports the capability as unavailable rather than falling back - there is no
    other code backend.

    :param message: Human-readable, payload-free description of the failure.
    :param grpc_url: Host[:port] that could not be reached, for diagnostics;
        configuration, never incident payload. ``None`` when not yet known.
    :ivar grpc_url: The unreachable endpoint, or ``None``.
    """

    def __init__(self, message: str, grpc_url: Optional[str] = None):
        self.grpc_url = grpc_url
        super().__init__(message)


class PermissionDeniedError(Exception):
    """Raised on a ``PERMISSION_REQ`` frame for a non-allowlisted command.

    OpenClaude runs non-interactively (C2). A permission request for a tool or
    ``Bash`` binary outside ``settings.allowed_tools`` /
    ``settings.bash_allowlist`` is denied by ``tool.py`` (via the gRPC client),
    which raises this error, emits :class:`OpenClaudePermissionDenied`, and halts
    the invocation. It is **non-retriable by definition** (C7): retrying cannot
    change an allowlist decision. Only the offending binary name is captured -
    never the full command line - so no incident payload leaks (C9).

    :param tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :param denied_binary: Binary name requested but not allowlisted.
    :ivar retriable: Always ``False``; present so retry logic can branch on it
        uniformly with retriable failure types.
    :ivar tool: The requesting tool name.
    :ivar denied_binary: The denied binary name.
    """

    retriable: bool = False

    def __init__(self, tool: str, denied_binary: str):
        self.tool = tool
        self.denied_binary = denied_binary
        super().__init__(
            f"OpenClaude requested non-allowlisted command "
            f"'{denied_binary}' via tool '{tool}'; denied (non-retriable)."
        )


class OpenClaudeConfigError(ValueError):
    """Raised when :class:`OpenClaudeSettings` receives an invalid value.

    This is the **canonical** definition. Task 01.0 forward-declared an
    identical class in ``config.py`` (same base, same ``field``/``reason``
    signature, same formatted message) so it could raise before this module
    existed; this task moves the definition here and updates ``config.py`` to
    import and re-export it, so downstream imports of
    ``aegis.openclaude.config.OpenClaudeConfigError`` continue to resolve
    unchanged.

    Distinct from the router's ``ConfigValidationError`` (Milestone 0003,
    ``aegis/router/exceptions.py``): a different exception in a different module
    for a different failure domain (router ``agents.yaml`` validation vs
    OpenClaude environment settings). The two are never interchangeable and
    neither subclasses the other.

    :param field: Name of the offending settings field.
    :param reason: Human-readable, payload-free explanation of the violation.
    :ivar field: The offending field name.
    :ivar reason: The violation explanation.
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"OpenClaudeSettings.{field}: {reason}")
```

## Migration path (Task 01.0 forward declaration → canonical)

Task 01.0 subtask 01 defined `OpenClaudeConfigError` locally in
`aegis/openclaude/config.py` with the exact signature reproduced above
(`ValueError` base, `__init__(self, field: str, reason: str)`, message
`f"OpenClaudeSettings.{field}: {reason}"`). When this subtask lands:

1. Add the canonical class here in `aegis/openclaude/exceptions.py`.
2. In `aegis/openclaude/config.py`, delete the local class body and replace it
   with a re-export:
   `from aegis.openclaude.exceptions import OpenClaudeConfigError` (kept in
   `config.py`'s namespace so `aegis.openclaude.config.OpenClaudeConfigError`
   still resolves).
3. No caller changes: any code that imported `OpenClaudeConfigError` from
   either `config.py` or `exceptions.py` continues to resolve the same class.
   The forward declaration and the canonical definition are behaviourally
   identical, so `except OpenClaudeConfigError` sites are unaffected.

**Affected modules:** `aegis/openclaude/config.py` (re-export edit here),
`aegis/openclaude/exceptions.py` (new). No other backend or module imports
change. This is intra-module to `aegis/openclaude/`; no cross-service contract
change and nothing in `aegis/core/`, `aegis/ui/`, or `aegis/code_intel/` is
touched (C3).

## Design notes

- **Three independent hierarchies.** `OpenClaudeUnavailableError` and
  `PermissionDeniedError` subclass `Exception`; `OpenClaudeConfigError`
  subclasses `ValueError` (matching the Task 01.0 forward declaration and
  Pydantic's expectation that validator failures raise `ValueError`). None
  subclasses another, so callers catch precisely the failure they mean.
- **`retriable = False`** is a class attribute on `PermissionDeniedError`
  because an allowlist denial is definitionally terminal (C7); exposing it lets
  the `tool.py` budget/retry path branch uniformly without `isinstance`
  ladders.
- **No payload in messages.** `OpenClaudeUnavailableError` stores only
  `grpc_url` (configuration); `PermissionDeniedError` stores only the binary
  name (not the full command); `OpenClaudeConfigError` stores only field name
  and a fixed reason string. No exception ever formats dump/log/stack/response
  text into its message (C9).
- **Distinct from the router.** Explicitly not `ConfigValidationError`; the two
  configuration-error types coexist because they guard unrelated config
  surfaces and must be catchable separately.

## Constraints

- `from __future__ import annotations` at the top; `Optional[T]` from `typing`,
  never `T | None` (C9).
- No `grpc`, `litellm`, or `pydantic` import in this file - it is a leaf module
  that `config.py`, `process.py`, `grpc/client.py`, and `tool.py` all import
  from without creating a cycle.
- `ruff check src/ tests/` - clean; every class
  has an RST-style docstring.
- No `Any` in any signature.

## Success criteria

- [ ] Three classes present: `OpenClaudeUnavailableError`,
      `PermissionDeniedError`, `OpenClaudeConfigError`.
- [ ] `PermissionDeniedError` has a class attribute `retriable` equal to
      `False` and stores `.tool` and `.denied_binary`.
- [ ] `OpenClaudeConfigError` subclasses `ValueError`, stores `.field` and
      `.reason`, and produces the message `f"OpenClaudeSettings.{field}: {reason}"`
      - identical to the Task 01.0 forward declaration.
- [ ] `aegis/openclaude/config.py` re-exports `OpenClaudeConfigError` from this
      module; `aegis.openclaude.config.OpenClaudeConfigError is
      aegis.openclaude.exceptions.OpenClaudeConfigError`.
- [ ] `OpenClaudeConfigError` is **not** a subclass of the router's
      `ConfigValidationError`, and vice versa.
- [ ] `OpenClaudeUnavailableError` accepts an optional `grpc_url` and stores it.
- [ ] No exception message can contain incident payload (asserted by a unit
      test constructing each type).
- [ ] `ruff check src/ tests/` - clean; no `grpc`
      import pulled in by `import aegis.openclaude.exceptions`.
