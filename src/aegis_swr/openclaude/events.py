"""Forward declaration of OpenClaude lifecycle events (owned by Task 05.0).

This module hosts the minimal ``OpenClaude*`` lifecycle events that the process
lifecycle manager (Task 03.0) needs to emit before Task 05.0 canonicalises the
full event set - mirroring how ``exceptions.py`` forward-declares the exception
hierarchy.

Both events **subclass the live** :class:`aegis_swr.core.events.DomainEvent`.
This deliberately deviates from Task 05.0's stale draft text (which described a
plain dataclass carrying an ``event_type`` string and no base class): that draft
assumed a routing event bus keyed on a string discriminator which was never
built. The bus that actually ships (:class:`aegis_swr.core.events.EventBus`)
dispatches by walking ``type(event).__mro__`` and delivers only to
:class:`DomainEvent` subclasses, so a plain dataclass would be silently dropped
to zero subscribers. Subclassing :class:`DomainEvent` is therefore the only
shape that dispatches on the live bus.

When Task 05.0 canonicalises these events it **must preserve** both the
:class:`DomainEvent` subclassing and the field names declared here so existing
subscribers and the Task 03.0 emitter keep working; it may only extend them.

This module must not import ``grpc`` or ``litellm`` (contract C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

from aegis_swr.core.events import DomainEvent


def _utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp.

    :return: ``datetime.now`` bound to UTC (never a naive timestamp).
    """
    return datetime.now(UTC)


@dataclass(frozen=True)
class OpenClaudeConnected(DomainEvent):
    """Emitted once when an OpenClaude session is ready to serve requests.

    :ivar run_id: Investigation run id this session is bound to.
    :ivar grpc_url: Ready ``host[:port]`` endpoint the caller may dial;
        configuration, never incident payload (C9).
    :ivar mode: Lifecycle mode that produced the session - ``"external"`` for a
        pre-running sidecar, ``"managed"`` for an Aegis-started process.
    :ivar timestamp: Timezone-aware UTC time the connection was established.
    """

    event_type: ClassVar[str] = "openclaude.connected"

    run_id: str
    grpc_url: str
    mode: str
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(frozen=True)
class OpenClaudeDisconnected(DomainEvent):
    """Emitted once when an OpenClaude session is torn down.

    :ivar run_id: Investigation run id this session was bound to.
    :ivar reason: Short, payload-free reason string (e.g. ``"context_exit"``).
    :ivar timestamp: Timezone-aware UTC time the disconnect fired.
    """

    event_type: ClassVar[str] = "openclaude.disconnected"

    run_id: str
    reason: str
    timestamp: datetime = field(default_factory=_utc_now)
