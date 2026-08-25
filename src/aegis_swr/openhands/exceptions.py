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
