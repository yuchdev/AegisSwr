"""Unit tests for the MAS orchestrator: full pipeline, routing, HITL"""
from __future__ import annotations

from typing import Any
from unittest import mock

from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    CodeAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    RCAReport,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

# ---------------------------------------------------------------------------
# Helpers - scripted agent responses
# ---------------------------------------------------------------------------


def _os(confidence: float = 0.90) -> OSKernelOutput:
    return OSKernelOutput(
        exception_summary=ExceptionSummary(
            fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
            exception_code_raw="0xc0000005",
            exception_address="0x00007ff8016a1c3f",
            faulting_module="db_writer",
            faulting_function="db_writer::serialize",
            interpretation="UAF in serialize.",
        ),
        hypotheses=[Hypothesis(root_cause="UAF in serialize()", confidence=confidence)],
        confidence_score=confidence,
    )


def _code(confidence: float = 0.90) -> CodeAnalystOutput:
    return CodeAnalystOutput(
        rca=RCAHypothesis(
            root_cause="UAF in serialize()",
            faulting_module="db_writer",
            confidence=confidence,
        ),
        confidence_score=confidence,
    )


def _historian(confidence: float = 0.90) -> LogHistorianOutput:
    return LogHistorianOutput(
        confidence_adjustment=0.0,
        updated_confidence=confidence,
        history_note="No recurrence.",
    )


def _skeptic_yes(confidence: ConfidenceLevel = ConfidenceLevel.HIGH) -> SkepticVerdict:
    return SkepticVerdict(confirmed=True, confidence=confidence)


def _skeptic_no() -> SkepticVerdict:
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["module not confirmed"],
        corrections=["re-examine"],
    )


def _one_round(confidence: float = 0.90) -> list[Any]:
    return [_os(confidence), _code(confidence), _historian(confidence), _skeptic_yes()]


def _make_orchestrator(settings: Settings, responses: list[Any]) -> Orchestrator:
    ai = MockAIBackend(responses=responses)
    return Orchestrator(settings=settings, ai_backend=ai)


def _log_only_source() -> IncidentSource:
    return IncidentSource(mode=IncidentMode.LOG_FORENSICS)


# ---------------------------------------------------------------------------
# Full pipeline - convergence
# ---------------------------------------------------------------------------


async def test_full_pipeline_converges_in_one_round(settings: Settings):
    """
    [Unit] orchestrator: verifies full pipeline converges in one round.

    Scenario:
        Given test inputs and fixtures for full pipeline converges in one round
        When test_full_pipeline_converges_in_one_round executes the target flow
        Then the expected outcome for full pipeline converges in one round is confirmed.

    Boundaries:
        - Focus: full pipeline converges in one round
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full pipeline converges in one round
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    orch = _make_orchestrator(settings, _one_round(confidence=0.90))
    report = await orch.run(_log_only_source())

    assert isinstance(report, RCAReport)
    assert report.root_cause == "UAF in serialize()"
    assert report.confidence_score >= settings.core.consensus_threshold
    assert report.hitl_request is None
    assert report.consensus_rounds == 1


async def test_full_pipeline_token_tracker_accumulates(settings: Settings):
    """
    [Unit] orchestrator: verifies full pipeline token tracker accumulates.

    Scenario:
        Given test inputs and fixtures for full pipeline token tracker accumulates
        When test_full_pipeline_token_tracker_accumulates executes the target flow
        Then the expected outcome for full pipeline token tracker accumulates is confirmed.

    Boundaries:
        - Focus: full pipeline token tracker accumulates
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to full pipeline token tracker accumulates
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    ai = MockAIBackend(
        responses=_one_round(0.90),
        usage={"input_tokens": 100, "output_tokens": 20},
    )
    orch = Orchestrator(settings=settings, ai_backend=ai)
    report = await orch.run(_log_only_source())
    # 4 agents × {100 in, 20 out}
    assert report.total_input_tokens == 400
    assert report.total_output_tokens == 80


# ---------------------------------------------------------------------------
# Skeptic rejection → second round
# ---------------------------------------------------------------------------


