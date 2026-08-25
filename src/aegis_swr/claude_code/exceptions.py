"""Domain exceptions for the Claude Code backend.

This module is the **canonical** home for the three exception types the Claude
Code backend raises: :class:`ClaudeCodeConfigError` (invalid
:class:`~aegis_swr.claude_code.config.ClaudeCodeSettings` value, ``ValueError``
base), :class:`ClaudeCodeUnavailableError` (a runtime capability failure - the
``claude`` binary is missing, the one-shot subprocess cannot spawn, or the
startup auth-probe finds the resolved credential unusable, C7), and
:class:`PermissionDeniedError` (a non-allowlisted tool/command request). They
form three independent hierarchies - none subclasses another - so callers catch
precisely the failure they mean (C7).

This is a leaf module: it imports nothing from ``aegis_swr.claude_code`` (or
``grpc``/``pydantic``/any client library), so ``config.py``, ``process.py``, and
``tool.py`` can all import from it without a cycle (C3). No exception message
ever formats dump/log/stack/response/argv/credential text (C7/C13).
"""

from __future__ import annotations

from typing import Optional


class ClaudeCodeConfigError(ValueError):
    """Raised when :class:`ClaudeCodeSettings` receives an invalid value.

    This is the **canonical** definition. Task 02.0 forward-declared an
    identical class in ``config.py`` (same ``ValueError`` base, same
    ``__init__(self, field, reason)`` signature, same formatted message) so its
    validators could raise before this module existed; Task 04.0 reuses the same
    type for its ``auth_mode`` ambiguous-credential rejection. Landing Task 05.0
    moves the definition here and updates ``config.py`` to import and re-export
    it, so downstream imports of
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
        """Record the offending *field* and payload-free *reason* on the error."""
        self.field = field
        self.reason = reason
        super().__init__(f"ClaudeCodeSettings.{field}: {reason}")


class ClaudeCodeUnavailableError(Exception):
    """Raised when the Claude Code backend cannot be used at runtime.

    Raised by ``process.py`` / ``tool.py`` when the ``claude`` binary is not
    found or the one-shot subprocess cannot spawn (C6), and by Task 04.0's
    **startup auth-probe** when the resolved credential is not actually usable
    (C7) - the auth-failure case. Signals that code-intelligence capability is
    unusable for this run; per C4 the caller reports the capability as
    unavailable rather than falling back - there is no other code backend.

    Kept strictly **distinct** from :class:`ClaudeCodeConfigError`: this is a
    runtime / health-check capability failure, not a settings-shape fault.
    Neither subclasses the other, so callers catch precisely the failure they
    mean (C7).

    :param message: Human-readable, payload-free description of the failure.
    :param binary: Configured binary name that could not be run, for
        diagnostics; configuration, never incident payload. ``None`` when not
        applicable.
    :param reason: For auth-probe failures, a short status string from the fixed
        vocabulary shared with
        :class:`aegis_swr.claude_code.events.ClaudeCodeAuthFailed`
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
        """Record the configured *binary* and payload-free auth *reason* on the error."""
        self.binary = binary
        self.reason = reason
        super().__init__(message)


class PermissionDeniedError(Exception):
    """Raised when a tool/command outside the allowlist is requested.

    Claude Code runs non-interactively (C6) with ``--allowedTools`` and a
    non-bypassing ``permission_mode``. A request for a tool or ``Bash`` binary
    outside ``settings.allowed_tools`` is denied by ``tool.py``, which raises
    this error, emits
    :class:`aegis_swr.claude_code.events.ClaudeCodePermissionDenied`, and halts
    the invocation. It is **non-retriable by definition** (retrying cannot
    change an allowlist decision). Only the offending binary name is captured -
    never the full command line - so no incident payload leaks (C13). Analogous
    to OpenClaude's ``PermissionDeniedError``.

    :param tool: Claude Code tool that issued the request, e.g. ``"Bash"``.
    :param denied_binary: Binary name requested but not allowlisted.
    :ivar retriable: Always ``False``; present so retry logic can branch on it
        uniformly with retriable failure types.
    :ivar tool: The requesting tool name.
    :ivar denied_binary: The denied binary name.
    """

    retriable: bool = False

    def __init__(self, tool: str, denied_binary: str):
        """Record the requesting *tool* and the denied *binary* name (payload-free)."""
        self.tool = tool
        self.denied_binary = denied_binary
        super().__init__(
            f"Claude Code requested non-allowlisted command "
            f"'{denied_binary}' via tool '{tool}'; denied (non-retriable)."
        )
