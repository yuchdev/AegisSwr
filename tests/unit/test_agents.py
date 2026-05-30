"""Unit tests for the four Synthetic War Room agents."""
from __future__ import annotations

from typing import Any

from aegis_swr.agents.code_analyst import CodeAnalystAgent
from aegis_swr.agents.log_historian import LogHistorianAgent
from aegis_swr.agents.os_kernel import OSKernelAgent
from aegis_swr.agents.skeptic import SkepticAgent
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    CodeAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    InvestigationState,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _base_state(**extra: Any) -> InvestigationState:
    state: InvestigationState = {
        "incident_id": "test-id",
        "incident_brief": {
            "fault_class": "memory_access_violation",
            "exception_code_raw": "0xc0000005",
            "exception_address": "0x00007ff8016a1c3f",
            "faulting_module": "db_writer",
            "faulting_function": "db_writer::serialize",
            "stack_frames": [
                {"frame_number": 0, "module": "db_writer", "function": "db_writer::serialize",
                 "instruction_address": "0x00007ff8016a1c3f"},
                {"frame_number": 1, "module": "db_writer", "function": "db_writer::flush",
                 "instruction_address": "0x00007ff8016a2210"},
            ],
            "log_summary": "14:02:10 ERROR write latency 480ms",
            "mode": "crash_dump",
        },
        "discussion_history": [],
        "round_number": 1,
        "consensus_score": 0.0,
        "is_converged": False,
        "primary_hypothesis": None,
        "current_round_scores": {},
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }
    state.update(extra)  # type: ignore[typeddict-item]
    return state


def _os_kernel_response() -> OSKernelOutput:
    return OSKernelOutput(
        exception_summary=ExceptionSummary(
            fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
            exception_code_raw="0xc0000005",
            exception_address="0x00007ff8016a1c3f",
            faulting_module="db_writer",
            faulting_function="db_writer::serialize",
            interpretation="Access violation dereferencing a freed pointer in db_writer.",
        ),
        hypotheses=[Hypothesis(root_cause="Use-after-free in serialize()", confidence=0.85)],
        confidence_score=0.85,
    )


def _code_analyst_response() -> CodeAnalystOutput:
    return CodeAnalystOutput(
        rca=RCAHypothesis(
            root_cause="Race condition exposes UAF in serialize()",
            faulting_module="db_writer",
            faulting_function="db_writer::serialize",
            evidence=["frame 0 is serialize", "frame 1 is flush"],
            confidence=0.88,
            code_location="db_writer.cpp:142",
        ),
        confidence_score=0.88,
    )


def _log_historian_response() -> LogHistorianOutput:
    return LogHistorianOutput(
        pattern_match=None,
        confidence_adjustment=0.0,
        updated_confidence=0.85,
        history_note="No recurrence detected in the last 10 incidents.",
    )


def _skeptic_confirmed() -> SkepticVerdict:
    return SkepticVerdict(
        confirmed=True,
        confidence=ConfidenceLevel.HIGH,
        challenges=[],
        corrections=[],
    )


def _skeptic_rejected() -> SkepticVerdict:
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["Stated module not consistent with exception code"],
        corrections=["Re-examine the exception address"],
    )


# ---------------------------------------------------------------------------
# OS Kernel Agent
# ---------------------------------------------------------------------------


