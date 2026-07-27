"""Unit tests for :class:`~aegis_swr.agents.forensic.resource_analyst.ResourceExhaustionAgent`."""

from __future__ import annotations

import json
from typing import Any, Optional

from aegis_swr.agents.forensic.resource_analyst import _SYSTEM_PROMPT, ResourceExhaustionAgent
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    Hypothesis,
    InvestigationState,
    ResourceExhaustionOutput,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _state(
    *,
    log_summary: Any = None,
    include_log_summary: bool = True,
    raw_text_excerpt: str = "",
    round_number: int = 1,
    latest_arbiter_feedback: Optional[list[str]] = None,
) -> InvestigationState:
    brief: dict[str, Any] = {"fault_class": "resource_exhaustion", "mode": "crash_dump"}
    if include_log_summary:
        brief["log_summary"] = log_summary
    if raw_text_excerpt:
        brief["raw_text_excerpt"] = raw_text_excerpt
    state: InvestigationState = {
        "incident_id": "test-id",
        "incident_brief": brief,
        "discussion_history": [],
        "round_number": round_number,
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }
    if latest_arbiter_feedback is not None:
        state["latest_arbiter_feedback"] = latest_arbiter_feedback  # type: ignore[typeddict-unknown-key]
    return state


def _output(
    *,
    confidence: float = 0.72,
    exhausted_resource: Optional[str] = "Win32 handle table",
    leak_indicators: Optional[list[str]] = None,
    hypotheses: Optional[list[Hypothesis]] = None,
) -> ResourceExhaustionOutput:
    return ResourceExhaustionOutput(
        hypotheses=hypotheses
        if hypotheses is not None
        else [Hypothesis(root_cause="handle leak in accept loop", confidence=confidence)],
        confidence_score=confidence,
        exhausted_resource=exhausted_resource,
        leak_indicators=leak_indicators or [],
    )


def _last_context(mock: MockAIBackend) -> dict[str, Any]:
    return json.loads(mock.calls[-1]["messages"][0]["content"])


# ---------------------------------------------------------------------------
# ClassVars
# ---------------------------------------------------------------------------


def test_classvars():
    assert ResourceExhaustionAgent.agent_key == "resource_exhaustion"
    assert ResourceExhaustionAgent.category == "forensic"
    assert ResourceExhaustionAgent.display_name == "Resource Exhaustion Agent"


def test_authoritative_fault_classes():
    assert ResourceExhaustionAgent.authoritative_fault_classes == frozenset(
        {FaultClass.RESOURCE_EXHAUSTION, FaultClass.STACK_OVERFLOW, FaultClass.DEADLOCK}
    )


# ---------------------------------------------------------------------------
# Deterministic pre-check
# ---------------------------------------------------------------------------


def test_precheck_detects_oom():
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "java.lang.OutOfMemoryError: GC overhead limit exceeded"}
    )
    assert any("out of memory" in i.lower() or "oom" in i.lower() for i in indicators)


def test_precheck_detects_too_many_open_files():
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"raw_text_excerpt": "accept: too many open files (errno 24)"}
    )
    assert any("open files" in i.lower() for i in indicators)


def test_precheck_detects_win32_resource_error():
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"raw_text_excerpt": "CreateHandle failed: ERROR_NO_SYSTEM_RESOURCES"}
    )
    assert indicators


def test_precheck_detects_thread_exhaustion():
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "thread pool exhausted: limit 64 workers reached"}
    )
    assert any("thread" in i.lower() for i in indicators)


def test_precheck_detects_connection_pool():
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "ConnectionPool timeout: pool full (100/100)"}
    )
    assert indicators


def test_precheck_empty_brief():
    assert ResourceExhaustionAgent._extract_leak_indicators({}) == []


def test_precheck_never_raises():
    result = ResourceExhaustionAgent._extract_leak_indicators({"log_summary": 12345})
    assert isinstance(result, list)


def test_precheck_trims_long_indicators():
    filler = "x" * 500
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": f"{filler} too many open files {filler}"}
    )
    assert indicators
    assert all(len(i) <= 200 for i in indicators)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_resource_keywords():
    lowered = _SYSTEM_PROMPT.lower()
    assert "handle" in lowered
    assert "file descriptor" in lowered or "fd" in lowered
    assert "thread" in lowered
    assert "memory" in lowered
    assert "resourceexhaustionoutput" in lowered or "resource_exhaustion" in lowered
    assert "log_summary" in lowered


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


async def test_run_returns_agent_turn(settings: Settings):
    ai = MockAIBackend(responses=[_output(confidence=0.72)])
    turn = await ResourceExhaustionAgent(ai, settings).run(_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "Resource Exhaustion Agent"
    assert turn.agent_key == "resource_exhaustion"


async def test_run_merges_precheck_into_turn(settings: Settings):
    ai = MockAIBackend(responses=[_output(leak_indicators=[])])
    agent = ResourceExhaustionAgent(ai, settings)
    turn = await agent.run(_state(log_summary="java.lang.OutOfMemoryError: heap"))
    assert turn.hypotheses
    assert "precheck_leak_indicators" in _last_context(ai)
    assert _last_context(ai)["precheck_leak_indicators"]  # non-empty


async def test_run_includes_log_summary_in_context(settings: Settings):
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(log_summary="handle count: 62100 (threshold 60000)"))
    ctx = _last_context(ai)
    assert ctx["log_summary"] == "handle count: 62100 (threshold 60000)"


async def test_run_includes_log_summary_key_even_when_none(settings: Settings):
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(include_log_summary=False))
    ctx = _last_context(ai)
    assert "log_summary" in ctx
    assert ctx["log_summary"] is None


async def test_run_incorporates_skeptic_corrections(settings: Settings):
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(round_number=2, latest_arbiter_feedback=["check handle leak in thread X"]))
    ctx = _last_context(ai)
    assert ctx["skeptic_corrections_from_previous_round"] == ["check handle leak in thread X"]


async def test_run_confidence_propagated(settings: Settings):
    ai = MockAIBackend(responses=[_output(confidence=0.85)])
    turn = await ResourceExhaustionAgent(ai, settings).run(_state())
    assert turn.confidence_score == 0.85
