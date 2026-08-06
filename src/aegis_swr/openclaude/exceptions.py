"""Domain exceptions for the OpenClaude integration.

This module is the canonical home for the three exception types the OpenClaude
module raises: :class:`OpenClaudeUnavailableError` (unreachable backend / gRPC
``UNAVAILABLE``/``DEADLINE_EXCEEDED``), :class:`PermissionDeniedError` (a
non-allowlisted ``PERMISSION_REQ``), and :class:`OpenClaudeConfigError` (invalid
settings). They form three independent hierarchies - none subclasses another -
so callers catch precisely the failure they mean.

This is a leaf module: it imports nothing from ``aegis_swr.openclaude`` (or
``grpc``/``litellm``/``pydantic``), so ``config.py``, ``process.py``,
``grpc/client.py``, and ``tool.py`` can all import from it without a cycle. No
exception message ever formats dump/log/stack/response text (C9).
"""

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

    The constructor is a superset of the spec's narrower ``(message,
    grpc_url=None)`` signature: it keeps ``message`` positional and ``grpc_url``
    as the first optional positional (source-compatible with the spec), while
    adding the keyword-only ``retriable`` and ``status_code`` fields that
    ``grpc/client.py`` uses to classify a gRPC status error. ``status_code``
    carries only the gRPC status code name - never any response payload (C9).

    :param message: Human-readable, payload-free description of the failure.
    :param grpc_url: Host[:port] that could not be reached, for diagnostics;
        configuration, never incident payload. ``None`` when not yet known.
    :param retriable: Whether the caller may retry the operation. ``UNAVAILABLE``
        and ``DEADLINE_EXCEEDED`` are retriable transport failures; any other
        status code is non-retriable.
    :param status_code: The originating gRPC status code name (e.g.
        ``"UNAVAILABLE"``), or ``None`` when the failure carries no status code.
    :ivar grpc_url: The unreachable endpoint, or ``None``.
    :ivar retriable: Whether the operation may be retried.
    :ivar status_code: The originating gRPC status code name, or ``None``.
    """

    def __init__(
        self,
        message: str,
        grpc_url: Optional[str] = None,
        *,
        retriable: bool = True,
        status_code: Optional[str] = None,
    ):
        """Record the endpoint, retriability, and gRPC status on the error."""
        self.grpc_url = grpc_url
        self.retriable = retriable
        self.status_code = status_code
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
        """Record the requesting *tool* and the denied *binary* name (payload-free)."""
        self.tool = tool
        self.denied_binary = denied_binary
        super().__init__(
            f"OpenClaude requested non-allowlisted command '{denied_binary}' via tool '{tool}'; denied (non-retriable)."
        )


class OpenClaudeConfigError(ValueError):
    """Raised when :class:`OpenClaudeSettings` receives an invalid value.

    This is the **canonical** definition. Task 01.0 forward-declared an
    identical class in ``config.py`` (same base, same ``field``/``reason``
    signature, same formatted message) so it could raise before this module
    existed; this task moves the definition here and updates ``config.py`` to
    import and re-export it, so downstream imports of
    ``aegis_swr.openclaude.config.OpenClaudeConfigError`` continue to resolve
    unchanged.

    Distinct from the router's ``ConfigValidationError`` (Milestone 0003,
    ``aegis_swr/router/exceptions.py``): a different exception in a different
    module for a different failure domain (router ``agents.yaml`` validation vs
    OpenClaude environment settings). The two are never interchangeable and
    neither subclasses the other.

    :param field: Name of the offending settings field.
    :param reason: Human-readable, payload-free explanation of the violation.
    :ivar field: The offending field name.
    :ivar reason: The violation explanation.
    """

    def __init__(self, field: str, reason: str):
        """Record the offending *field* and payload-free *reason* on the error."""
        self.field = field
        self.reason = reason
        super().__init__(f"OpenClaudeSettings.{field}: {reason}")
