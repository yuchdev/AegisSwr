"""Integration tests: the Concurrency Analyst specialist in the full orchestrator path.

Drives the dynamic-panel orchestrator end-to-end with mocked AI and debug
backends and asserts fault-aware auto-selection: ``concurrency_analyst`` joins
the debate for a deadlock incident and is absent for an unrelated fault class.
"""

from __future__ import annotations

from typing import Any

from aegis_swr.config.settings import Settings
from aegis_swr.core.events import AgentSpoke, PanelResolved
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    CodeAnalystOutput,
    ConcurrencyAnalystOutput,
    ConfidenceLevel,
    DebugExtractionResult,
    ExceptionSummary,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    ResourceExhaustionOutput,
    SkepticVerdict,
    StackFrame,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend
from tests.unit.fixtures.mock_debug_backend import MockDebugBackend

_MODULE = "worker_pool"


def _extraction(fault_class: FaultClass) -> DebugExtractionResult:
    return DebugExtractionResult(
        fault_class=fault_class,
        exception_code_raw="0x0",
        exception_address="0x0",
        faulting_module=_MODULE,
        faulting_function="worker_pool::join",
        stack_frames=[
            StackFrame(
                frame_number=0,
                module=_MODULE,
                function="worker_pool::join",
                instruction_address="0x00007ff8016a1c3f",
            )
        ],
        symbol_resolution_score=0.9,
        raw_text_excerpt="Thread-12 EnterCriticalSection; Thread-7 EnterCriticalSection\n",
    )


def _dump_source() -> IncidentSource:
    return IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path="C:\\fake\\crash.dmp")


def _os(conf: float = 0.90) -> OSKernelOutput:
    return OSKernelOutput(
        exception_summary=ExceptionSummary(
            fault_class=FaultClass.DEADLOCK,
            exception_code_raw="0x0",
            exception_address="0x0",
            faulting_module=_MODULE,
            interpretation="Two worker threads blocked on each other's locks.",
        ),
        hypotheses=[Hypothesis(root_cause="AB-BA deadlock", faulting_module=_MODULE, confidence=conf)],
        confidence_score=conf,
    )


def _code(conf: float = 0.90) -> CodeAnalystOutput:
    return CodeAnalystOutput(
        rca=RCAHypothesis(root_cause="AB-BA deadlock", faulting_module=_MODULE, confidence=conf),
        confidence_score=conf,
    )


def _historian(conf: float = 0.90) -> LogHistorianOutput:
    return LogHistorianOutput(confidence_adjustment=0.0, updated_confidence=conf, history_note="No recurrence.")


def _concurrency(conf: float = 0.90) -> ConcurrencyAnalystOutput:
    return ConcurrencyAnalystOutput(
        hypotheses=[Hypothesis(root_cause="AB-BA deadlock", faulting_module=_MODULE, confidence=conf)],
        confidence_score=conf,
        wait_chain=["Thread-12 (holds A, waits B)", "Thread-7 (holds B, waits A)"],
    )


def _skeptic_yes() -> SkepticVerdict:
    return SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH)


def _resource(conf: float = 0.90) -> ResourceExhaustionOutput:
    return ResourceExhaustionOutput(
        hypotheses=[
            Hypothesis(root_cause="AB-BA deadlock", faulting_module=_MODULE, confidence=conf)
        ],
        confidence_score=conf,
        exhausted_resource="thread-pool worker threads (limit 64)",
    )


async def _collect(orch: Orchestrator, source: IncidentSource) -> list[Any]:
    return [event async for event in orch.stream_events(source)]


async def test_enabling_concurrency_analyst_yields_debate_turn(settings: Settings):
    """[Integration] a deadlock incident auto-includes concurrency_analyst before skeptic."""
    # Execution order: os_kernel, code_analyst, log_historian, concurrency_analyst,
    # resource_exhaustion (both authoritative for deadlock) then skeptic.
    responses: list[Any] = [_os(), _code(), _historian(), _concurrency(), _resource(), _skeptic_yes()]
    orch = Orchestrator(
        settings=settings,
        ai_backend=MockAIBackend(responses=responses),
        debug_backend=MockDebugBackend(_extraction(FaultClass.DEADLOCK)),
    )

    events = await _collect(orch, _dump_source())

    panel_event: PanelResolved = next(e for e in events if isinstance(e, PanelResolved))
    panel_names = [d.display_name for d in panel_event.panel]
    assert "Concurrency Analyst Agent" in panel_names
    assert panel_names[-1] == "Skeptic Agent"

    spoke_agents = [e.turn.agent for e in events if isinstance(e, AgentSpoke)]
    assert "Concurrency Analyst Agent" in spoke_agents


async def test_base_panel_unaffected_without_specialist(settings: Settings):
    """[Integration] a fault class with no specialist keeps the legacy four-agent panel."""
    responses: list[Any] = [_os(), _code(), _historian(), _skeptic_yes()]
    orch = Orchestrator(
        settings=settings,
        ai_backend=MockAIBackend(responses=responses),
        debug_backend=MockDebugBackend(_extraction(FaultClass.INTEGER_DIVIDE_BY_ZERO)),
    )

    events = await _collect(orch, _dump_source())

    panel_event: PanelResolved = next(e for e in events if isinstance(e, PanelResolved))
    panel_names = [d.display_name for d in panel_event.panel]
    assert panel_names == [
        "OS Kernel Agent",
        "Code Analyst Agent",
        "Log Historian Agent",
        "Skeptic Agent",
    ]
