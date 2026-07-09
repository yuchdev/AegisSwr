"""Domain exceptions for the OpenClaude integration.

This module hosts the minimal exception hierarchy the gRPC client (Task 02.0)
needs before Task 05.0 canonicalises the full set. The definitions here are
deliberately plain subclasses with no exotic constructor signature, so the
richer 05.0 hierarchy can extend them without breaking imports.
"""

from __future__ import annotations

from typing import Optional


class OpenClaudeError(Exception):
    """Base class for all OpenClaude integration errors.

    Task 05.0 owns the canonical hierarchy; this forward declaration exists so
    Task 02.0's gRPC client can raise a stable, import-compatible base type.
    """


class OpenClaudeUnavailableError(OpenClaudeError):
    """Raised when the OpenClaude sidecar is unreachable or the stream fails.

    Signals a transport-level failure (channel ``UNAVAILABLE``, deadline
    exceeded, or a stream that ended without a terminal frame).

    The constructor is a forward-safe superset of the canonical Task 05.0
    signature ``(message, grpc_url=None)``: it keeps ``message`` positional and
    ``grpc_url`` as the first optional positional (so 05.0's call sites remain
    source-compatible), while adding the keyword-only ``retriable`` and
    ``status_code`` fields Task 02.0 subtask 04 needs to classify a gRPC status
    error. ``status_code`` carries only the gRPC status code name - never any
    response payload text (C9).

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
    ) -> None:
        self.grpc_url = grpc_url
        self.retriable = retriable
        self.status_code = status_code
        super().__init__(message)
