# 02 - Canonical exception hierarchy

**Parent task:** 05.0 Claude Code Events & Exceptions
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** none

## Objective

Implement `aegis_swr/claude_code/exceptions.py` — the **canonical** home for the
three exception types the Claude Code backend raises:

- `ClaudeCodeConfigError` — invalid `ClaudeCodeSettings` value
  (settings-shape / ambiguity fault, `ValueError` base).
- `ClaudeCodeUnavailableError` — the `claude` binary is missing, the one-shot
  subprocess cannot spawn, or the **startup auth-probe** finds the resolved
  credential unusable (a runtime capability failure, **including auth
  failures**, C7).
- `PermissionDeniedError` — a tool or `Bash` binary outside the allowlist was
  requested (analogous to OpenClaude's `PermissionDeniedError`).

This module is the canonical definition site. Tasks 02.0 / 03.0 / 04.0
forward-declared same-name placeholders so their code could raise before this
module existed; landing this subtask moves the canonical definitions here and
turns each placeholder into a re-export alias, with **zero downstream
import-path changes** — exactly the pattern Milestone 0004 Task 05.0 used to
canonicalise `OpenClaudeConfigError`. These types carry no `grpc` / client-library
import (C3) and no raw payload, credential, or token text in any message
(C7/C13).

## File: `aegis_swr/claude_code/exceptions.py`

```python
from __future__ import annotations

from typing import Optional


class ClaudeCodeConfigError(ValueError):
    """Raised when :class:`ClaudeCodeSettings` receives an invalid value.

    This is the **canonical** definition. Task 02.0 forward-declared an
    identical class in ``config.py`` (same ``ValueError`` base, same
    ``__init__(self, field: str, reason: str)`` signature, same formatted
    message) so its validators could raise before this module existed; Task 04.0
    reuses the same type for its ``auth_mode`` ambiguous-credential rejection.
    Landing this subtask moves the definition here and updates ``config.py`` to
    import and re-export it, so downstream imports of
    ``aegis_swr.claude_code.config.ClaudeCodeConfigError`` continue to resolve
    unchanged.

    Distinct from the router's ``ConfigValidationError`` (Milestone 0003) and
    from ``HarnessConfigError`` (Milestone 0005 Task 01.0): three different
    exceptions in three modules guarding three unrelated config surfaces. None
    subclasses another and none is interchangeable.

    :param field: Name of the offending settings field.
    :param reason: Human-readable, payload-free explanation of the violation.
        Must never contain a secret, credential, token, or incident-payload
        value (C7/C13).
    :ivar field: The offending field name.
    :ivar reason: The violation explanation.
    """

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"ClaudeCodeSettings.{field}: {reason}")


class ClaudeCodeUnavailableError(Exception):
    """Raised when the Claude Code backend cannot be used at runtime.

    Raised by ``process.py`` / ``tool.py`` when the ``claude`` binary is not
    found or the one-shot subprocess cannot spawn (C6), and by Task 04.0's
    **startup auth-probe** when the resolved credential is not actually usable
    (C7) — the auth-failure case. Signals that code-intelligence capability is
    unusable for this run; per C4 the caller reports the capability as
    unavailable rather than falling back — there is no other code backend.

    Kept strictly **distinct** from :class:`ClaudeCodeConfigError`: this is a
    runtime / health-check capability failure, not a settings-shape fault.
    Neither subclasses the other, so callers catch precisely the failure they
    mean (C7).

    :param message: Human-readable, payload-free description of the failure.
    :param binary: Configured binary name that could not be run, for
        diagnostics; configuration, never incident payload. ``None`` when not
        applicable.
    :param reason: For auth-probe failures, a short status string from the fixed
        vocabulary shared with :class:`ClaudeCodeAuthFailed`
        (``"ambiguous_credential"`` | ``"no_stored_login"`` |
        ``"token_rejected"``); ``None`` for non-auth failures. **Never** a
        credential, token, or credential-file path (C7/C13).
    :ivar binary: The unrunnable binary name, or ``None``.
    :ivar reason: The auth failure reason string, or ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        binary: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        self.binary = binary
        self.reason = reason
        super().__init__(message)


class PermissionDeniedError(Exception):
    """Raised when a tool/command outside the allowlist is requested.

    Claude Code runs non-interactively (C6) with ``--allowedTools`` and a
    non-bypassing ``permission_mode``. A request for a tool or ``Bash`` binary
    outside ``settings.allowed_tools`` is denied by ``tool.py``, which raises
    this error, emits :class:`aegis_swr.claude_code.events.ClaudeCodePermissionDenied`,
    and halts the invocation. It is **non-retriable by definition** (retrying
    cannot change an allowlist decision). Only the offending binary name is
    captured — never the full command line — so no incident payload leaks
    (C13). Analogous to OpenClaude's ``PermissionDeniedError``.

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
            f"Claude Code requested non-allowlisted command "
            f"'{denied_binary}' via tool '{tool}'; denied (non-retriable)."
        )
```

## File: `aegis_swr/claude_code/config.py` (re-export edit)

The placeholder `ClaudeCodeConfigError` class body defined in Task 02.0 subtask
01 is deleted and replaced with a re-export alias so the name keeps resolving
from `config.py`'s namespace:

```python
# Canonical definition lives in exceptions.py (Task 05.0); re-exported here so
# aegis_swr.claude_code.config.ClaudeCodeConfigError keeps resolving unchanged.
from aegis_swr.claude_code.exceptions import (
    ClaudeCodeConfigError as ClaudeCodeConfigError,
)
```

The `as ClaudeCodeConfigError` redundant-alias form marks the re-export as
intentional for `ruff`'s `F401`, matching how `openclaude/config.py` re-exports
`OpenClaudeConfigError`.

## Migration path (forward declaration → canonical)

Tasks 02.0, 03.0, and 04.0 forward-declared placeholders with the **exact**
signatures reproduced above so their code could raise before this module
existed. When this subtask lands:

1. Add the canonical `ClaudeCodeConfigError`, `ClaudeCodeUnavailableError`, and
   `PermissionDeniedError` here in `aegis_swr/claude_code/exceptions.py`.
2. In `aegis_swr/claude_code/config.py`, delete the local
   `ClaudeCodeConfigError` body and replace it with the re-export alias above
   (kept in `config.py`'s namespace so
   `aegis_swr.claude_code.config.ClaudeCodeConfigError` still resolves).
3. In `aegis_swr/claude_code/tool.py` and `aegis_swr/claude_code/process.py`
   (Task 03.0) and any Task 04.0 placeholder in `exceptions.py`, ensure
   `ClaudeCodeUnavailableError` (and, for 04.0, its `reason` keyword) resolves
   to this canonical class. Task 04.0's placeholder `exceptions.py` (the "auth
   errors" file it created) is **superseded** by this canonical module — its
   auth-error definitions merge into `ClaudeCodeUnavailableError`'s `reason`
   surface here.
4. No caller changes: any code that imported these names from `config.py`,
   `tool.py`, `process.py`, or `exceptions.py` continues to resolve the same
   class. The forward declarations and the canonical definitions are
   behaviourally identical (same base, same `__init__` signature, same formatted
   message), so every `except ClaudeCodeConfigError` / `except
   ClaudeCodeUnavailableError` / `except PermissionDeniedError` site is
   unaffected.

**Affected modules:** `aegis_swr/claude_code/exceptions.py` (new canonical),
`aegis_swr/claude_code/config.py` (re-export edit), and — as import-source only,
no signature change — `aegis_swr/claude_code/tool.py` / `process.py` (Task 03.0)
and any Task 04.0 auth-error placeholder. **No cross-service contract change:**
this is intra-package to `aegis_swr/claude_code/`; nothing in `aegis_swr/core/`,
`aegis_swr/views/`, `aegis_swr/code_intel/`, or the sibling `openclaude` /
`openhands` / `harness` backends is touched (C3). No downstream import path
changes.

## Implementation notes

- **Three independent hierarchies.** `ClaudeCodeUnavailableError` and
  `PermissionDeniedError` subclass `Exception`; `ClaudeCodeConfigError`
  subclasses `ValueError` (matching the Task 02.0 forward declaration and
  Pydantic's expectation that validator failures raise `ValueError`, which the
  `__init__` unwrap in `config.py` relies on). None subclasses another, so
  callers catch precisely the failure they mean — the C7 requirement that
  config-shape and runtime-capability faults never be conflated.
- **`ClaudeCodeUnavailableError` folds auth failures in via `reason`.** The
  auth-probe (Task 04.0) raises this error with `reason` drawn from the same
  fixed vocabulary as `ClaudeCodeAuthFailed.reason`
  (`"ambiguous_credential"` / `"no_stored_login"` / `"token_rejected"`), so the
  raised exception and the emitted event describe the same failure without ever
  carrying the credential. `binary` and `reason` are keyword-only to keep the
  common non-auth `ClaudeCodeUnavailableError("...")` call site clean.
- **`retriable = False`** on `PermissionDeniedError` because an allowlist denial
  is definitionally terminal; exposing it as a class attribute lets `tool.py`'s
  budget/retry path branch uniformly without `isinstance` ladders — identical to
  OpenClaude's `PermissionDeniedError`.
- **No payload, credential, or token in messages.** `ClaudeCodeConfigError`
  stores only field name and a fixed reason string; `ClaudeCodeUnavailableError`
  stores only the configured binary name and a fixed auth-reason string;
  `PermissionDeniedError` stores only the binary name (not the full command). No
  exception ever formats dump/log/stack/response/argv/credential text into its
  message (C7/C13).
- **Distinct from the router and the harness.** Explicitly not
  `ConfigValidationError` (Milestone 0003) and not `HarnessConfigError`
  (Task 01.0); the three config-error types coexist because they guard unrelated
  config surfaces and must be catchable separately.

## Constraints

- All new code uses `docs/dev/python_coding_standard.md`.
- `ruff` (`ruff.toml`) clean with zero new `# type: ignore`.
- Every new public class and function has an RST-style docstring (`:param:`/`:ivar:`/`:return:`).
- No `grpc`, client-library, `pydantic`, or sibling-backend import in this file — it is a leaf module that `config.py`, `process.py`, and `tool.py` all import from without creating a cycle (C3).
- `ruff check src/ tests/` - clean; every class has an RST-style docstring.
- No `Any` in any signature.

## Success criteria

- [ ] Three classes present: `ClaudeCodeConfigError`, `ClaudeCodeUnavailableError`, `PermissionDeniedError`.
- [ ] `ClaudeCodeConfigError` subclasses `ValueError`, stores `.field` and `.reason`, and produces the message `f"ClaudeCodeSettings.{field}: {reason}"` — identical to the Task 02.0 forward declaration.
- [ ] `aegis_swr/claude_code/config.py` re-exports `ClaudeCodeConfigError` from this module; `aegis_swr.claude_code.config.ClaudeCodeConfigError is aegis_swr.claude_code.exceptions.ClaudeCodeConfigError`.
- [ ] `ClaudeCodeUnavailableError` accepts optional keyword-only `binary` and `reason` and stores them; `reason` accepts only the fixed vocabulary shared with `ClaudeCodeAuthFailed` (documented, not enum-enforced).
- [ ] `PermissionDeniedError` has a class attribute `retriable == False` and stores `.tool` and `.denied_binary`.
- [ ] `ClaudeCodeConfigError` is **not** a subclass of the router's `ConfigValidationError` or of `HarnessConfigError`, and vice versa; `ClaudeCodeUnavailableError` does **not** subclass `ClaudeCodeConfigError`.
- [ ] No exception message can contain an incident payload, a credential, or a token (asserted by a unit test constructing each type).
- [ ] `ruff check src/ tests/` - clean; no `grpc` or client-library import pulled in by `import aegis_swr.claude_code.exceptions`.
