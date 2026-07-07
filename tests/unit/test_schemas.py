import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from aegis_swr.core.fault_codes import (
    FaultClass,
    map_linux_signal,
    map_macos_exception,
    map_windows_ntstatus,
)
from aegis_swr.core.schemas import (
    AgentTurn,
    ConfidenceLevel,
    DebugExtractionResult,
    HITLRequest,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    InvestigationState,
    RCAReport,
    SkepticVerdict,
    StackFrame,
)

# ---------------------------------------------------------------------------
# IncidentSource
# ---------------------------------------------------------------------------


def test_incident_source_minimal():
    """
    [Unit] schemas: verifies incident source minimal.

    Scenario:
        Given test inputs and fixtures for incident source minimal
        When test_incident_source_minimal executes the target flow
        Then the expected outcome for incident source minimal is confirmed.

    Boundaries:
        - Focus: incident source minimal
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to incident source minimal
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    src = IncidentSource(mode=IncidentMode.CRASH_DUMP)
    assert src.mode == IncidentMode.CRASH_DUMP
    assert src.dump_path is None
    assert src.log_paths == []


def test_incident_source_with_all_fields():
    """
    [Unit] schemas: verifies incident source with all fields.

    Scenario:
        Given test inputs and fixtures for incident source with all fields
        When test_incident_source_with_all_fields executes the target flow
        Then the expected outcome for incident source with all fields is confirmed.

    Boundaries:
        - Focus: incident source with all fields
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to incident source with all fields
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    src = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11, tzinfo=UTC),
        log_paths=["/var/log/app.log"],
        user_assumption="DB pool was reduced.",
        metadata={"env": "production"},
    )
    assert src.mode == IncidentMode.LOG_FORENSICS
    assert len(src.log_paths) == 1
    assert src.metadata["env"] == "production"


# ---------------------------------------------------------------------------
# StackFrame + DebugExtractionResult
# ---------------------------------------------------------------------------


def test_stack_frame_resolved():
    """
    [Unit] schemas: verifies stack frame resolved.

    Scenario:
        Given test inputs and fixtures for stack frame resolved
        When test_stack_frame_resolved executes the target flow
        Then the expected outcome for stack frame resolved is confirmed.

    Boundaries:
        - Focus: stack frame resolved
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to stack frame resolved
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    frame = StackFrame(
        frame_number=0,
        module="db_writer.dll",
        function="db_writer::serialize",
        source_file="db_writer.cpp",
        source_line=142,
        instruction_address="0x00007ff8ab12c3f0",
    )
    assert frame.function == "db_writer::serialize"


def test_stack_frame_unresolved():
    """
    [Unit] schemas: verifies stack frame unresolved.

    Scenario:
        Given test inputs and fixtures for stack frame unresolved
        When test_stack_frame_unresolved executes the target flow
        Then the expected outcome for stack frame unresolved is confirmed.

    Boundaries:
        - Focus: stack frame unresolved
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to stack frame unresolved
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    frame = StackFrame(frame_number=1, instruction_address="0x00007ff8ab12c3f1")
    assert frame.module is None
    assert frame.function is None


def test_debug_extraction_result_defaults():
    """
    [Unit] schemas: verifies debug extraction result defaults.

    Scenario:
        Given test inputs and fixtures for debug extraction result defaults
        When test_debug_extraction_result_defaults executes the target flow
        Then the expected outcome for debug extraction result defaults is confirmed.

    Boundaries:
        - Focus: debug extraction result defaults
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to debug extraction result defaults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    result = DebugExtractionResult(
        fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
        exception_code_raw="0xC0000005",
        exception_address="0x00007ff8ab12c3f0",
    )
    assert result.symbol_resolution_score == 0.0
    assert result.stack_frames == []


# ---------------------------------------------------------------------------
# Hypothesis + AgentTurn
# ---------------------------------------------------------------------------


def test_hypothesis_creation():
    """
    [Unit] schemas: verifies hypothesis creation.

    Scenario:
        Given test inputs and fixtures for hypothesis creation
        When test_hypothesis_creation executes the target flow
        Then the expected outcome for hypothesis creation is confirmed.

    Boundaries:
        - Focus: hypothesis creation
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hypothesis creation
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    h = Hypothesis(
        root_cause="Null pointer dereference in serialize()",
        faulting_module="db_writer.dll",
        evidence=["Stack frame 0 shows db_writer::serialize"],
        confidence=0.85,
    )
    assert h.confidence == 0.85


