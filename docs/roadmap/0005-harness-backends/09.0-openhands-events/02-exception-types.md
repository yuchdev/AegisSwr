# 02 - Canonical OpenHands exception hierarchy

**Parent task:** 09.0 OpenHands Events & Exceptions
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 07.0, 08.0

## Objective

Implement `aegis_swr/openhands/exceptions.py` — the **canonical home** for the
three exception types the OpenHands module raises: `OpenHandsConfigError`
(invalid `OpenHandsSettings`, raised by `config.py`), `OpenHandsUnavailableError`
(unreachable sidecar / failed health-check / REST/WS transport failure, raised by
`process.py` and `client.py`), and `PermissionDeniedError` (a non-allowlisted
sandbox action, raised by `tool.py`). They form three independent hierarchies —
none subclasses another — so callers catch precisely the failure they mean. No
exception message ever formats dump/log/stack/observation/credential text (C13).

**This is the canonical definition; it replaces the placeholder forward
declarations.** Following the exact pattern 0004's task 05.0 used to
canonicalise `OpenClaudeConfigError` (which task 01.0 had forward-declared in
`config.py`), earlier OpenHands-track tasks that need to raise before this module
exists — Task 06.0 (`config.py`, for `OpenHandsConfigError`) and Task 07.0
(`process.py`/`client.py`, for `OpenHandsUnavailableError`), and possibly Task
08.0 (`tool.py`, for `PermissionDeniedError`) — forward-declare an **identical**
class locally (same base, same `__init__` signature, same formatted message).
When this subtask lands, those local bodies are deleted and replaced with a
re-export of the canonical class from this module, so downstream imports of
`aegis_swr.openhands.config.OpenHandsConfigError` (etc.) continue to resolve
**unchanged**. See "Migration path" below.

## File: `aegis_swr/openhands/exceptions.py`

