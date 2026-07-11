"""Unit tests for :class:`~aegis_swr.agents.forensic.concurrency_analyst.ConcurrencyAnalystAgent`."""

from __future__ import annotations

import inspect
import json
from typing import Any, Optional

from aegis_swr.agents.base import AgentSpec, SkepticAgent
from aegis_swr.agents.forensic.concurrency_analyst import (
    _SYSTEM_PROMPT,
    ConcurrencyAnalystAgent,
    _extract_wait_chain_candidates,
)
from aegis_swr.agents.panel import resolve_panel
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    ConcurrencyAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    InvestigationState,
    OSKernelOutput,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _state(
    *,
    raw_text_excerpt: str = "",
    round_number: int = 1,
    latest_arbiter_feedback: Optional[list[str]] = None,
) -> InvestigationState:
    state: InvestigationState = {
        "incident_id": "test-id",
        "incident_brief": {
            "fault_class": "deadlock",
            "raw_text_excerpt": raw_text_excerpt,
            "mode": "crash_dump",
        },
        "discussion_history": [],
        "round_number": round_number,
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }
    if latest_arbiter_feedback is not None:
        state["latest_arbiter_feedback"] = latest_arbiter_feedback  # type: ignore[typeddict-unknown-key]
    return state


def _output(
    *,
    confidence: float = 0.75,
    hypotheses: Optional[list[Hypothesis]] = None,
    wait_chain: Optional[list[str]] = None,
) -> ConcurrencyAnalystOutput:
    return ConcurrencyAnalystOutput(
        hypotheses=hypotheses
        if hypotheses is not None
        else [Hypothesis(root_cause="AB-BA deadlock between worker threads", confidence=confidence)],
        confidence_score=confidence,
        wait_chain=wait_chain or [],
    )


def _last_context(mock: MockAIBackend) -> dict[str, Any]:
    return json.loads(mock.calls[-1]["messages"][0]["content"])


# ---------------------------------------------------------------------------
# ClassVars
# ---------------------------------------------------------------------------


def test_agent_key():
    assert ConcurrencyAnalystAgent.agent_key == "concurrency_analyst"


def test_category():
    assert ConcurrencyAnalystAgent.category == "forensic"


def test_display_name():
    assert ConcurrencyAnalystAgent.display_name == "Concurrency Analyst Agent"


