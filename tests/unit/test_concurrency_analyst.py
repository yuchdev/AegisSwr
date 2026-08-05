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
    """Build an investigation state seeded with a deadlock incident brief."""
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
    """Build a canned concurrency-analyst output with the given confidence/chain."""
    return ConcurrencyAnalystOutput(
        hypotheses=hypotheses
        if hypotheses is not None
        else [Hypothesis(root_cause="AB-BA deadlock between worker threads", confidence=confidence)],
        confidence_score=confidence,
        wait_chain=wait_chain or [],
    )


def _last_context(mock: MockAIBackend) -> dict[str, Any]:
    """Return the JSON-decoded context of the mock backend's most recent call."""
    return json.loads(mock.calls[-1]["messages"][0]["content"])


# ---------------------------------------------------------------------------
# ClassVars
# ---------------------------------------------------------------------------


def test_agent_key():
    """[Unit] concurrency: the agent advertises its canonical ``agent_key``.

    Scenario: the class-level ``agent_key`` is read.

    Boundaries: static class metadata only.

    On failure, first check: ``agent_key`` must be ``concurrency_analyst``.
    """
    assert ConcurrencyAnalystAgent.agent_key == "concurrency_analyst"


def test_category():
    """[Unit] concurrency: the agent declares the ``forensic`` category.

    Scenario: the class-level ``category`` is read.

    Boundaries: static class metadata only.

    On failure, first check: ``category`` must be ``forensic``.
    """
    assert ConcurrencyAnalystAgent.category == "forensic"


def test_display_name():
    """[Unit] concurrency: the agent exposes its human-readable display name.

    Scenario: the class-level ``display_name`` is read.

    Boundaries: static class metadata only.

    On failure, first check: ``display_name`` must be ``Concurrency Analyst Agent``.
    """
    assert ConcurrencyAnalystAgent.display_name == "Concurrency Analyst Agent"


