import json
from datetime import datetime, timezone
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


def test_incident_source_minimal() -> None:
    src = IncidentSource(mode=IncidentMode.CRASH_DUMP)
    assert src.mode == IncidentMode.CRASH_DUMP
    assert src.dump_path is None
    assert src.log_paths == []


def test_incident_source_with_all_fields() -> None:
    src = IncidentSource(
        mode=IncidentMode.LOG_FORENSICS,
        incident_timestamp=datetime(2026, 5, 30, 14, 2, 11, tzinfo=timezone.utc),
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


def test_stack_frame_resolved() -> None:
    frame = StackFrame(
        frame_number=0,
        module="db_writer.dll",
        function="db_writer::serialize",
        source_file="db_writer.cpp",
        source_line=142,
        instruction_address="0x00007ff8ab12c3f0",
    )
    assert frame.function == "db_writer::serialize"


def test_stack_frame_unresolved() -> None:
    frame = StackFrame(frame_number=1, instruction_address="0x00007ff8ab12c3f1")
    assert frame.module is None
    assert frame.function is None


def test_debug_extraction_result_defaults() -> None:
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


def test_hypothesis_creation() -> None:
    h = Hypothesis(
        root_cause="Null pointer dereference in serialize()",
        faulting_module="db_writer.dll",
        evidence=["Stack frame 0 shows db_writer::serialize"],
        confidence=0.85,
    )
    assert h.confidence == 0.85


def test_agent_turn_serialization_round_trip() -> None:
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


def test_skeptic_verdict_confirmed() -> None:
    v = SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH)
    assert v.confirmed is True
    assert v.corrections == []


def test_skeptic_verdict_rejected() -> None:
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


def test_hitl_request() -> None:
    req = HITLRequest(
        question="Panel is split. Can you clarify the DB pool size?",
        context_summary="Two competing hypotheses at 0.41 and 0.38.",
        requested_data=["Current pool size", "Recent deploy notes"],
    )
    assert len(req.requested_data) == 2


# ---------------------------------------------------------------------------
# RCAReport
# ---------------------------------------------------------------------------


def test_rca_report_creation() -> None:
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


def test_rca_report_json_round_trip() -> None:
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
def test_confidence_level_from_score(score: float, expected: ConfidenceLevel) -> None:
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
def test_map_windows_ntstatus(code: str, expected: FaultClass) -> None:
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
def test_map_linux_signal(signal: int, expected: FaultClass) -> None:
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
def test_map_macos_exception(code: int, expected: FaultClass) -> None:
    assert map_macos_exception(code) == expected


# ---------------------------------------------------------------------------
# InvestigationState TypedDict
# ---------------------------------------------------------------------------


def test_investigation_state_is_dict_compatible() -> None:
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
def test_model_json_schema_exportable(model_cls: type) -> None:
    schema = model_cls.model_json_schema()
    assert "properties" in schema
    # Round-trip through json to confirm it is serialisable
    json.dumps(schema)
