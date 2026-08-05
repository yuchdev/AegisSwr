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
    ConcurrencyAnalystOutput,
    ConfidenceLevel,
    DebugExtractionResult,
    ExploitabilityOutput,
    HITLRequest,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    InvestigationState,
    MemoryForensicsOutput,
    RCAReport,
    RemediationPlan,
    RemediationStep,
    ResourceExhaustionOutput,
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
        (11, FaultClass.MEMORY_ACCESS_VIOLATION),  # SIGSEGV
        (7, FaultClass.MEMORY_ACCESS_VIOLATION),  # SIGBUS
        (8, FaultClass.INTEGER_DIVIDE_BY_ZERO),  # SIGFPE
        (6, FaultClass.ASSERTION_FAILURE),  # SIGABRT
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


# ---------------------------------------------------------------------------
# MemoryForensicsOutput
# ---------------------------------------------------------------------------


def test_memory_forensics_output_minimal():
    """[Unit] schemas: minimal MemoryForensicsOutput uses empty/None defaults.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: minimal MemoryForensicsOutput uses empty/None defaults.
    """
    out = MemoryForensicsOutput(
        hypotheses=[Hypothesis(root_cause="heap overflow", confidence=0.8)],
        confidence_score=0.8,
    )
    assert out.corruption_signatures == []
    assert out.suspected_allocation_site is None
    assert out.heap_state is None


def test_memory_forensics_output_full():
    """[Unit] schemas: a fully-populated MemoryForensicsOutput round-trips.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a fully-populated MemoryForensicsOutput round-trips.
    """
    out = MemoryForensicsOutput(
        hypotheses=[Hypothesis(root_cause="use-after-free", confidence=0.9)],
        confidence_score=0.9,
        corruption_signatures=["0xBAADF00D at 0x7ffd3a20", "0xFEEEFEEE"],
        suspected_allocation_site="operator new[] in MyBuffer.cpp:42",
        heap_state="heap header overwritten; HEAP_ENTRY size field corrupted",
    )
    restored = MemoryForensicsOutput.model_validate(json.loads(out.model_dump_json()))
    assert restored.confidence_score == 0.9
    assert restored.corruption_signatures == ["0xBAADF00D at 0x7ffd3a20", "0xFEEEFEEE"]
    assert restored.suspected_allocation_site == "operator new[] in MyBuffer.cpp:42"
    assert restored.heap_state == "heap header overwritten; HEAP_ENTRY size field corrupted"


def test_memory_forensics_output_hypotheses_list():
    """[Unit] schemas: each hypothesis is a valid Hypothesis with confidence in range.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: each hypothesis is a valid Hypothesis with confidence in range.
    """
    out = MemoryForensicsOutput(
        hypotheses=[
            Hypothesis(root_cause="double free", confidence=0.7),
            Hypothesis(root_cause="buffer overrun", confidence=0.55),
        ],
        confidence_score=0.7,
    )
    assert all(isinstance(h, Hypothesis) for h in out.hypotheses)
    assert all(0.0 <= h.confidence <= 1.0 for h in out.hypotheses)


@pytest.mark.parametrize("bad_score", [-0.1, 1.1])
def test_memory_forensics_output_rejects_invalid_confidence(bad_score):
    """[Unit] schemas: confidence_score outside [0.0, 1.0] raises ValidationError.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: confidence_score outside [0.0, 1.0] raises ValidationError.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MemoryForensicsOutput(hypotheses=[], confidence_score=bad_score)


# ---------------------------------------------------------------------------
# ConcurrencyAnalystOutput
# ---------------------------------------------------------------------------


def test_concurrency_analyst_output_minimal():
    """[Unit] schemas: minimal ConcurrencyAnalystOutput uses empty/None defaults.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: minimal ConcurrencyAnalystOutput uses empty/None defaults.
    """
    out = ConcurrencyAnalystOutput(hypotheses=[], confidence_score=0.5)
    assert out.wait_chain == []
    assert out.lock_order_inversions == []
    assert out.suspected_race is None


def test_concurrency_analyst_output_full():
    """[Unit] schemas: a fully-populated ConcurrencyAnalystOutput round-trips.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a fully-populated ConcurrencyAnalystOutput round-trips.
    """
    out = ConcurrencyAnalystOutput(
        hypotheses=[Hypothesis(root_cause="AB-BA deadlock", confidence=0.8)],
        confidence_score=0.8,
        wait_chain=["Thread-12 (holds A, waits B)", "Thread-7 (holds B, waits A)"],
        lock_order_inversions=["MutexA before MutexB in foo.cpp:1, reversed in bar.cpp:2"],
        suspected_race="TOCTOU on shared counter",
    )
    restored = ConcurrencyAnalystOutput.model_validate(json.loads(out.model_dump_json()))
    assert restored.wait_chain == out.wait_chain
    assert restored.lock_order_inversions == out.lock_order_inversions
    assert restored.suspected_race == "TOCTOU on shared counter"


def test_concurrency_analyst_output_missing_confidence_raises():
    """[Unit] schemas: omitting confidence_score raises ValidationError.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: omitting confidence_score raises ValidationError.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ConcurrencyAnalystOutput(hypotheses=[])