def test_authoritative_fault_classes():
    """[Unit] concurrency: the agent claims its authoritative fault classes.

    Scenario: the class-level ``authoritative_fault_classes`` is read.

    Boundaries: static class metadata only.

    On failure, first check: the set must be deadlock, use-after-free, and assertion
    failure.
    """
    assert ConcurrencyAnalystAgent.authoritative_fault_classes == frozenset(
        {FaultClass.DEADLOCK, FaultClass.USE_AFTER_FREE, FaultClass.ASSERTION_FAILURE}
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_deadlock_keywords():
    """[Unit] concurrency: the system prompt covers core deadlock vocabulary.

    Scenario: the module system prompt is scanned for keywords.

    Boundaries: static prompt-content check only.

    On failure, first check: ``deadlock``, ``lock``, ``race``, and ``wait_chain`` must
    all appear.
    """
    lowered = _SYSTEM_PROMPT.lower()
    for keyword in ["deadlock", "lock", "race", "wait_chain"]:
        assert keyword in lowered


def test_system_prompt_mentions_blocking_primitives():
    """[Unit] concurrency: the system prompt names common blocking primitives.

    Scenario: the module system prompt is scanned for OS synchronisation calls.

    Boundaries: static prompt-content check only.

    On failure, first check: at least two named blocking primitives must appear.
    """
    primitives = ["WaitForMultipleObjects", "EnterCriticalSection", "pthread_mutex", "std::mutex", "futex"]
    assert sum(p in _SYSTEM_PROMPT for p in primitives) >= 2


def test_system_prompt_references_output_schema():
    """[Unit] concurrency: the system prompt names its structured output schema.

    Scenario: the module system prompt is scanned for the schema name.

    Boundaries: static prompt-content check only.

    On failure, first check: ``ConcurrencyAnalystOutput`` must be referenced.
    """
    assert "ConcurrencyAnalystOutput" in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Wait-chain pre-check (pure helper)
# ---------------------------------------------------------------------------


def test_precheck_fires_on_enter_critical_section():
    """[Unit] concurrency: the wait-chain pre-check matches EnterCriticalSection.

    Scenario: text containing ``EnterCriticalSection`` is scanned.

    Boundaries: exercises the pure regex pre-check helper only.

    On failure, first check: the helper must return a non-empty candidate list.
    """
    assert _extract_wait_chain_candidates("frame: EnterCriticalSection at foo")


def test_precheck_fires_on_pthread_mutex_lock():
    """[Unit] concurrency: the wait-chain pre-check matches pthread_mutex_lock.

    Scenario: text containing ``pthread_mutex_lock`` is scanned.

    Boundaries: exercises the pure regex pre-check helper only.

    On failure, first check: the helper must return a non-empty candidate list.
    """
    assert _extract_wait_chain_candidates("0x1 pthread_mutex_lock (mtx)")


def test_precheck_fires_on_wait_for_multiple_objects():
    """[Unit] concurrency: the wait-chain pre-check matches WaitForMultipleObjects.

    Scenario: text containing ``WaitForMultipleObjects`` is scanned.

    Boundaries: exercises the pure regex pre-check helper only.

    On failure, first check: the helper must return a non-empty candidate list.
    """
    assert _extract_wait_chain_candidates("ntdll!WaitForMultipleObjects+0x1")


def test_precheck_empty_on_unrelated_text():
    """[Unit] concurrency: the wait-chain pre-check ignores unrelated text.

    Scenario: text with no blocking primitives is scanned.

    Boundaries: exercises the pure regex pre-check helper only.

    On failure, first check: the helper must return an empty list.
    """
    assert _extract_wait_chain_candidates("just an ordinary crash with no locks") == []


def test_precheck_no_shell_or_eval():
    """[Unit] concurrency: the wait-chain pre-check performs no dangerous operations.

    Scenario: the helper's source is inspected for forbidden sinks.

    Boundaries: static source scan enforcing the payload-safety rule.

    On failure, first check: the source must contain no shell/eval/exec/subprocess use.
    """
    source = inspect.getsource(_extract_wait_chain_candidates)
    for forbidden in ["shell", "eval", "exec", "subprocess"]:
        assert forbidden not in source


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


async def test_run_returns_agent_turn(settings: Settings):
    """[Unit] concurrency: ``run`` returns a well-formed agent turn.

    Scenario: the agent runs against a scripted 0.72-confidence output.

    Boundaries: the AI backend is mocked; only turn assembly is asserted.

    On failure, first check: the result must be an ``AgentTurn`` with the agent name,
    key, and confidence propagated.
    """
    ai = MockAIBackend(responses=[_output(confidence=0.72)])
    turn = await ConcurrencyAnalystAgent(ai, settings).run(_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "Concurrency Analyst Agent"
    assert turn.agent_key == "concurrency_analyst"
    assert turn.confidence_score == 0.72


async def test_run_builds_hypotheses_from_output(settings: Settings):
    """[Unit] concurrency: ``run`` carries the model's hypotheses into the turn.

    Scenario: the scripted output lists two ranked hypotheses.

    Boundaries: the AI backend is mocked; only hypothesis propagation is asserted.

    On failure, first check: the turn's hypotheses must preserve the model's order.
    """
    hyps = [
        Hypothesis(root_cause="AB-BA deadlock", confidence=0.8),
        Hypothesis(root_cause="lock convoy", confidence=0.5),
    ]
    ai = MockAIBackend(responses=[_output(hypotheses=hyps)])
    turn = await ConcurrencyAnalystAgent(ai, settings).run(_state())
    assert [h.root_cause for h in turn.hypotheses] == ["AB-BA deadlock", "lock convoy"]


async def test_run_merges_precheck_into_empty_wait_chain(settings: Settings):
    """[Unit] concurrency: pre-check candidates reach the LLM and fill an empty chain.

    Scenario: the excerpt names ``EnterCriticalSection`` and the model returns an
    empty wait chain.

    Boundaries: the AI backend is mocked; the deterministic pre-check merge is under
    test.

    On failure, first check: the merged candidate must appear in the LLM context and
    the turn message.
    """
    ai = MockAIBackend(responses=[_output(wait_chain=[])])
    agent = ConcurrencyAnalystAgent(ai, settings)
    turn = await agent.run(_state(raw_text_excerpt="Thread-12 EnterCriticalSection blocked"))

    assert "wait_chain_candidates" in _last_context(ai)
    # The merged deterministic candidate is surfaced in the turn message.
    assert "EnterCriticalSection" in turn.message


async def test_run_does_not_overwrite_populated_wait_chain(settings: Settings):
    """[Unit] concurrency: a populated LLM wait_chain is kept verbatim.

    Scenario: the model returns a non-empty wait chain while the excerpt also names a
    primitive.

    Boundaries: the AI backend is mocked; the no-overwrite rule is under test.

    On failure, first check: the model's chain must be kept and the deterministic
    candidate must not be prepended.
    """
    ai = MockAIBackend(responses=[_output(wait_chain=["Thread-3 -> MutexA"])])
    agent = ConcurrencyAnalystAgent(ai, settings)
    turn = await agent.run(_state(raw_text_excerpt="EnterCriticalSection present"))

    assert "Thread-3 -> MutexA" in turn.message
    assert "EnterCriticalSection" not in turn.message


async def test_run_injects_skeptic_corrections_on_round_2(settings: Settings):
    """[Unit] concurrency: round-2 runs forward the prior arbiter corrections.

    Scenario: the agent runs on round 2 with arbiter feedback in state.

    Boundaries: the AI backend is mocked; only context assembly is asserted.

    On failure, first check: the LLM context must carry
    ``skeptic_corrections_from_previous_round``.
    """
    ai = MockAIBackend(responses=[_output()])
    agent = ConcurrencyAnalystAgent(ai, settings)
    await agent.run(_state(round_number=2, latest_arbiter_feedback=["re-examine lock order"]))
    assert _last_context(ai)["skeptic_corrections_from_previous_round"] == ["re-examine lock order"]


async def test_run_accumulates_tokens(settings: Settings):
    """[Unit] concurrency: ``run`` accumulates the call's token usage into state.

    Scenario: the mock backend reports usage for one run.

    Boundaries: the AI backend is mocked; only token bookkeeping is asserted.

    On failure, first check: the state token tracker must reflect the reported input
    tokens.
    """
    ai = MockAIBackend(responses=[_output()], usage={"input_tokens": 9, "output_tokens": 3})
    state = _state()
    await ConcurrencyAnalystAgent(ai, settings).run(state)
    assert state["token_tracker"]["input_tokens"] == 9


# ---------------------------------------------------------------------------
# Mock pipeline
# ---------------------------------------------------------------------------


async def test_mock_pipeline_deadlock_incident(settings: Settings):
    """[Unit] concurrency: a resolved deadlock panel surfaces the specialist turn.

    Scenario: a scripted os-kernel/concurrency/skeptic sequence runs a deadlock
    incident through the panel.

    Boundaries: the AI backend is mocked; end-to-end panel wiring is under test.

    On failure, first check: the concurrency specialist's turn must appear in the
    resolved panel's dialogue.
    """
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
