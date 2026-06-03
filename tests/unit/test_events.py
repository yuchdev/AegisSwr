"""Unit tests for the EventBus and orchestrator domain-event emission."""
from __future__ import annotations

from aegis_swr.config.settings import Settings
from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    DomainEvent,
    EventBus,
    EvidenceExtracted,
    HumanInputRequired,
    InvestigationCompleted,
    InvestigationStarted,
)
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import AgentTurn, IncidentMode, IncidentSource
from tests.unit.fixtures.mock_ai_backend import MockAIBackend
from tests.unit.test_orchestrator import _code, _historian, _one_round, _os, _skeptic_no

# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


def _turn(agent: str = "OS Kernel Agent") -> AgentTurn:
    return AgentTurn(agent=agent, turn_number=1, message="m", confidence_score=0.8)


def test_subscribe_exact_type_receives_event() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(AgentSpoke, received.append)

    event = AgentSpoke(node="os_kernel_node", turn=_turn())
    bus.publish(event)

    assert received == [event]


def test_subscribe_base_class_receives_all_events() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    bus.publish(AgentSpoke(node="os_kernel_node", turn=_turn()))
    bus.publish(ConsensusEvaluated(score=0.9, round_number=1))

    assert len(received) == 2


def test_subscriber_does_not_receive_unrelated_events() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(EvidenceExtracted, received.append)

    bus.publish(ConsensusEvaluated(score=0.9))

    assert received == []


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    unsubscribe = bus.subscribe(ConsensusEvaluated, received.append)

    bus.publish(ConsensusEvaluated(score=0.5))
    unsubscribe()
    bus.publish(ConsensusEvaluated(score=0.9))

    assert len(received) == 1


def test_failing_subscriber_does_not_break_others() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []

    def _broken(event: DomainEvent) -> None:
        raise RuntimeError("view crashed")

    bus.subscribe(ConsensusEvaluated, _broken)
    bus.subscribe(ConsensusEvaluated, received.append)

    bus.publish(ConsensusEvaluated(score=0.7))  # must not raise

    assert len(received) == 1


# ---------------------------------------------------------------------------
# Orchestrator emission
# ---------------------------------------------------------------------------


def _log_only_source() -> IncidentSource:
    return IncidentSource(mode=IncidentMode.LOG_FORENSICS)


async def test_orchestrator_publishes_events_to_bus(settings: Settings) -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    ai = MockAIBackend(responses=_one_round(confidence=0.90))
    orch = Orchestrator(settings=settings, ai_backend=ai, event_bus=bus)

    async for _ in orch.stream_events(_log_only_source()):
        pass

    types = [type(e) for e in received]
    assert types[0] is InvestigationStarted
    assert EvidenceExtracted in types
    assert types.count(AgentSpoke) == 4  # one full panel round
    assert ConsensusEvaluated in types
    assert types[-1] is InvestigationCompleted


async def test_orchestrator_publishes_hitl_on_deadlock(settings: Settings) -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(DomainEvent, received.append)

    low = 0.25
    responses = []
    for _ in range(settings.core.max_debate_rounds):
        responses += [_os(low), _code(low), _historian(low), _skeptic_no()]
    ai = MockAIBackend(responses=responses)
    orch = Orchestrator(settings=settings, ai_backend=ai, event_bus=bus)

    async for _ in orch.stream_events(_log_only_source()):
        pass

    assert isinstance(received[-1], HumanInputRequired)
    assert received[-1].report.hitl_request is not None