def test_concurrency_analyst_output_optional_race_none():
    """[Unit] schemas: suspected_race=None serializes as JSON null.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: suspected_race=None serializes as JSON null.
    """
    out = ConcurrencyAnalystOutput(hypotheses=[], confidence_score=0.4)
    assert json.loads(out.model_dump_json())["suspected_race"] is None


# ---------------------------------------------------------------------------
# ExploitabilityOutput
# ---------------------------------------------------------------------------


def test_exploitability_output_minimal():
    """[Unit] schemas: minimal ExploitabilityOutput uses empty/None defaults.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: minimal ExploitabilityOutput uses empty/None defaults.
    """
    out = ExploitabilityOutput(hypotheses=[], confidence_score=0.5, exploitable=False, severity="none")
    assert out.attacker_control is None
    assert out.mitigations_present == []


def test_exploitability_output_full():
    """[Unit] schemas: a fully-populated ExploitabilityOutput round-trips.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a fully-populated ExploitabilityOutput round-trips.
    """
    out = ExploitabilityOutput(
        hypotheses=[Hypothesis(root_cause="controlled write primitive", confidence=0.9)],
        confidence_score=0.9,
        exploitable=True,
        severity="high",
        attacker_control="faulting address derived from user-controlled buffer offset",
        mitigations_present=["ASLR", "DEP", "stack_canary"],
    )
    restored = ExploitabilityOutput.model_validate(json.loads(out.model_dump_json()))
    assert restored.exploitable is True
    assert restored.severity == "high"
    assert restored.attacker_control == out.attacker_control
    assert restored.mitigations_present == ["ASLR", "DEP", "stack_canary"]


def test_exploitability_output_hypotheses_valid():
    """[Unit] schemas: each hypothesis is a valid Hypothesis with confidence in range.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: each hypothesis is a valid Hypothesis with confidence in range.
    """
    out = ExploitabilityOutput(
        hypotheses=[
            Hypothesis(root_cause="vtable hijack", confidence=0.7),
            Hypothesis(root_cause="SEH overwrite", confidence=0.5),
        ],
        confidence_score=0.7,
        exploitable=True,
        severity="medium",
    )
    assert all(isinstance(h, Hypothesis) for h in out.hypotheses)
    assert all(0.0 <= h.confidence <= 1.0 for h in out.hypotheses)


def test_exploitability_output_exploitable_bool():
    """[Unit] schemas: both exploitable verdicts construct and serialize cleanly.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: both exploitable verdicts construct and serialize cleanly.
    """
    not_exp = ExploitabilityOutput(hypotheses=[], confidence_score=0.3, exploitable=False, severity="none")
    exp = ExploitabilityOutput(hypotheses=[], confidence_score=0.95, exploitable=True, severity="high")
    assert json.loads(not_exp.model_dump_json())["exploitable"] is False
    assert json.loads(exp.model_dump_json())["exploitable"] is True


# ---------------------------------------------------------------------------
# ResourceExhaustionOutput
# ---------------------------------------------------------------------------


def test_resource_exhaustion_output_minimal():
    """[Unit] schemas: minimal ResourceExhaustionOutput uses empty/None defaults.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: minimal ResourceExhaustionOutput uses empty/None defaults.
    """
    out = ResourceExhaustionOutput(hypotheses=[], confidence_score=0.5)
    assert out.exhausted_resource is None
    assert out.leak_indicators == []
    assert out.growth_trend is None


def test_resource_exhaustion_output_full():
    """[Unit] schemas: a fully-populated ResourceExhaustionOutput round-trips.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a fully-populated ResourceExhaustionOutput round-trips.
    """
    out = ResourceExhaustionOutput(
        hypotheses=[Hypothesis(root_cause="fd leak in accept loop", confidence=0.8)],
        confidence_score=0.8,
        exhausted_resource="file descriptors (ulimit 1024)",
        leak_indicators=["too many open files: errno 24", "handle count: 62100"],
        growth_trend="fd count grows ~5/s, linear since 02:00 UTC",
    )
    restored = ResourceExhaustionOutput.model_validate(json.loads(out.model_dump_json()))
    assert restored.exhausted_resource == out.exhausted_resource
    assert restored.leak_indicators == out.leak_indicators
    assert restored.growth_trend == out.growth_trend


def test_resource_exhaustion_output_hypotheses_list():
    """[Unit] schemas: each hypothesis is a valid Hypothesis with confidence in range.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: each hypothesis is a valid Hypothesis with confidence in range.
    """
    out = ResourceExhaustionOutput(
        hypotheses=[
            Hypothesis(root_cause="handle leak", confidence=0.7),
            Hypothesis(root_cause="thread pool starvation", confidence=0.6),
        ],
        confidence_score=0.7,
    )
    assert all(isinstance(h, Hypothesis) for h in out.hypotheses)
    assert all(0.0 <= h.confidence <= 1.0 for h in out.hypotheses)


