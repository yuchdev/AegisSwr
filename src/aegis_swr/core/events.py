"""Neutral domain events and the EventBus that distributes them.

The core (Model) emits :class:`DomainEvent` instances while an investigation
runs; any number of registered views (Rich CLI, Textual TUI, GUI, headless
collectors) subscribes via the :class:`EventBus` and renders however they like.
This module is pure Python - it must never import UI libraries.

Subscription is by event type and covers subclasses: subscribing to
``DomainEvent`` itself receives every event.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger

from aegis_swr.core.schemas import AgentRole, AgentTurn, IncidentSource, RCAReport

# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all investigation events"""

    pass


@dataclass(frozen=True)
class InvestigationStarted(DomainEvent):
    """
    Represents an event that signifies the start of an investigation.

    :ivar incident_id: Unique identifier of the incident associated with the investigation.
    :type incident_id: str
    :ivar source: Source of the incident triggering the investigation.
    :type source: IncidentSource
    """

    incident_id: str
    source: IncidentSource


@dataclass(frozen=True)
class EvidenceExtracted(DomainEvent):
    """Data Adapter finished: the incident brief is ready for the panel

    :ivar brief: The incident brief
    :type brief: dict[str, Any]
    """

    brief: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PanelAgentDescriptor:
    """A JSON-serializable description of a single resolved panel agent.

    :ivar node_name: The graph node name assigned to the agent.
    :type node_name: str
    :ivar display_name: The human-facing label for the agent.
    :type display_name: str
    :ivar role: The behavioral role the agent plays in the panel.
    :type role: AgentRole
    """

    node_name: str
    display_name: str
    role: AgentRole


@dataclass(frozen=True)
class PanelResolved(DomainEvent):
    """Panel resolution completed: the agent roster for this run is fixed

    Views subscribe to this to learn which agents are running instead of
    assuming a fixed panel, so tracking state adapts to any resolved roster.

    :ivar panel: The resolved agents, in the order they run.
    :type panel: list[PanelAgentDescriptor]
    """

    panel: list[PanelAgentDescriptor] = field(default_factory=list)


@dataclass(frozen=True)
class AgentSpoke(DomainEvent):
    """One agent completed its turn in the current debate round

    :ivar node: The node that spoke
    :type node: str
    :ivar turn: The turn that was spoken
    :type turn: AgentTurn
    """

    node: str
    turn: AgentTurn


@dataclass(frozen=True)
class ConsensusEvaluated(DomainEvent):
    """Weighted consensus computed after a full debate round

    :ivar score: The consensus score
    :type score: float
    :ivar round_number: The round number
    :type round_number: Optional[int]
    """

    score: float
    round_number: Optional[int] = None


@dataclass(frozen=True)
class InvestigationCompleted(DomainEvent):
    """The panel converged; the final report is available

    :ivar report: The final report
    :type report: RCAReport
    """

    report: RCAReport


@dataclass(frozen=True)
class HumanInputRequired(DomainEvent):
    """Debate limit reached without consensus; the report carries a HITL request

    :ivar report: The final report
    :type report: RCAReport
    """

    report: RCAReport


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

Subscriber = Callable[[DomainEvent], None]


class EventBus:
    """Synchronous publish/subscribe dispatcher for :class:`DomainEvent`.

    Subscribers are plain callables invoked in registration order.  A failing
    subscriber is logged and skipped - a broken view must never abort the
    investigation itself.
    """

    def __init__(self):
        """Initialise with no subscribers registered."""
        self._subscribers: dict[type[DomainEvent], list[Subscriber]] = {}

    def subscribe(
        self,
        event_type: type[DomainEvent],
        callback: Subscriber,
    ) -> Callable[[], None]:
        """Register *callback* for *event_type* (and its subclasses).

        Returns an unsubscribe function.
        """
        self._subscribers.setdefault(event_type, []).append(callback)

        def _unsubscribe():
            """Remove *callback* from *event_type*'s subscriber list, if still present."""
            try:
                self._subscribers[event_type].remove(callback)
            except (KeyError, ValueError):
                logger.warning("Failed to unsubscribe from {}: not subscribed", event_type)

        return _unsubscribe

    def publish(self, event: DomainEvent):
        """Deliver *event* to every subscriber of its type or any base type"""
        # noinspection PyTypeChecker
        for event_type in type(event).__mro__:
            if not issubclass(event_type, DomainEvent):
                break
            for callback in list(self._subscribers.get(event_type, [])):
                try:
                    callback(event)
                except Exception:  # noqa: X002 - a broken subscriber must never abort the investigation
                    logger.exception("Subscriber {} raised for {}", callback, event_type)
