"""Neutral domain events and the EventBus that distributes them.

The core (Model) emits :class:`DomainEvent` instances while an investigation
runs; any number of registered views (Rich CLI, Textual TUI, GUI, headless
collectors) subscribe via the :class:`EventBus` and render however they like.
This module is pure Python — it must never import UI libraries.

Subscription is by event type and covers subclasses: subscribing to
``DomainEvent`` itself receives every event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

from aegis_swr.core.schemas import AgentTurn, IncidentSource, RCAReport


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all investigation events"""


@dataclass(frozen=True)
class InvestigationStarted(DomainEvent):
    incident_id: str
    source: IncidentSource


@dataclass(frozen=True)
class EvidenceExtracted(DomainEvent):
    """Data Adapter finished: the incident brief is ready for the panel"""

    brief: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentSpoke(DomainEvent):
    """One agent completed its turn in the current debate round"""

    node: str
    turn: AgentTurn


@dataclass(frozen=True)
class ConsensusEvaluated(DomainEvent):
    """Weighted consensus computed after a full debate round"""

    score: float
    round_number: int | None = None


@dataclass(frozen=True)
class InvestigationCompleted(DomainEvent):
    """The panel converged; the final report is available"""

    report: RCAReport


@dataclass(frozen=True)
class HumanInputRequired(DomainEvent):
    """Debate limit reached without consensus; the report carries a HITL request"""

    report: RCAReport


# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

Subscriber = Callable[[DomainEvent], None]


class EventBus:
    """Synchronous publish/subscribe dispatcher for :class:`DomainEvent`.

    Subscribers are plain callables invoked in registration order.  A failing
    subscriber is logged and skipped — a broken view must never abort the
    investigation itself.
    """

    def __init__(self):
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
            try:
                self._subscribers[event_type].remove(callback)
            except (KeyError, ValueError):
                pass

        return _unsubscribe

    def publish(self, event: DomainEvent):
        """Deliver *event* to every subscriber of its type or any base type"""
        for event_type in type(event).__mro__:
            if not issubclass(event_type, DomainEvent):
                break
            for callback in list(self._subscribers.get(event_type, [])):
                try:
                    callback(event)
                except Exception as exc:  # noqa: BLE001 — view errors must not kill the run
                    logger.warning(
                        f"Event subscriber {callback!r} failed on "
                        f"{type(event).__name__}: {exc}"
                    )