@pytest.mark.parametrize("bad_score", [-0.1, 1.1])
def test_resource_exhaustion_output_rejects_invalid_confidence(bad_score):
    """[Unit] schemas: confidence_score outside [0.0, 1.0] raises ValidationError.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: confidence_score outside [0.0, 1.0] raises ValidationError.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ResourceExhaustionOutput(hypotheses=[], confidence_score=bad_score)


# ---------------------------------------------------------------------------
# RemediationStep / RemediationPlan / RCAReport.remediation_plan
# ---------------------------------------------------------------------------


def _step(order: int = 1, **kw) -> RemediationStep:
    """Build a canned idempotent :class:`RemediationStep`, overriding fields via *kw*."""
    base = {"order": order, "action": "restart svc", "idempotent": True, "rollback": "stop svc"}
    base.update(kw)
    return RemediationStep(**base)


def _plan(**kw) -> RemediationPlan:
    """Build a canned single-step :class:`RemediationPlan`, overriding fields via *kw*."""
    base = {
        "steps": [_step()],
        "summary": "restart the service",
        "confidence": 0.9,
        "requires_human_approval": False,
    }
    base.update(kw)
    return RemediationPlan(**base)


def _minimal_report(**kw) -> RCAReport:
    """Build a minimal :class:`RCAReport`, overriding fields via *kw*."""
    from aegis_swr.core.schemas import ConfidenceLevel

    base = {
        "mode": IncidentMode.LOG_FORENSICS,
        "root_cause": "fd leak",
        "confidence_score": 0.9,
        "confidence_level": ConfidenceLevel.HIGH,
        "primary_hypothesis": Hypothesis(root_cause="fd leak", confidence=0.9),
        "consensus_rounds": 1,
    }
    base.update(kw)
    return RCAReport(**base)


def test_remediation_step_requires_rollback():
    """[Unit] schemas: an empty rollback string is rejected.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: an empty rollback string is rejected.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _step(rollback="")


def test_remediation_step_defaults():
    """[Unit] schemas: verification/risk default to None; approval defaults False.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: verification/risk default to None; approval defaults False.
    """
    step = _step()
    assert step.verification is None
    assert step.risk is None
    assert step.requires_human_approval is False


def test_remediation_step_rejects_readonly_rollback_when_not_idempotent():
    """[Unit] schemas: a non-idempotent step cannot use the read-only sentinel.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a non-idempotent step cannot use the read-only sentinel.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _step(idempotent=False, rollback="read-only: no state change")


def test_remediation_plan_rejects_empty_steps():
    """[Unit] schemas: a plan with no steps is rejected.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a plan with no steps is rejected.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RemediationPlan(steps=[], summary="x", confidence=0.9, requires_human_approval=False)


def test_remediation_plan_rejects_non_contiguous_order():
    """[Unit] schemas: step order must be a contiguous 1-based sequence.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: step order must be a contiguous 1-based sequence.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RemediationPlan(
            steps=[_step(order=1), _step(order=3)],
            summary="x",
            confidence=0.9,
            requires_human_approval=False,
        )
    ok = RemediationPlan(
        steps=[_step(order=1), _step(order=2), _step(order=3)],
        summary="x",
        confidence=0.9,
        requires_human_approval=False,
    )
    assert [s.order for s in ok.steps] == [1, 2, 3]


def test_remediation_plan_requires_human_approval_on_low_confidence():
    """[Unit] schemas: confidence < 0.70 forces requires_human_approval=True.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: confidence < 0.70 forces requires_human_approval=True.
    """
    plan = _plan(confidence=0.60, requires_human_approval=False)
    assert plan.requires_human_approval is True


def test_rca_report_remediation_plan_optional():
    """[Unit] schemas: RCAReport without a plan serializes with remediation_plan None.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: rCAReport without a plan serializes with remediation_plan None.
    """
    report = _minimal_report()
    assert report.remediation_plan is None
    assert json.loads(report.model_dump_json())["remediation_plan"] is None


def test_rca_report_with_remediation_plan_roundtrips():
    """[Unit] schemas: a report carrying a plan survives a JSON round-trip.

    Scenario: the schema is constructed and validated as described in the summary.

    Boundaries: exercises the Pydantic model definition only.

    On failure, first check: a report carrying a plan survives a JSON round-trip.
    """
    report = _minimal_report(remediation_plan=_plan())
    restored = RCAReport.model_validate_json(report.model_dump_json())
    assert restored.remediation_plan is not None
    assert restored.remediation_plan.steps[0].rollback == "stop svc"
    assert restored.remediation_plan.steps[0].order == 1


@pytest.mark.parametrize(
    "code,expected",
    [
        (1, FaultClass.MEMORY_ACCESS_VIOLATION),  # EXC_BAD_ACCESS
        (3, FaultClass.INTEGER_DIVIDE_BY_ZERO),  # EXC_ARITHMETIC
        (6, FaultClass.ASSERTION_FAILURE),  # EXC_BREAKPOINT
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
