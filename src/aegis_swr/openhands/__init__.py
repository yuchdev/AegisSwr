"""Public API for the OpenHands backend integration package.

Re-exports the payload-free, dependency-free event and exception types so callers
can ``from aegis_swr.openhands import OpenHandsCompleted`` without a full module
path - mirroring :mod:`aegis_swr.openclaude` and :mod:`aegis_swr.claude_code`.

Registration of the ``openhands.*`` events with the
:class:`~aegis_swr.core.events.EventBus` is implicit: the bus distributes any
:class:`~aegis_swr.core.events.DomainEvent` subclass and subscribers filter on
the ``event_type`` sentinel, so there is no imperative ``bus.register(...)`` call
and :mod:`aegis_swr.core.events` is left untouched (contract C10).

:class:`~aegis_swr.openhands.config.OpenHandsSettings` is deliberately **not**
re-exported here: importing it at package-import time would pull ``pydantic`` /
``pydantic_settings`` into the package namespace. Likewise ``OpenHandsProcess``,
``OpenHandsClient``, and ``OpenHandsTool`` (later tasks) are never re-exported so
importing this package never pulls the OpenHands HTTP/WS client library into the
namespace (contract C3 isolation boundary). The event/exception modules
re-exported here are dependency-free leaf modules (no ``pydantic``, no client
library).
"""

from __future__ import annotations

from aegis_swr.openhands.events import (
    OpenHandsAction,
    OpenHandsCompleted,
    OpenHandsConnected,
    OpenHandsDisconnected,
    OpenHandsError,
    OpenHandsObservation,
    OpenHandsPermissionDenied,
)
from aegis_swr.openhands.exceptions import (
    OpenHandsConfigError,
    OpenHandsUnavailableError,
    PermissionDeniedError,
)

__all__ = [
    # events (C10 taxonomy)
    "OpenHandsConnected",
    "OpenHandsDisconnected",
    "OpenHandsAction",
    "OpenHandsObservation",
    "OpenHandsPermissionDenied",
    "OpenHandsCompleted",
    "OpenHandsError",
    # exceptions
    "OpenHandsConfigError",
    "OpenHandsUnavailableError",
    "PermissionDeniedError",
]