def test_authoritative_fault_classes():
    assert ConcurrencyAnalystAgent.authoritative_fault_classes == frozenset(
        {FaultClass.DEADLOCK, FaultClass.USE_AFTER_FREE, FaultClass.ASSERTION_FAILURE}
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_deadlock_keywords():
    lowered = _SYSTEM_PROMPT.lower()
    for keyword in ["deadlock", "lock", "race", "wait_chain"]:
        assert keyword in lowered


def test_system_prompt_mentions_blocking_primitives():
    primitives = ["WaitForMultipleObjects", "EnterCriticalSection", "pthread_mutex", "std::mutex", "futex"]
    assert sum(p in _SYSTEM_PROMPT for p in primitives) >= 2


def test_system_prompt_references_output_schema():
    assert "ConcurrencyAnalystOutput" in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Wait-chain pre-check (pure helper)
# ---------------------------------------------------------------------------


def test_precheck_fires_on_enter_critical_section():
    assert _extract_wait_chain_candidates("frame: EnterCriticalSection at foo")


def test_precheck_fires_on_pthread_mutex_lock():
    assert _extract_wait_chain_candidates("0x1 pthread_mutex_lock (mtx)")


def test_precheck_fires_on_wait_for_multiple_objects():
    assert _extract_wait_chain_candidates("ntdll!WaitForMultipleObjects+0x1")


def test_precheck_empty_on_unrelated_text():
    assert _extract_wait_chain_candidates("just an ordinary crash with no locks") == []


def test_precheck_no_shell_or_eval():
    source = inspect.getsource(_extract_wait_chain_candidates)
    for forbidden in ["shell", "eval", "exec", "subprocess"]:
        assert forbidden not in source


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


async def test_run_returns_agent_turn(settings: Settings):
    ai = MockAIBackend(responses=[_output(confidence=0.72)])
    turn = await ConcurrencyAnalystAgent(ai, settings).run(_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "Concurrency Analyst Agent"
    assert turn.agent_key == "concurrency_analyst"
    assert turn.confidence_score == 0.72


async def test_run_builds_hypotheses_from_output(settings: Settings):
    hyps = [
        Hypothesis(root_cause="AB-BA deadlock", confidence=0.8),
        Hypothesis(root_cause="lock convoy", confidence=0.5),
    ]
    ai = MockAIBackend(responses=[_output(hypotheses=hyps)])
    turn = await ConcurrencyAnalystAgent(ai, settings).run(_state())
    assert [h.root_cause for h in turn.hypotheses] == ["AB-BA deadlock", "lock convoy"]


async def test_run_merges_precheck_into_empty_wait_chain(settings: Settings):
    """[Unit] concurrency: pre-check candidates reach the LLM and populate an empty wait_chain."""
    ai = MockAIBackend(responses=[_output(wait_chain=[])])
    agent = ConcurrencyAnalystAgent(ai, settings)
    turn = await agent.run(_state(raw_text_excerpt="Thread-12 EnterCriticalSection blocked"))

    assert "wait_chain_candidates" in _last_context(ai)
    # The merged deterministic candidate is surfaced in the turn message.
    assert "EnterCriticalSection" in turn.message


async def test_run_does_not_overwrite_populated_wait_chain(settings: Settings):
    """[Unit] concurrency: a populated LLM wait_chain is kept verbatim (no prepend)."""
    ai = MockAIBackend(responses=[_output(wait_chain=["Thread-3 -> MutexA"])])
    agent = ConcurrencyAnalystAgent(ai, settings)
    turn = await agent.run(_state(raw_text_excerpt="EnterCriticalSection present"))

    assert "Thread-3 -> MutexA" in turn.message
    assert "EnterCriticalSection" not in turn.message


async def test_run_injects_skeptic_corrections_on_round_2(settings: Settings):
    ai = MockAIBackend(responses=[_output()])
    agent = ConcurrencyAnalystAgent(ai, settings)
    await agent.run(_state(round_number=2, latest_arbiter_feedback=["re-examine lock order"]))
    assert _last_context(ai)["skeptic_corrections_from_previous_round"] == ["re-examine lock order"]


async def test_run_accumulates_tokens(settings: Settings):
    ai = MockAIBackend(responses=[_output()], usage={"input_tokens": 9, "output_tokens": 3})
    state = _state()
    await ConcurrencyAnalystAgent(ai, settings).run(state)
    assert state["token_tracker"]["input_tokens"] == 9


# ---------------------------------------------------------------------------
# Mock pipeline
# ---------------------------------------------------------------------------


async def test_mock_pipeline_deadlock_incident(settings: Settings):
    """[Unit] concurrency: a resolved deadlock panel runs and surfaces the specialist turn."""
    responses: list[Any] = [
        OSKernelOutput(
            exception_summary=ExceptionSummary(
                fault_class=FaultClass.DEADLOCK,
                exception_code_raw="0x0",
                exception_address="0x0",
                interpretation="Two threads blocked on each other's locks.",
            ),
            hypotheses=[Hypothesis(root_cause="deadlock", confidence=0.8)],
            confidence_score=0.8,
        ),
        _output(confidence=0.78),
        SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH),
    ]
    ai = MockAIBackend(responses=responses)
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="concurrency_analyst"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = resolve_panel(specs, ai, settings)

    assert sum(isinstance(a, ConcurrencyAnalystAgent) for a in panel) == 1
    assert isinstance(panel[-1], SkepticAgent)

    state = _state(raw_text_excerpt="Thread-12 EnterCriticalSection; Thread-7 EnterCriticalSection")
    turns = [await agent.run(state) for agent in panel]

    assert [t.agent for t in turns] == [
        "OS Kernel Agent",
        "Concurrency Analyst Agent",
        "Skeptic Agent",
    ]