async def test_skeptic_rejection_triggers_second_round(settings: Settings):
    """
    [Unit] orchestrator: verifies skeptic rejection triggers second round.

    Scenario:
        Given test inputs and fixtures for skeptic rejection triggers second round
        When test_skeptic_rejection_triggers_second_round executes the target flow
        Then the expected outcome for skeptic rejection triggers second round is confirmed.

    Boundaries:
        - Focus: skeptic rejection triggers second round
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic rejection triggers second round
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    responses = [
        # Round 1: Skeptic rejects.
        _os(0.90), _code(0.90), _historian(0.90), _skeptic_no(),
        # Round 2: Skeptic confirms.
        _os(0.90), _code(0.90), _historian(0.90), _skeptic_yes(),
    ]
    orch = _make_orchestrator(settings, responses)
    report = await orch.run(_log_only_source())

    assert report.consensus_rounds == 2
    assert report.hitl_request is None
    # Round-2 OS Kernel turn was called - it's in the dialogue
    os_turns = [t for t in report.agent_dialogue if t.agent == "OS Kernel Agent"]
    assert len(os_turns) == 2


# ---------------------------------------------------------------------------
# Deadlock → HITL request
# ---------------------------------------------------------------------------


async def test_deadlock_produces_hitl_request(settings: Settings):
    """
    [Unit] orchestrator: verifies deadlock produces hitl request.

    Scenario:
        Given test inputs and fixtures for deadlock produces hitl request
        When test_deadlock_produces_hitl_request executes the target flow
        Then the expected outcome for deadlock produces hitl request is confirmed.

    Boundaries:
        - Focus: deadlock produces hitl request
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to deadlock produces hitl request
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    low = 0.30  # well below hitl_confidence_threshold=0.50
    # max_debate_rounds=4, so we need 4 rounds all rejecting
    responses = []
    for _ in range(settings.core.max_debate_rounds):
        responses += [_os(low), _code(low), _historian(low), _skeptic_no()]
    orch = _make_orchestrator(settings, responses)
    report = await orch.run(_log_only_source())

    assert report.hitl_request is not None
    assert "consensus" in report.hitl_request.question.lower() or \
           "limit" in report.hitl_request.question.lower()


# ---------------------------------------------------------------------------
# Deduplication (cache hit)
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_analysis(settings: Settings):
    """
    [Mock] orchestrator: verifies cache hit skips analysis.

    Scenario:
        Given test inputs and fixtures for cache hit skips analysis
        When test_cache_hit_skips_analysis executes the target flow
        Then the expected outcome for cache hit skips analysis is confirmed.

    Boundaries:
        - Focus: cache hit skips analysis
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cache hit skips analysis
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    cached_report = RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash="sha256:abc123",
        root_cause="Cached UAF",
        confidence_score=0.92,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(root_cause="Cached UAF", confidence=0.92),
        consensus_rounds=1,
    )
    relational = mock.AsyncMock()
    relational.find_by_hash.return_value = cached_report

    ai = MockAIBackend()  # No responses - any call would exhaust the queue
    orch = Orchestrator(settings=settings, ai_backend=ai, relational_store=relational)

    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash="sha256:abc123",
    )
    result = await orch.run(source)

    assert result.root_cause == "Cached UAF"
    assert len(ai.calls) == 0
    relational.find_by_hash.assert_awaited_once_with("sha256:abc123")


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


async def test_run_streaming_yields_agent_turn_events(settings: Settings):
    """
    [Unit] orchestrator: verifies run streaming yields agent turn events.

    Scenario:
        Given test inputs and fixtures for run streaming yields agent turn events
        When test_run_streaming_yields_agent_turn_events executes the target flow
        Then the expected outcome for run streaming yields agent turn events is confirmed.

    Boundaries:
        - Focus: run streaming yields agent turn events
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to run streaming yields agent turn events
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    orch = _make_orchestrator(settings, _one_round(confidence=0.90))
    events = []
    async for event in orch.run_streaming(_log_only_source()):
        events.append(event)

    types = [e["type"] for e in events]
    assert "agent_turn" in types
    assert "complete" in types


async def test_run_streaming_yields_hitl_event_on_deadlock(settings: Settings):
    """
    [Unit] orchestrator: verifies run streaming yields hitl event on deadlock.

    Scenario:
        Given test inputs and fixtures for run streaming yields hitl event on deadlock
        When test_run_streaming_yields_hitl_event_on_deadlock executes the target flow
        Then the expected outcome for run streaming yields hitl event on deadlock is confirmed.

    Boundaries:
        - Focus: run streaming yields hitl event on deadlock
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to run streaming yields hitl event on deadlock
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by orchestrator
    """
    low = 0.25
    responses = []
    for _ in range(settings.core.max_debate_rounds):
        responses += [_os(low), _code(low), _historian(low), _skeptic_no()]
    orch = _make_orchestrator(settings, responses)
    events = []
    async for event in orch.run_streaming(_log_only_source()):
        events.append(event)

    assert any(e["type"] == "hitl_request" for e in events)
