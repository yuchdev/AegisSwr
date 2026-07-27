"""Unit tests for :class:`~aegis_swr.agents.forensic.memory_forensics.MemoryForensicsAgent`."""

from __future__ import annotations

import json
from typing import Any, Optional

from aegis_swr.agents.base import AgentSpec, SkepticAgent
from aegis_swr.agents.forensic.memory_forensics import _SYSTEM_PROMPT, MemoryForensicsAgent
from aegis_swr.agents.panel import resolve_panel
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    InvestigationState,
    MemoryForensicsOutput,
    OSKernelOutput,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

# ---------------------------------------------------------------------------
# State / response helpers
# ---------------------------------------------------------------------------


def _state(
    *,
    raw_text_excerpt: str = "",
    stack_frames: Optional[list[dict[str, Any]]] = None,
    round_number: int = 1,
    latest_arbiter_feedback: Optional[list[str]] = None,
) -> InvestigationState:
    state: InvestigationState = {
        "incident_id": "test-id",
        "incident_brief": {
            "fault_class": "memory_access_violation",
            "faulting_module": "db_writer",
            "stack_frames": stack_frames or [],
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


def _mem_output(
    *,
    confidence: float = 0.82,
    corruption_signatures: Optional[list[str]] = None,
    hypotheses: Optional[list[Hypothesis]] = None,
    heap_state: Optional[str] = None,
) -> MemoryForensicsOutput:
    return MemoryForensicsOutput(
        hypotheses=hypotheses
        if hypotheses is not None
        else [Hypothesis(root_cause="Use-after-free in serialize()", confidence=confidence)],
        confidence_score=confidence,
        corruption_signatures=corruption_signatures or [],
        heap_state=heap_state,
    )


def _last_context(mock: MockAIBackend) -> str:
    """Return the JSON user-content string of the most recent generate() call."""
    return mock.calls[-1]["messages"][0]["content"]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def test_system_prompt_contains_specialism_keywords():
    """[Unit] memory: the system prompt names the specialism and output schema."""
    for keyword in ["heap", "use-after-free", "fill", "0xBAADF00D", "MemoryForensicsOutput"]:
        assert keyword in _SYSTEM_PROMPT


def test_system_prompt_does_not_instruct_shell_or_eval():
    """[Unit] memory: the prompt never instructs shell/eval/exec/subprocess use."""
    for forbidden in ["shell", "eval", "exec(", "subprocess"]:
        assert forbidden not in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# ClassVar identity (contract C2)
# ---------------------------------------------------------------------------


def test_classvar_agent_key():
    assert MemoryForensicsAgent.agent_key == "memory_forensics"


def test_classvar_category():
    assert MemoryForensicsAgent.category == "forensic"


def test_classvar_display_name():
    assert MemoryForensicsAgent.display_name == "Memory Forensics Agent"


def test_authoritative_fault_classes():
    """[Unit] memory: authoritative for the three memory-domain fault classes."""
    assert MemoryForensicsAgent.authoritative_fault_classes == frozenset(
        {
            FaultClass.MEMORY_ACCESS_VIOLATION,
            FaultClass.NULL_POINTER_DEREFERENCE,
            FaultClass.USE_AFTER_FREE,
        }
    )


# ---------------------------------------------------------------------------
# Fill-pattern pre-check
# ---------------------------------------------------------------------------


async def test_fill_pattern_precheck_detects_baadf00d(settings: Settings):
    """[Unit] memory: a 0xBAADF00D in raw text reaches the LLM context pre-call."""
    ai = MockAIBackend(responses=[_mem_output(corruption_signatures=[])])
    agent = MemoryForensicsAgent(ai, settings)
    state = _state(raw_text_excerpt="crash near 0xBAADF00D detected")

    turn = await agent.run(state)

    assert turn.hypotheses  # LLM output propagated
    assert "0xBAADF00D" in _last_context(ai)


async def test_fill_pattern_precheck_multiple_sentinels(settings: Settings):
    """[Unit] memory: sentinels inside stack frames are detected and passed along."""
    ai = MockAIBackend(responses=[_mem_output(corruption_signatures=[])])
    agent = MemoryForensicsAgent(ai, settings)
    frames = [
        {"frame_number": 0, "module": "a", "raw": "value 0xFEEEFEEE here"},
        {"frame_number": 1, "module": "b", "raw": "and 0xDDDDDDDD there"},
    ]
    state = _state(stack_frames=frames)

    await agent.run(state)

    context = _last_context(ai)
    assert "0xFEEEFEEE" in context
    assert "0xDDDDDDDD" in context


async def test_fill_pattern_precheck_merges_with_llm_output(settings: Settings):
    """[Unit] memory: pre-check + LLM signatures are merged, neither discarded."""
    ai = MockAIBackend(responses=[_mem_output(corruption_signatures=["0xABABABAB"])])
    agent = MemoryForensicsAgent(ai, settings)
    state = _state(raw_text_excerpt="heap tell 0xBAADF00D")

    turn = await agent.run(state)

    assert "0xBAADF00D" in turn.message  # deterministic pre-check retained
    assert "0xABABABAB" in turn.message  # LLM-surfaced signature retained


async def test_fill_pattern_precheck_clean_brief_no_signatures(settings: Settings):
    """[Unit] memory: a brief with no sentinels yields no spurious signatures."""
    ai = MockAIBackend(responses=[_mem_output(corruption_signatures=[])])
    agent = MemoryForensicsAgent(ai, settings)
    state = _state(raw_text_excerpt="ordinary log line, nothing suspicious")

    turn = await agent.run(state)

    assert json.loads(_last_context(ai))["pre_detected_signatures"] == []
    assert "Detected corruption signatures" not in turn.message


# ---------------------------------------------------------------------------
# run() output shape
# ---------------------------------------------------------------------------


async def test_run_returns_agent_turn(settings: Settings):
    ai = MockAIBackend(responses=[_mem_output()])
    turn = await MemoryForensicsAgent(ai, settings).run(_state())
    assert isinstance(turn, AgentTurn)


async def test_run_agent_name_matches_display_name(settings: Settings):
    ai = MockAIBackend(responses=[_mem_output()])
    turn = await MemoryForensicsAgent(ai, settings).run(_state())
    assert turn.agent == "Memory Forensics Agent"
    assert turn.agent_key == "memory_forensics"


async def test_run_confidence_score_propagated(settings: Settings):
    ai = MockAIBackend(responses=[_mem_output(confidence=0.73)])
    turn = await MemoryForensicsAgent(ai, settings).run(_state())
    assert turn.confidence_score == 0.73


async def test_run_hypotheses_propagated(settings: Settings):
    hyps = [
        Hypothesis(root_cause="double free", confidence=0.7),
        Hypothesis(root_cause="buffer overrun", confidence=0.6),
    ]
    ai = MockAIBackend(responses=[_mem_output(hypotheses=hyps)])
    turn = await MemoryForensicsAgent(ai, settings).run(_state())
    assert len(turn.hypotheses) == 2


async def test_run_accumulates_tokens(settings: Settings):
    ai = MockAIBackend(responses=[_mem_output()], usage={"input_tokens": 11, "output_tokens": 4})
    state = _state()
    await MemoryForensicsAgent(ai, settings).run(state)
    assert state["token_tracker"]["input_tokens"] == 11
    assert state["token_tracker"]["output_tokens"] == 4


async def test_run_incorporates_skeptic_corrections(settings: Settings):
    """[Unit] memory: prior-round arbiter corrections reach the LLM context."""
    ai = MockAIBackend(responses=[_mem_output()])
    agent = MemoryForensicsAgent(ai, settings)
    state = _state(round_number=2, latest_arbiter_feedback=["re-examine heap header"])

    await agent.run(state)

    context = json.loads(_last_context(ai))
    assert context["skeptic_corrections_from_previous_round"] == ["re-examine heap header"]


# ---------------------------------------------------------------------------
# Mock pipeline
# ---------------------------------------------------------------------------


async def test_mock_pipeline_memory_access_violation(settings: Settings):
    """[Unit] memory: a resolved memory panel runs os_kernel, memory_forensics, skeptic."""
    responses: list[Any] = [
        OSKernelOutput(
            exception_summary=ExceptionSummary(
                fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
                exception_code_raw="0xc0000005",
                exception_address="0x00007ff8016a1c3f",
                interpretation="AV dereferencing a freed pointer.",
            ),
            hypotheses=[Hypothesis(root_cause="UAF in serialize()", confidence=0.85)],
            confidence_score=0.85,
        ),
        _mem_output(confidence=0.82),
        SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH),
    ]
    ai = MockAIBackend(responses=responses)
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="memory_forensics"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = resolve_panel(specs, ai, settings)

    assert sum(isinstance(a, MemoryForensicsAgent) for a in panel) == 1
    assert isinstance(panel[-1], SkepticAgent)  # arbiter last
    assert not isinstance(panel[0], SkepticAgent)

    state = _state()
    turns = [await agent.run(state) for agent in panel]

    assert [t.agent for t in turns] == [
        "OS Kernel Agent",
        "Memory Forensics Agent",
        "Skeptic Agent",
    ]
    assert all(isinstance(t, AgentTurn) for t in turns)
