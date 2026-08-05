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
    """Build an investigation state seeded with a resource-exhaustion brief."""
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
    """Build a canned resource-exhaustion output with the given fields."""
    return ResourceExhaustionOutput(
        hypotheses=hypotheses
        if hypotheses is not None
        else [Hypothesis(root_cause="handle leak in accept loop", confidence=confidence)],
        confidence_score=confidence,
        exhausted_resource=exhausted_resource,
        leak_indicators=leak_indicators or [],
    )


def _last_context(mock: MockAIBackend) -> dict[str, Any]:
    """Return the JSON-decoded context of the mock backend's most recent call."""
    return json.loads(mock.calls[-1]["messages"][0]["content"])


# ---------------------------------------------------------------------------
# ClassVars
# ---------------------------------------------------------------------------


def test_classvars():
    """[Unit] resource: the agent advertises its key, category, and display name.

    Scenario: the class-level metadata is read.

    Boundaries: static class metadata only.

    On failure, first check: key ``resource_exhaustion``, category ``forensic``, and
    the display name must all match.
    """
    assert ResourceExhaustionAgent.agent_key == "resource_exhaustion"
    assert ResourceExhaustionAgent.category == "forensic"
    assert ResourceExhaustionAgent.display_name == "Resource Exhaustion Agent"


def test_authoritative_fault_classes():
    """[Unit] resource: the agent claims its authoritative fault classes.

    Scenario: the class-level ``authoritative_fault_classes`` is read.

    Boundaries: static class metadata only.

    On failure, first check: the set must be resource-exhaustion, stack-overflow, and
    deadlock.
    """
    assert ResourceExhaustionAgent.authoritative_fault_classes == frozenset(
        {FaultClass.RESOURCE_EXHAUSTION, FaultClass.STACK_OVERFLOW, FaultClass.DEADLOCK}
    )


# ---------------------------------------------------------------------------
# Deterministic pre-check
# ---------------------------------------------------------------------------


def test_precheck_detects_oom():
    """[Unit] resource: the leak pre-check flags an out-of-memory log line.

    Scenario: a log summary containing ``OutOfMemoryError`` is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: an out-of-memory indicator must be returned.
    """
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "java.lang.OutOfMemoryError: GC overhead limit exceeded"}
    )
    assert any("out of memory" in i.lower() or "oom" in i.lower() for i in indicators)


def test_precheck_detects_too_many_open_files():
    """[Unit] resource: the leak pre-check flags a too-many-open-files error.

    Scenario: a raw excerpt containing ``too many open files`` is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: an open-files indicator must be returned.
    """
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"raw_text_excerpt": "accept: too many open files (errno 24)"}
    )
    assert any("open files" in i.lower() for i in indicators)


def test_precheck_detects_win32_resource_error():
    """[Unit] resource: the leak pre-check flags a Win32 resource error.

    Scenario: a raw excerpt containing ``ERROR_NO_SYSTEM_RESOURCES`` is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: at least one indicator must be returned.
    """
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"raw_text_excerpt": "CreateHandle failed: ERROR_NO_SYSTEM_RESOURCES"}
    )
    assert indicators


def test_precheck_detects_thread_exhaustion():
    """[Unit] resource: the leak pre-check flags thread-pool exhaustion.

    Scenario: a log summary describing an exhausted thread pool is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: a thread-related indicator must be returned.
    """
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "thread pool exhausted: limit 64 workers reached"}
    )
    assert any("thread" in i.lower() for i in indicators)


def test_precheck_detects_connection_pool():
    """[Unit] resource: the leak pre-check flags connection-pool exhaustion.

    Scenario: a log summary describing a full connection pool is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: at least one indicator must be returned.
    """
    indicators = ResourceExhaustionAgent._extract_leak_indicators(
        {"log_summary": "ConnectionPool timeout: pool full (100/100)"}
    )
    assert indicators


def test_precheck_empty_brief():
    """[Unit] resource: the leak pre-check returns nothing for an empty brief.

    Scenario: an empty brief dict is scanned.

    Boundaries: exercises the pure ``_extract_leak_indicators`` helper only.

    On failure, first check: the result must be an empty list.
    """
    assert ResourceExhaustionAgent._extract_leak_indicators({}) == []


