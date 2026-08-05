"""Integration tests: the Memory Forensics specialist in the full orchestrator path.

Drives the dynamic-panel orchestrator end-to-end with mocked AI and debug
backends (no live LLM, no real dump) and asserts the fault-aware auto-selection
contract: ``memory_forensics`` joins the debate for its authoritative fault
classes and is absent for unrelated ones.
"""

from __future__ import annotations

from typing import Any

from aegis_swr.config.settings import Settings
from aegis_swr.core.events import AgentSpoke, PanelResolved
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    CodeAnalystOutput,
    ConfidenceLevel,
    DebugExtractionResult,
    ExceptionSummary,
    ExploitabilityOutput,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    LogHistorianOutput,
    MemoryForensicsOutput,
    OSKernelOutput,
    RCAHypothesis,
    SkepticVerdict,
    StackFrame,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend
from tests.unit.fixtures.mock_debug_backend import MockDebugBackend

_MODULE = "db_writer"


def _extraction(fault_class: FaultClass) -> DebugExtractionResult:
    """Helper that provides extraction for the memory forensics integration tests."""
    return DebugExtractionResult(
        fault_class=fault_class,
        exception_code_raw="0xc0000005",
        exception_address="0x00007ff8016a1c3f",
        faulting_module=_MODULE,
        faulting_function="db_writer::serialize",
        stack_frames=[
            StackFrame(
                frame_number=0,
                module=_MODULE,
                function="db_writer::serialize",
                instruction_address="0x00007ff8016a1c3f",
            )
        ],
        symbol_resolution_score=0.87,
        raw_text_excerpt="EXCEPTION_CODE: 0xc0000005; heap tell 0xBAADF00D\n",
    )


def _dump_source() -> IncidentSource:
    """Helper that provides dump source for the memory forensics integration tests."""
    return IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path="C:\\fake\\crash.dmp")


def _os(conf: float = 0.90) -> OSKernelOutput:
    """Helper that provides os for the memory forensics integration tests."""
    return OSKernelOutput(
        exception_summary=ExceptionSummary(
            fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
            exception_code_raw="0xc0000005",
            exception_address="0x00007ff8016a1c3f",
            faulting_module=_MODULE,
            interpretation="Access violation dereferencing a freed pointer.",
        ),
        hypotheses=[Hypothesis(root_cause="UAF in serialize()", faulting_module=_MODULE, confidence=conf)],
        confidence_score=conf,
    )


def _code(conf: float = 0.90) -> CodeAnalystOutput:
    """Helper that provides code for the memory forensics integration tests."""
    return CodeAnalystOutput(
        rca=RCAHypothesis(
            root_cause="UAF in serialize()",
            faulting_module=_MODULE,
            confidence=conf,
        ),
        confidence_score=conf,
    )


def _historian(conf: float = 0.90) -> LogHistorianOutput:
    """Helper that provides historian for the memory forensics integration tests."""
    return LogHistorianOutput(
        confidence_adjustment=0.0,
        updated_confidence=conf,
        history_note="No recurrence found.",
    )


def _mem(conf: float = 0.90) -> MemoryForensicsOutput:
    """Helper that provides mem for the memory forensics integration tests."""
    return MemoryForensicsOutput(
        hypotheses=[Hypothesis(root_cause="UAF in serialize()", faulting_module=_MODULE, confidence=conf)],
        confidence_score=conf,
        heap_state="freed chunk reused before serialize()",
    )


def _skeptic_yes() -> SkepticVerdict:
    """Helper that provides skeptic yes for the memory forensics integration tests."""
    return SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH)


def _exploit(conf: float = 0.90) -> ExploitabilityOutput:
    """Helper that provides exploit for the memory forensics integration tests."""
    return ExploitabilityOutput(
        hypotheses=[Hypothesis(root_cause="UAF in serialize()", faulting_module=_MODULE, confidence=conf)],
        confidence_score=conf,
        exploitable=True,
        severity="high",
        attacker_control="freed pointer reused with attacker-influenced contents",
    )


async def _collect(orch: Orchestrator, source: IncidentSource) -> list[Any]:
    """Helper that provides collect for the memory forensics integration tests."""
    return [event async for event in orch.stream_events(source)]


async def test_memory_forensics_turn_present_in_debate(settings: Settings):
    """[Integration] a memory_access_violation incident auto-includes memory_forensics.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: [Integration] a memory_access_violation incident auto-includes memory_forensics.
    """
    # Execution order for this panel: os_kernel, code_analyst, log_historian,
    # memory_forensics, exploitability (investigators) then skeptic (arbiter) -
    # exploitability is also authoritative for memory_access_violation.
    responses: list[Any] = [_os(), _code(), _historian(), _mem(), _exploit(), _skeptic_yes()]
    orch = Orchestrator(
        settings=settings,
        ai_backend=MockAIBackend(responses=responses),
        debug_backend=MockDebugBackend(_extraction(FaultClass.MEMORY_ACCESS_VIOLATION)),
    )

    events = await _collect(orch, _dump_source())
    event_types = [type(e).__name__ for e in events]

    assert event_types[-1] == "InvestigationCompleted"

    panel_event: PanelResolved = next(e for e in events if isinstance(e, PanelResolved))
    panel_names = [d.display_name for d in panel_event.panel]
    assert "Memory Forensics Agent" in panel_names
    # Arbiter stays terminal even with the specialist inserted.
    assert panel_names[-1] == "Skeptic Agent"

    spoke_agents = [e.turn.agent for e in events if isinstance(e, AgentSpoke)]
    assert "Memory Forensics Agent" in spoke_agents


async def test_memory_forensics_absent_from_unrelated_fault_class(settings: Settings):
    """[Integration] a fault class with no specialist keeps the legacy four-agent panel.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: [Integration] a fault class with no specialist keeps the legacy four-agent panel.
    """
    responses: list[Any] = [_os(), _code(), _historian(), _skeptic_yes()]
    orch = Orchestrator(
        settings=settings,
        ai_backend=MockAIBackend(responses=responses),
        debug_backend=MockDebugBackend(_extraction(FaultClass.INTEGER_DIVIDE_BY_ZERO)),
    )

    events = await _collect(orch, _dump_source())

    panel_event: PanelResolved = next(e for e in events if isinstance(e, PanelResolved))
    panel_names = [d.display_name for d in panel_event.panel]
    assert "Memory Forensics Agent" not in panel_names
    assert panel_names == [
        "OS Kernel Agent",
        "Code Analyst Agent",
        "Log Historian Agent",
        "Skeptic Agent",
    ]

    spoke_agents = [e.turn.agent for e in events if isinstance(e, AgentSpoke)]
    assert "Memory Forensics Agent" not in spoke_agents