```python
"""Domain exceptions for the OpenHands integration.

Canonical home for the three exception types the OpenHands module raises:
:class:`OpenHandsConfigError` (invalid ``OpenHandsSettings``),
:class:`OpenHandsUnavailableError` (unreachable sidecar / failed health-check /
REST/WS transport failure), and :class:`PermissionDeniedError` (a non-allowlisted
sandbox action). They form three independent hierarchies — none subclasses
another — so callers catch precisely the failure they mean.

This is a leaf module: it imports nothing from ``aegis_swr.openhands`` (nor the
OpenHands client library, ``grpc``, ``httpx``, ``websockets``, or ``pydantic``),
so ``config.py``, ``process.py``, ``client.py``, and ``tool.py`` can all import
from it without a cycle. No exception message ever formats
dump/log/stack/observation/credential text (C13).
"""

from __future__ import annotations

from typing import Optional


class OpenHandsUnavailableError(Exception):
    """Raised when the OpenHands sidecar cannot be reached or used.

    Raised by ``process.py`` when a health check fails or a managed sidecar
    never becomes ready (C8), and by ``client.py`` on a REST/WS transport
    failure or a terminal server error status (C8). Signals that
    code-intelligence capability is unusable for this run; per C4 the harness
    reports the capability as unavailable rather than falling back — there is no
    sibling backend to fall through to. This is also the error the harness
    raises when OpenHands is the explicitly-selected backend but its presence
    signal is absent at composition/health-check time (plan.md C2).

    :param message: Human-readable, payload-free description of the failure.
    :param server_url: ``host[:port]`` that could not be reached, for
        diagnostics; configuration, never incident payload. ``None`` when not
        yet known.
    :param retriable: Whether the caller may retry the operation. Transient
        transport failures (connection refused, timeout) are retriable; a
        rejected/unusable server is not.
    :param status_code: The originating HTTP/WS status code name (e.g.
        ``"UNAVAILABLE"`` or ``"503"``), or ``None`` when the failure carries no
        status code. Never carries a response body (C13).
    :ivar server_url: The unreachable endpoint, or ``None``.
    :ivar retriable: Whether the operation may be retried.
    :ivar status_code: The originating status code name, or ``None``.
    """

    def __init__(
        self,
        message: str,
        server_url: Optional[str] = None,
        *,
        retriable: bool = True,
        status_code: Optional[str] = None,
    ):
        """Record the endpoint, retriability, and status code on the error."""
        self.server_url = server_url
        self.retriable = retriable
        self.status_code = status_code
        super().__init__(message)


class PermissionDeniedError(Exception):
    """Raised when a sandbox action requests a non-allowlisted command.

    OpenHands runs non-interactively inside a Docker sandbox (C8). An action
    requesting a binary or operation outside ``settings.allowed_tools`` is denied
    by ``tool.py``, which raises this error, emits
    :class:`~aegis_swr.openhands.events.OpenHandsPermissionDenied`, and halts the
    invocation. It is **non-retriable by definition**: retrying cannot change an
    allowlist decision. Only the offending binary name is captured — never the
    full command line — so no incident payload leaks (C13).

    Analogous to OpenClaude's ``PermissionDeniedError``
    (``aegis_swr.openclaude.exceptions``): a same-named, same-shaped type in a
    sibling backend package. The two are **distinct classes** and neither
    subclasses the other; callers import the one for the backend they mean.

    :param action: OpenHands action kind that issued the request, e.g. ``"run"``.
    :param denied_binary: Binary name requested but not allowlisted.
    :ivar retriable: Always ``False``; present so retry logic can branch on it
        uniformly with retriable failure types.
    :ivar action: The requesting action kind.
    :ivar denied_binary: The denied binary name.
    """

    retriable: bool = False

    def __init__(self, action: str, denied_binary: str):
        """Record the requesting *action* and denied *binary* name (payload-free)."""
        self.action = action
        self.denied_binary = denied_binary
        super().__init__(
            f"OpenHands requested non-allowlisted command "
            f"'{denied_binary}' via action '{action}'; denied (non-retriable)."
        )


class OpenHandsConfigError(ValueError):
    """Raised when :class:`OpenHandsSettings` receives an invalid value.

    This is the **canonical** definition. Task 06.0 forward-declared an
    identical class in ``config.py`` (same base, same ``field``/``reason``
    signature, same formatted message) so it could raise before this module
    existed; landing this task moves the definition here and updates
    ``config.py`` to import and re-export it, so downstream imports of
    ``aegis_swr.openhands.config.OpenHandsConfigError`` continue to resolve
    unchanged.

    Subclasses ``ValueError`` so a Pydantic ``field_validator`` in
    ``OpenHandsSettings`` may raise it directly and ``__init__`` can unwrap it
    from Pydantic's ``ValidationError`` (the OpenClaude settings convention, C5).

    Distinct from the harness's ``HarnessConfigError`` (plan.md C2,
    ``aegis_swr/harness/exceptions.py``) and from the router's
    ``ConfigValidationError`` (Milestone 0003): different exceptions in different
    modules for different failure domains (per-backend settings vs harness
    selection ambiguity vs router ``agents.yaml`` validation). None subclasses
    another and none is interchangeable.

    :param field: Name of the offending settings field.
    :param reason: Human-readable, payload-free explanation of the violation.
    :ivar field: The offending field name.
    :ivar reason: The violation explanation.
    """

    def __init__(self, field: str, reason: str):
        """Record the offending *field* and payload-free *reason* on the error."""
        self.field = field
        self.reason = reason
        super().__init__(f"OpenHandsSettings.{field}: {reason}")
```

## Migration path (Tasks 06.0/07.0/08.0 forward declarations → canonical)

Mirrors 0004's task 05.0 canonicalisation of `OpenClaudeConfigError` exactly:
the forward declaration and the canonical definition are behaviourally identical,
so `except OpenHands*` sites are unaffected and no caller import path changes.

1. **`OpenHandsConfigError`** — Task 06.0 defines it locally in
   `aegis_swr/openhands/config.py` with the exact signature reproduced above
   (`ValueError` base, `__init__(self, field: str, reason: str)`, message
   `f"OpenHandsSettings.{field}: {reason}"`). When this subtask lands: add the
   canonical class here; in `config.py` delete the local body and replace it with
   `from aegis_swr.openhands.exceptions import OpenHandsConfigError` (kept in
   `config.py`'s namespace so `aegis_swr.openhands.config.OpenHandsConfigError`
   still resolves).
2. **`OpenHandsUnavailableError`** — if Task 07.0 (`process.py`/`client.py`)
   forward-declares it before this task lands, it uses the identical
   `(message, server_url=None, *, retriable=True, status_code=None)` signature;
   canonicalising here replaces that local body with a re-export the same way.
3. **`PermissionDeniedError`** — Task 08.0 (`tool.py`) raises it; if 08.0 lands
   first it forward-declares the identical `(action, denied_binary)` shape and is
   re-pointed at this module on canonicalisation. If this task lands first (its
   only hard dependency is Task 06.0), 08.0 simply imports the canonical class
   and no forward declaration is ever needed.

