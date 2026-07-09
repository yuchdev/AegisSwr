"""Public API for the OpenClaude integration package.

Re-exports the payload-free, ``grpc``-free event and exception types so callers
can ``from aegis_swr.openclaude import OpenClaudeStreamCompleted`` without a full
module path — mirroring ``from aegis_swr.router import RouterCallCompleted``.

Registration of the ``openclaude.*`` events with the
:class:`~aegis_swr.core.events.EventBus` is implicit: the bus distributes any
:class:`~aegis_swr.core.events.DomainEvent` subclass and subscribers filter on
the ``event_type`` sentinel, so there is no imperative ``bus.register(...)`` call
and :mod:`aegis_swr.core.events` is left untouched (contract C8).

``OpenClaudeTool``, ``OpenClaudeProcess``, and ``OpenClaudeGrpcClient`` are
deliberately **not** re-exported here: importing them at package-import time
would pull ``grpc`` into the package namespace and break the C3 isolation
boundary. Those classes stay behind their submodules and are constructed at the
``app.py`` composition root.
"""

from __future__ import annotations

from aegis_swr.openclaude.events import (
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
)
from aegis_swr.openclaude.exceptions import (
    OpenClaudeConfigError,
    OpenClaudeUnavailableError,
    PermissionDeniedError,
)

__all__ = [
    # events (C8 taxonomy)
    "OpenClaudeConnected",
    "OpenClaudeDisconnected",
    "OpenClaudeToolCall",
    "OpenClaudeToolResult",
    "OpenClaudePermissionDenied",
    "OpenClaudeStreamCompleted",
    "OpenClaudeStreamError",
    # exceptions
    "OpenClaudeUnavailableError",
    "PermissionDeniedError",
    "OpenClaudeConfigError",
]