async def test_os_kernel_requests_correct_schema(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "OS Kernel Agent"
    assert turn.confidence_score == 0.85
    # The generate() call must have used OSKernelOutput as the schema.
    assert ai.calls[0]["schema"] is OSKernelOutput


async def test_os_kernel_prepends_low_symbol_warning(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    state = _base_state()
    state["incident_brief"]["low_symbol_coverage_warning"] = "[LOW SYMBOL COVERAGE: 30%]"
    await agent.run(state)
    sent_content = ai.calls[0]["messages"][0]["content"]
    assert "LOW SYMBOL COVERAGE" in sent_content


async def test_os_kernel_injects_skeptic_corrections_on_round_2(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    skeptic_turn = AgentTurn(
        agent="Skeptic Agent",
        turn_number=1,
        message="Challenged",
        confidence_score=0.30,
        corrections=["Re-examine frame 3"],
    )
    state = _base_state(
        round_number=2,
        discussion_history=[skeptic_turn.model_dump(mode="json")],
    )
    await agent.run(state)
    sent = ai.calls[0]["messages"][0]["content"]
    assert "Re-examine frame 3" in sent


# ---------------------------------------------------------------------------
# Code Analyst Agent
# ---------------------------------------------------------------------------


async def test_code_analyst_requests_correct_schema(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_code_analyst_response()])
    agent = CodeAnalystAgent(ai, settings)
    os_turn = AgentTurn(
        agent="OS Kernel Agent", turn_number=1, message="UAF",
        hypotheses=[Hypothesis(root_cause="UAF", confidence=0.85)],
        confidence_score=0.85,
    )
    state = _base_state(discussion_history=[os_turn.model_dump(mode="json")])
    turn = await agent.run(state)
    assert isinstance(turn, AgentTurn)
    assert ai.calls[0]["schema"] is CodeAnalystOutput


async def test_code_analyst_includes_user_assumption(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_code_analyst_response()])
    agent = CodeAnalystAgent(ai, settings)
    state = _base_state()
    state["incident_brief"]["user_assumption"] = "DB pool was reduced yesterday"
    await agent.run(state)
    sent = ai.calls[0]["messages"][0]["content"]
    assert "DB pool was reduced yesterday" in sent


# ---------------------------------------------------------------------------
# Log Historian Agent
# ---------------------------------------------------------------------------


async def test_log_historian_requests_correct_schema(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_log_historian_response()])
    agent = LogHistorianAgent(ai, settings)
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert ai.calls[0]["schema"] is LogHistorianOutput


# ---------------------------------------------------------------------------
# Skeptic Agent — LLM path
# ---------------------------------------------------------------------------


async def test_skeptic_confirmed_sets_high_confidence(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_skeptic_confirmed()])
    agent = SkepticAgent(ai, settings)
    state = _base_state(
        primary_hypothesis={"root_cause": "UAF", "faulting_module": "db_writer"},
    )
    turn = await agent.run(state)
    assert isinstance(turn, AgentTurn)
    assert turn.confidence_score >= 0.65   # MEDIUM or HIGH


async def test_skeptic_rejected_sets_low_confidence(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_skeptic_rejected()])
    agent = SkepticAgent(ai, settings)
    state = _base_state(
        primary_hypothesis={"root_cause": "UAF", "faulting_module": "db_writer"},
    )
    turn = await agent.run(state)
    assert turn.confidence_score < 0.50
    assert len(turn.corrections) > 0


# ---------------------------------------------------------------------------
# Skeptic Agent — programmatic pre-check (no LLM call when module absent)
# ---------------------------------------------------------------------------


async def test_skeptic_fails_prechecks_without_llm_call(settings: Settings) -> None:
    ai = MockAIBackend()  # empty responses — any call would raise
    agent = SkepticAgent(ai, settings)
    state = _base_state(
        primary_hypothesis={
            "root_cause": "UAF in completely_different_module",
            "faulting_module": "completely_different_module",
        },
    )
    # stack_frames only contain "db_writer", not "completely_different_module"
    turn = await agent.run(state)
    assert turn.confidence_score < 0.50
    assert "not found in top 5 stack frames" in turn.hypotheses[0].evidence[0]
    # generate() must NOT have been called.
    assert len(ai.calls) == 0


async def test_skeptic_skips_precheck_when_no_primary_hypothesis(settings: Settings) -> None:
    ai = MockAIBackend(responses=[_skeptic_confirmed()])
    agent = SkepticAgent(ai, settings)
    # No primary_hypothesis → pre-check cannot run → falls through to LLM.
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert len(ai.calls) == 1


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------


async def test_token_tracker_accumulated_in_state(settings: Settings) -> None:
    ai = MockAIBackend(
        responses=[_os_kernel_response()],
        usage={"input_tokens": 300, "output_tokens": 50},
    )
    agent = OSKernelAgent(ai, settings)
    state = _base_state()
    await agent.run(state)
    assert state["token_tracker"]["input_tokens"] == 300
    assert state["token_tracker"]["output_tokens"] == 50