**Affected modules:** `aegis_swr/openhands/config.py`,
`aegis_swr/openhands/process.py`, `aegis_swr/openhands/client.py`,
`aegis_swr/openhands/tool.py` (each: a re-export edit iff it forward-declared),
`aegis_swr/openhands/exceptions.py` (new, canonical). No other backend or module
import changes. This is intra-module to `aegis_swr/openhands/`; **no
cross-service contract change** and nothing in `aegis_swr/core/`,
`aegis_swr/views/`, `aegis_swr/code_intel/`, or the sibling `openclaude` /
`claude_code` / `harness` packages is touched (C3).

## Implementation notes

- **Three independent hierarchies.** `OpenHandsUnavailableError` and
  `PermissionDeniedError` subclass `Exception`; `OpenHandsConfigError` subclasses
  `ValueError` (so a Pydantic validator can raise it and `__init__` can unwrap it
  from `ValidationError`, C5). None subclasses another, so callers catch
  precisely the failure they mean.
- **`retriable` on both non-config errors.** `PermissionDeniedError.retriable`
  is a class attribute `False` (an allowlist denial is terminal);
  `OpenHandsUnavailableError.retriable` is an instance flag the `client.py`/
  `tool.py` retry path branches on uniformly, without `isinstance` ladders.
  Mirrors the shipped `OpenClaudeUnavailableError` superset shape.
- **No payload in messages.** `OpenHandsUnavailableError` stores only
  `server_url` and `status_code` (configuration/status, never a response body);
  `PermissionDeniedError` stores only the binary name (not the full command);
  `OpenHandsConfigError` stores only field name and a fixed reason string. No
  exception ever formats dump/log/stack/observation/credential text (C13).
- **Analogous, not shared, `PermissionDeniedError`.** The same-named type exists
  in `aegis_swr.openclaude.exceptions`; they are deliberately **not** unified
  into a shared base — that would force one backend package to import another and
  break the C3 isolation posture. Each backend owns its own copy; the OpenHands
  one keys on `action` (OpenHands' action kind) rather than OpenClaude's `tool`.
- **Distinct from `HarnessConfigError`.** The harness's selection-ambiguity error
  (C2) is a *different* configuration failure at a *different* layer (which
  backend to run) and is never interchangeable with a per-backend settings error
  (how this backend is configured). Neither subclasses the other.

## Constraints

- `from __future__ import annotations` at the top; `Optional[T]` from `typing`,
  never `T | None`.
- No OpenHands client library, `grpc`, `httpx`, `websockets`, or `pydantic`
  import in this file — it is a leaf module that `config.py`, `process.py`,
  `client.py`, and `tool.py` all import from without creating a cycle (C3).
- No `Any` in any signature.
- `ruff` and `python scripts/replace_optional.py --check` clean; every class has
  an RST-style docstring.

## Success criteria

- [ ] Three classes present: `OpenHandsUnavailableError`,
      `PermissionDeniedError`, `OpenHandsConfigError`.
- [ ] `OpenHandsUnavailableError` accepts an optional `server_url` and the
      keyword-only `retriable`/`status_code`, and stores all three.
- [ ] `PermissionDeniedError` has a class attribute `retriable` equal to `False`
      and stores `.action` and `.denied_binary`.
- [ ] `OpenHandsConfigError` subclasses `ValueError`, stores `.field` and
      `.reason`, and produces the message
      `f"OpenHandsSettings.{field}: {reason}"` — identical to the Task 06.0
      forward declaration.
- [ ] Any module that forward-declared one of these (Task 06.0 `config.py`, and
      07.0/08.0 if applicable) re-exports it from this module;
      `aegis_swr.openhands.config.OpenHandsConfigError is
      aegis_swr.openhands.exceptions.OpenHandsConfigError`.
- [ ] `OpenHandsConfigError` is **not** a subclass of `HarnessConfigError` or the
      router's `ConfigValidationError`, and vice versa.
- [ ] OpenHands' `PermissionDeniedError` is a distinct class from OpenClaude's;
      neither subclasses the other.
- [ ] No exception message can contain incident payload, observation text, or a
      credential (asserted by a unit test constructing each type).
- [ ] `ruff` and `python scripts/replace_optional.py --check` clean; no OpenHands
      client library, `grpc`, `httpx`, or `websockets` import pulled in by
      `import aegis_swr.openhands.exceptions`.