def test_agent_turn_serialization_round_trip():
    """
    [Unit] schemas: verifies agent turn serialization round trip.

    Scenario:
        Given test inputs and fixtures for agent turn serialization round trip
        When test_agent_turn_serialization_round_trip executes the target flow
        Then the expected outcome for agent turn serialization round trip is confirmed.

    Boundaries:
        - Focus: agent turn serialization round trip
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to agent turn serialization round trip
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    turn = AgentTurn(
        agent="OS Kernel Agent",
        turn_number=1,
        message="Detected access violation at 0x00007ff8ab12c3f0.",
        hypotheses=[Hypothesis(root_cause="Use-after-free", confidence=0.70)],
        confidence_score=0.70,
    )
    data = turn.model_dump_json()
    restored = AgentTurn.model_validate_json(data)
    assert restored.agent == "OS Kernel Agent"
    assert restored.confidence_score == 0.70


# ---------------------------------------------------------------------------
# SkepticVerdict
# ---------------------------------------------------------------------------


def test_skeptic_verdict_confirmed():
    """
    [Unit] schemas: verifies skeptic verdict confirmed.

    Scenario:
        Given test inputs and fixtures for skeptic verdict confirmed
        When test_skeptic_verdict_confirmed executes the target flow
        Then the expected outcome for skeptic verdict confirmed is confirmed.

    Boundaries:
        - Focus: skeptic verdict confirmed
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic verdict confirmed
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    v = SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH)
    assert v.confirmed is True
    assert v.corrections == []


def test_skeptic_verdict_rejected():
    """
    [Unit] schemas: verifies skeptic verdict rejected.

    Scenario:
        Given test inputs and fixtures for skeptic verdict rejected
        When test_skeptic_verdict_rejected executes the target flow
        Then the expected outcome for skeptic verdict rejected is confirmed.

    Boundaries:
        - Focus: skeptic verdict rejected
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic verdict rejected
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    v = SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["Module not found in stack frames"],
        corrections=["Check frame 3 instead of frame 0"],
    )
    assert v.confirmed is False
    assert len(v.challenges) == 1


# ---------------------------------------------------------------------------
# HITLRequest
# ---------------------------------------------------------------------------


def test_hitl_request():
    """
    [Unit] schemas: verifies hitl request.

    Scenario:
        Given test inputs and fixtures for hitl request
        When test_hitl_request executes the target flow
        Then the expected outcome for hitl request is confirmed.

    Boundaries:
        - Focus: hitl request
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to hitl request
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    req = HITLRequest(
        question="Panel is split. Can you clarify the DB pool size?",
        context_summary="Two competing hypotheses at 0.41 and 0.38.",
        requested_data=["Current pool size", "Recent deploy notes"],
    )
    assert len(req.requested_data) == 2


# ---------------------------------------------------------------------------
# RCAReport
# ---------------------------------------------------------------------------


def test_rca_report_creation():
    """
    [Unit] schemas: verifies rca report creation.

    Scenario:
        Given test inputs and fixtures for rca report creation
        When test_rca_report_creation executes the target flow
        Then the expected outcome for rca report creation is confirmed.

    Boundaries:
        - Focus: rca report creation
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to rca report creation
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    report = RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        root_cause="Race condition in serialize()",
        confidence_score=0.92,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(root_cause="Race condition", confidence=0.92),
        consensus_rounds=2,
    )
    assert isinstance(report.incident_id, UUID)
    assert report.total_input_tokens == 0


def test_rca_report_json_round_trip():
    """
    [Unit] schemas: verifies rca report json round trip.

    Scenario:
        Given test inputs and fixtures for rca report json round trip
        When test_rca_report_json_round_trip executes the target flow
        Then the expected outcome for rca report json round trip is confirmed.

    Boundaries:
        - Focus: rca report json round trip
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to rca report json round trip
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    report = RCAReport(
        mode=IncidentMode.LOG_FORENSICS,
        root_cause="Deadlock in thread pool",
        confidence_score=0.78,
        confidence_level=ConfidenceLevel.MEDIUM,
        primary_hypothesis=Hypothesis(root_cause="Deadlock", confidence=0.78),
        consensus_rounds=3,
        mitigation_instructions=["Increase pool size", "Restart service"],
    )
    data = report.model_dump_json()
    restored = RCAReport.model_validate_json(data)
    assert restored.root_cause == report.root_cause
    assert len(restored.mitigation_instructions) == 2