def test_precheck_never_raises():
    """[Unit] resource: the leak pre-check tolerates non-string brief values.

    Scenario: a numeric ``log_summary`` value is scanned.

    Boundaries: exercises the helper's defensive input handling.

    On failure, first check: the helper must return a list without raising.
    """
    result = ResourceExhaustionAgent._extract_leak_indicators({"log_summary": 12345})
    assert isinstance(result, list)


def test_precheck_trims_long_indicators():
    """[Unit] resource: the leak pre-check clamps indicator length.

    Scenario: a very long log line surrounding a match is scanned.

    Boundaries: exercises the helper's snippet-trimming rule.

    On failure, first check: every returned indicator must be at most 200 chars.
    """
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
    """[Unit] resource: the system prompt covers core resource vocabulary.

    Scenario: the module system prompt is scanned for keywords.

    Boundaries: static prompt-content check only.

    On failure, first check: handle, file-descriptor, thread, memory, the schema name,
    and ``log_summary`` must all appear.
    """
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
    """[Unit] resource: ``run`` returns a well-formed agent turn.

    Scenario: the agent runs against a scripted output.

    Boundaries: the AI backend is mocked; only turn assembly is asserted.

    On failure, first check: the result must be an ``AgentTurn`` with the agent name
    and key set.
    """
    ai = MockAIBackend(responses=[_output(confidence=0.72)])
    turn = await ResourceExhaustionAgent(ai, settings).run(_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "Resource Exhaustion Agent"
    assert turn.agent_key == "resource_exhaustion"


async def test_run_merges_precheck_into_turn(settings: Settings):
    """[Unit] resource: pre-check indicators reach the LLM context on ``run``.

    Scenario: the excerpt names an OOM error and the model returns no indicators.

    Boundaries: the AI backend is mocked; the deterministic merge is under test.

    On failure, first check: ``precheck_leak_indicators`` must be present and non-empty
    in the LLM context.
    """
    ai = MockAIBackend(responses=[_output(leak_indicators=[])])
    agent = ResourceExhaustionAgent(ai, settings)
    turn = await agent.run(_state(log_summary="java.lang.OutOfMemoryError: heap"))
    assert turn.hypotheses
    assert "precheck_leak_indicators" in _last_context(ai)
    assert _last_context(ai)["precheck_leak_indicators"]  # non-empty


async def test_run_includes_log_summary_in_context(settings: Settings):
    """[Unit] resource: ``run`` forwards the log summary into the LLM context.

    Scenario: the state carries a handle-count log summary.

    Boundaries: the AI backend is mocked; only context assembly is asserted.

    On failure, first check: the LLM context ``log_summary`` must equal the state value.
    """
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(log_summary="handle count: 62100 (threshold 60000)"))
    ctx = _last_context(ai)
    assert ctx["log_summary"] == "handle count: 62100 (threshold 60000)"


async def test_run_includes_log_summary_key_even_when_none(settings: Settings):
    """[Unit] resource: the log-summary key is always present, even when None.

    Scenario: the state omits a log summary entirely.

    Boundaries: the AI backend is mocked; only context shape is asserted.

    On failure, first check: the LLM context must contain a ``log_summary`` key set to
    ``None``.
    """
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(include_log_summary=False))
    ctx = _last_context(ai)
    assert "log_summary" in ctx
    assert ctx["log_summary"] is None


async def test_run_incorporates_skeptic_corrections(settings: Settings):
    """[Unit] resource: round-2 runs forward the prior arbiter corrections.

    Scenario: the agent runs on round 2 with arbiter feedback in state.

    Boundaries: the AI backend is mocked; only context assembly is asserted.

    On failure, first check: the LLM context must carry
    ``skeptic_corrections_from_previous_round``.
    """
    ai = MockAIBackend(responses=[_output()])
    agent = ResourceExhaustionAgent(ai, settings)
    await agent.run(_state(round_number=2, latest_arbiter_feedback=["check handle leak in thread X"]))
    ctx = _last_context(ai)
    assert ctx["skeptic_corrections_from_previous_round"] == ["check handle leak in thread X"]


async def test_run_confidence_propagated(settings: Settings):
    """[Unit] resource: ``run`` propagates the model's confidence to the turn.

    Scenario: the scripted output reports 0.85 confidence.

    Boundaries: the AI backend is mocked; only confidence propagation is asserted.

    On failure, first check: the turn's confidence score must equal 0.85.
    """
    ai = MockAIBackend(responses=[_output(confidence=0.85)])
    turn = await ResourceExhaustionAgent(ai, settings).run(_state())
    assert turn.confidence_score == 0.85
