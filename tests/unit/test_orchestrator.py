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
# Helpers — scripted agent responses
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
# Full pipeline — convergence
# ---------------------------------------------------------------------------


async def test_full_pipeline_converges_in_one_round(settings: Settings):
    orch = _make_orchestrator(settings, _one_round(confidence=0.90))
    report = await orch.run(_log_only_source())

    assert isinstance(report, RCAReport)
    assert report.root_cause == "UAF in serialize()"
    assert report.confidence_score >= settings.core.consensus_threshold
    assert report.hitl_request is None
    assert report.consensus_rounds == 1


async def test_full_pipeline_token_tracker_accumulates(settings: Settings):
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
    # Round-2 OS Kernel turn was called — it's in the dialogue
    os_turns = [t for t in report.agent_dialogue if t.agent == "OS Kernel Agent"]
    assert len(os_turns) == 2


# ---------------------------------------------------------------------------
# Deadlock → HITL request
# ---------------------------------------------------------------------------


async def test_deadlock_produces_hitl_request(settings: Settings):
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

    ai = MockAIBackend()  # No responses — any call would exhaust the queue
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
    orch = _make_orchestrator(settings, _one_round(confidence=0.90))
    events = []
    async for event in orch.run_streaming(_log_only_source()):
        events.append(event)

    types = [e["type"] for e in events]
    assert "agent_turn" in types
    assert "complete" in types


async def test_run_streaming_yields_hitl_event_on_deadlock(settings: Settings):
    low = 0.25
    responses = []
    for _ in range(settings.core.max_debate_rounds):
        responses += [_os(low), _code(low), _historian(low), _skeptic_no()]
    orch = _make_orchestrator(settings, responses)
    events = []
    async for event in orch.run_streaming(_log_only_source()):
        events.append(event)

    assert any(e["type"] == "hitl_request" for e in events)