# ---------------------------------------------------------------------------
# ConfidenceLevel.from_score
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (1.00, ConfidenceLevel.HIGH),
        (0.80, ConfidenceLevel.HIGH),
        (0.79, ConfidenceLevel.MEDIUM),
        (0.50, ConfidenceLevel.MEDIUM),
        (0.49, ConfidenceLevel.LOW),
        (0.00, ConfidenceLevel.LOW),
    ],
)
def test_confidence_level_from_score(score: float, expected: ConfidenceLevel):
    """
    [Unit] schemas: verifies confidence level from score.

    Scenario:
        Given test inputs and fixtures for confidence level from score
        When test_confidence_level_from_score executes the target flow
        Then the expected outcome for confidence level from score is confirmed.

    Boundaries:
        - Focus: confidence level from score
        - Fixtures/params: score, expected (parametrized, 6 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to confidence level from score
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    assert ConfidenceLevel.from_score(score) == expected


# ---------------------------------------------------------------------------
# FaultClass mapping functions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("0xC0000005", FaultClass.MEMORY_ACCESS_VIOLATION),
        ("0xc0000005", FaultClass.MEMORY_ACCESS_VIOLATION),  # case-insensitive
        ("0xC00000FD", FaultClass.STACK_OVERFLOW),
        ("0xC0000094", FaultClass.INTEGER_DIVIDE_BY_ZERO),
        ("0xDEADBEEF", FaultClass.UNKNOWN),
    ],
)
def test_map_windows_ntstatus(code: str, expected: FaultClass):
    """
    [Unit] schemas: verifies map windows ntstatus.

    Scenario:
        Given test inputs and fixtures for map windows ntstatus
        When test_map_windows_ntstatus executes the target flow
        Then the expected outcome for map windows ntstatus is confirmed.

    Boundaries:
        - Focus: map windows ntstatus
        - Fixtures/params: code, expected (parametrized, 5 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to map windows ntstatus
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    assert map_windows_ntstatus(code) == expected


@pytest.mark.parametrize(
    "signal,expected",
    [
        (11, FaultClass.MEMORY_ACCESS_VIOLATION),   # SIGSEGV
        (7, FaultClass.MEMORY_ACCESS_VIOLATION),    # SIGBUS
        (8, FaultClass.INTEGER_DIVIDE_BY_ZERO),     # SIGFPE
        (6, FaultClass.ASSERTION_FAILURE),          # SIGABRT
        (99, FaultClass.UNKNOWN),
    ],
)
def test_map_linux_signal(signal: int, expected: FaultClass):
    """
    [Unit] schemas: verifies map linux signal.

    Scenario:
        Given test inputs and fixtures for map linux signal
        When test_map_linux_signal executes the target flow
        Then the expected outcome for map linux signal is confirmed.

    Boundaries:
        - Focus: map linux signal
        - Fixtures/params: signal, expected (parametrized, 5 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to map linux signal
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    assert map_linux_signal(signal) == expected


@pytest.mark.parametrize(
    "code,expected",
    [
        (1, FaultClass.MEMORY_ACCESS_VIOLATION),    # EXC_BAD_ACCESS
        (3, FaultClass.INTEGER_DIVIDE_BY_ZERO),     # EXC_ARITHMETIC
        (6, FaultClass.ASSERTION_FAILURE),          # EXC_BREAKPOINT
        (99, FaultClass.UNKNOWN),
    ],
)
def test_map_macos_exception(code: int, expected: FaultClass):
    """
    [Unit] schemas: verifies map macos exception.

    Scenario:
        Given test inputs and fixtures for map macos exception
        When test_map_macos_exception executes the target flow
        Then the expected outcome for map macos exception is confirmed.

    Boundaries:
        - Focus: map macos exception
        - Fixtures/params: code, expected (parametrized, 4 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to map macos exception
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    assert map_macos_exception(code) == expected


# ---------------------------------------------------------------------------
# InvestigationState TypedDict
# ---------------------------------------------------------------------------


def test_investigation_state_is_dict_compatible():
    """
    [Unit] schemas: verifies investigation state is dict compatible.

    Scenario:
        Given test inputs and fixtures for investigation state is dict compatible
        When test_investigation_state_is_dict_compatible executes the target flow
        Then the expected outcome for investigation state is dict compatible is confirmed.

    Boundaries:
        - Focus: investigation state is dict compatible
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to investigation state is dict compatible
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    state: InvestigationState = {
        "incident_id": "test-uuid",
        "discussion_history": [],
        "round_number": 1,
        "consensus_score": 0.0,
        "is_converged": False,
        "hitl_pending": False,
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }
    assert state["round_number"] == 1
    assert isinstance(state["discussion_history"], list)


# ---------------------------------------------------------------------------
# JSON schema generation (ensures models are schema-export compatible)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_cls",
    [
        IncidentSource,
        StackFrame,
        DebugExtractionResult,
        Hypothesis,
        AgentTurn,
        SkepticVerdict,
        HITLRequest,
        RCAReport,
    ],
)
def test_model_json_schema_exportable(model_cls: type):
    """
    [Unit] schemas: verifies model json schema exportable.

    Scenario:
        Given test inputs and fixtures for model json schema exportable
        When test_model_json_schema_exportable executes the target flow
        Then the expected outcome for model json schema exportable is confirmed.

    Boundaries:
        - Focus: model json schema exportable
        - Fixtures/params: model_cls (parametrized, 8 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to model json schema exportable
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by schemas
    """
    schema = model_cls.model_json_schema()
    assert "properties" in schema
    # Round-trip through json to confirm it is serialisable
    json.dumps(schema)
