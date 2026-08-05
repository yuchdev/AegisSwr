"""Integration tests for the dynamic-panel orchestrator redesign (Phase 6).

Covers the verification gates from the design document's "Verification" section:

1. Back-compat equivalence: stream_events() with the default 4-agent auto-
   selected panel produces the same discussion order and report values as the
   pre-refactor implementation, and the new PanelResolved event is published
   with correct agent roles.

2. Variable-panel: an explicit 5-agent panel (one custom test-double beyond the
   four built-in agents) runs in descending-priority order, an explicit
   per-incident weight override beats the agent's own declared default_weight,
   and _build_report's role/capability-driven synthesis extracts the
   probabilistic fix without any display-name string.

3. Recursion-limit: a high max_debate_rounds value that would exhaust LangGraph's
   default 25-step recursion limit without the (len(panel)+2)*rounds+5 budget
   formula completes successfully and returns a valid HITL report.

All tests run fully in-process with MockAIBackend; no network, subprocess, or
file-system side effects are introduced.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional

import pytest

from aegis_swr.agents import registry as agent_registry_module
from aegis_swr.agents.base import AgentSpec, BaseAgent
from aegis_swr.config.settings import Settings
from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    InvestigationCompleted,
    PanelResolved,
)
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    CodeAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    InvestigationState,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    RCAReport,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

# ---------------------------------------------------------------------------
# Test-double: a synthetic fifth investigator for the variable-panel test.
#
# Intentionally does NOT call the AI backend so that the MockAIBackend's
# scripted-response list stays predictable regardless of panel ordering.
# ---------------------------------------------------------------------------


class _ExtraAnalystAgent(BaseAgent):
    """Synthetic fifth investigator registered only for the variable-panel test.

    Returns a deterministic turn (confidence_score=0.50) without calling the
    AI backend.  This lets the test assert exact consensus-score arithmetic
    while keeping the MockAIBackend response list small and ordered.
    """

    agent_key: ClassVar[str] = "extra_analyst"
    display_name: ClassVar[str] = "Extra Analyst"
    category: ClassVar[str] = "forensic"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.20

    @property
    def system_prompt(self) -> str:
        """Helper that provides system prompt for the orchestrator dynamic panel tests."""
        return "extra analyst system prompt"

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Return a hardcoded turn; no AI backend call is made."""
        round_num = state.get("round_number", 1)
        return self.make_turn(
            turn_number=round_num,
            message="Extra analyst contribution.",
            confidence_score=0.50,
            hypotheses=[Hypothesis(root_cause="UAF in serialize()", confidence=0.50)],
        )


# ---------------------------------------------------------------------------
# Scripted response constructors shared across tests
# ---------------------------------------------------------------------------


def _os(confidence: float = 0.90) -> OSKernelOutput:
    """Helper that provides os for the orchestrator dynamic panel tests."""
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


def _code(confidence: float = 0.90, *, with_fix: bool = False) -> CodeAnalystOutput:
    """Helper that provides code for the orchestrator dynamic panel tests."""
    fix_text: Optional[str] = "guard the pointer with a null check" if with_fix else None
    return CodeAnalystOutput(
        rca=RCAHypothesis(
            root_cause="UAF in serialize()",
            faulting_module="db_writer",
            confidence=confidence,
        ),
        confidence_score=confidence,
        probabilistic_fix=fix_text,
        fix_language="python" if with_fix else None,
    )


def _historian(confidence: float = 0.90) -> LogHistorianOutput:
    """Helper that provides historian for the orchestrator dynamic panel tests."""
    return LogHistorianOutput(
        confidence_adjustment=0.0,
        updated_confidence=confidence,
        history_note="No recurrence found.",
    )


def _skeptic_yes(confidence: ConfidenceLevel = ConfidenceLevel.HIGH) -> SkepticVerdict:
    """Helper that provides skeptic yes for the orchestrator dynamic panel tests."""
    return SkepticVerdict(confirmed=True, confidence=confidence)


def _skeptic_no() -> SkepticVerdict:
    """Helper that provides skeptic no for the orchestrator dynamic panel tests."""
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["module not confirmed in stack"],
        corrections=["re-examine the top frames"],
    )


def _log_only_source() -> IncidentSource:
    """LOG_FORENSICS source with no dump; produces a brief with fault_class=None."""
    return IncidentSource(mode=IncidentMode.LOG_FORENSICS)


# ---------------------------------------------------------------------------
# Test 1: back-compat equivalence via stream_events()
# ---------------------------------------------------------------------------


async def test_stream_events_default_panel_preserves_prerefactor_order_and_publishes_panel_resolved(
    settings: Settings,
) -> None:
    """[Integration] orchestrator dynamic panel: The default 4-agent auto-selected panel is byte-identical to the pre-refactor chain.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the default 4-agent auto-selected panel is byte-identical to the pre-refactor chain.
    """
    responses: list[Any] = [
        # Round 1: arbiter rejects, providing explicit challenges.
        _os(0.90),
        _code(0.90),
        _historian(0.90),
        _skeptic_no(),
        # Round 2: all agents at high confidence; arbiter confirms.
        _os(0.90),
        _code(0.90),
        _historian(0.90),
        _skeptic_yes(),
    ]
    orch = Orchestrator(settings=settings, ai_backend=MockAIBackend(responses=responses))

    events: list[Any] = []
    async for event in orch.stream_events(_log_only_source()):
        events.append(event)

    event_types = [type(e).__name__ for e in events]

    # The stream must start with InvestigationStarted and end with
    # InvestigationCompleted (not HumanInputRequired).
    assert event_types[0] == "InvestigationStarted", f"First event was: {event_types[0]}"
    assert event_types[-1] == "InvestigationCompleted", f"Last event was: {event_types[-1]}"

    # EvidenceExtracted and PanelResolved must precede any AgentSpoke event.
    assert "EvidenceExtracted" in event_types
    assert "PanelResolved" in event_types
    evidence_idx = event_types.index("EvidenceExtracted")
    panel_idx = event_types.index("PanelResolved")
    first_spoke_idx = next(i for i, t in enumerate(event_types) if t == "AgentSpoke")
    assert evidence_idx < panel_idx < first_spoke_idx, (
        f"Event order wrong: EvidenceExtracted={evidence_idx}, "
        f"PanelResolved={panel_idx}, first AgentSpoke={first_spoke_idx}"
    )

    # PanelResolved carries the four default agents with correct roles.
    panel_event: PanelResolved = next(e for e in events if isinstance(e, PanelResolved))
    assert len(panel_event.panel) == 4
    panel_keys = [d.node_name.replace("_node", "") for d in panel_event.panel]
    # Investigators come first in the resolved order, arbiter last.
    assert panel_keys == ["os_kernel", "code_analyst", "log_historian", "skeptic"]
    roles = [d.role for d in panel_event.panel]
    assert roles == [
        AgentRole.INVESTIGATOR,
        AgentRole.INVESTIGATOR,
        AgentRole.INVESTIGATOR,
        AgentRole.ARBITER,
    ]

    # Exactly 8 AgentSpoke events: 4 agents × 2 rounds.
    spoke_events = [e for e in events if isinstance(e, AgentSpoke)]
    assert len(spoke_events) == 8, f"Expected 8 AgentSpoke events, got {len(spoke_events)}"

    # Both rounds must fire in the historical [os_kernel, code_analyst,
    # log_historian, skeptic] chain, preserving the pre-refactor debate order.
    round1_keys = [e.turn.agent_key for e in spoke_events[:4]]
    round2_keys = [e.turn.agent_key for e in spoke_events[4:]]
    assert round1_keys == ["os_kernel", "code_analyst", "log_historian", "skeptic"], (
        f"Round-1 agent order mismatch: {round1_keys}"
    )
    assert round2_keys == ["os_kernel", "code_analyst", "log_historian", "skeptic"], (
        f"Round-2 agent order mismatch: {round2_keys}"
    )

    # Exactly 2 ConsensusEvaluated events (one emitted after each arbiter turn).
    cs_events = [e for e in events if isinstance(e, ConsensusEvaluated)]
    assert len(cs_events) == 2, f"Expected 2 ConsensusEvaluated events, got {len(cs_events)}"

    # Final report assertions.
    completed: InvestigationCompleted = next(e for e in events if isinstance(e, InvestigationCompleted))
    report: RCAReport = completed.report

    assert report.consensus_rounds == 2
    assert report.hitl_request is None
    assert report.root_cause == "UAF in serialize()"
    assert report.confidence_score == pytest.approx(0.90)
    assert report.confidence_level == ConfidenceLevel.HIGH

    # Round-1 arbiter's challenges must appear in the report - extracted by
    # AgentRole.ARBITER lookup on agent_key, not by 'Skeptic Agent' name match.
    assert "module not confirmed in stack" in report.skeptic_challenges, (
        f"Expected arbiter challenge in report.skeptic_challenges; got: {report.skeptic_challenges}"
    )


# ---------------------------------------------------------------------------
# Test 2: variable-panel - explicit 5-agent panel with mixed weight tiers
# ---------------------------------------------------------------------------


async def test_explicit_five_agent_panel_respects_priority_order_and_weight_tiers(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[Integration] orchestrator dynamic panel: An explicit 5-agent panel runs in priority order with two-tier weight resolution.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an explicit 5-agent panel runs in priority order with two-tier weight resolution.
    """
    monkeypatch.setitem(
        agent_registry_module.AGENT_REGISTRY,
        _ExtraAnalystAgent.agent_key,
        _ExtraAnalystAgent,
    )

    # Lower threshold so the computed CS=0.75 triggers convergence.
    low_threshold_settings = Settings(core={"consensus_threshold": 0.70})

    # Explicit specs: extra_analyst gets a tier-1 explicit weight override; all
    # real agents fall to tier-2 (their own class-declared default_weight).
    explicit_specs = [
        AgentSpec(agent_key="extra_analyst", priority=5, weight=0.6),
        AgentSpec(agent_key="os_kernel", priority=4),
        AgentSpec(agent_key="code_analyst", priority=3),
        AgentSpec(agent_key="log_historian", priority=2),
        AgentSpec(agent_key="skeptic"),
    ]

    # After priority-sort the debate order is: extra_analyst(5) → os_kernel(4)
    # → code_analyst(3) → log_historian(2) → skeptic(arbiter/last).
    # extra_analyst does NOT call the AI backend (hardcoded turn), so only
    # 4 scripted responses are needed for the 4 real agents.
    responses: list[Any] = [
        _os(0.90),
        _code(0.90, with_fix=True),
        _historian(0.90),
        _skeptic_yes(),
    ]

    orch = Orchestrator(
        settings=low_threshold_settings,
        ai_backend=MockAIBackend(responses=responses),
        explicit_specs=explicit_specs,
    )
    report = await orch.run(_log_only_source())

    assert isinstance(report, RCAReport)
    assert report.hitl_request is None, "Unexpected HITL escalation"

    # All 5 agents must have spoken exactly once.
    assert len(report.agent_dialogue) == 5, (
        f"Expected 5 turns; got {len(report.agent_dialogue)}: {[t.agent_key for t in report.agent_dialogue]}"
    )

    turn_keys = [t.agent_key for t in report.agent_dialogue]

    # extra_analyst (priority=5) must be the first speaker.
    assert turn_keys[0] == "extra_analyst", f"extra_analyst (priority=5) must speak first; order was: {turn_keys}"
    # os_kernel (priority=4) must follow.
    assert turn_keys[1] == "os_kernel", f"Expected os_kernel second; order was: {turn_keys}"
    assert turn_keys[2] == "code_analyst"
    assert turn_keys[3] == "log_historian"
    # The arbiter must always be last regardless of its priority.
    assert turn_keys[-1] == "skeptic", f"skeptic (ARBITER) must always be last; order was: {turn_keys}"

    # Probabilistic fix extracted via code_analyst.contributes_fix, not by name.
    assert report.probabilistic_fix == "guard the pointer with a null check", (
        f"Expected fix extracted from code_analyst; got: {report.probabilistic_fix!r}"
    )

    # Verify the two-tier weight precedence took effect by asserting the
    # consensus_score matches the analytically computed expected value.
    # Scores: extra=0.50 (hardcoded), all others 0.90.
    # Weights: extra=0.60 (tier-1 explicit override), os=0.35, code=0.35,
    #          historian=0.17, skeptic=0.13 (all tier-2 agent-declared defaults).
    _weights = {
        "extra_analyst": 0.60,
        "os_kernel": 0.35,
        "code_analyst": 0.35,
        "log_historian": 0.17,
        "skeptic": 0.13,
    }
    _scores = {
        "extra_analyst": 0.50,
        "os_kernel": 0.90,
        "code_analyst": 0.90,
        "log_historian": 0.90,
        "skeptic": 0.90,
    }
    expected_cs = sum(_weights[k] * _scores[k] for k in _weights) / sum(_weights.values())
    assert report.confidence_score == pytest.approx(expected_cs, abs=1e-3), (
        f"consensus_score={report.confidence_score:.4f} does not match "
        f"expected {expected_cs:.4f} — weight-tier resolution may be incorrect"
    )


# ---------------------------------------------------------------------------
# Test 3: recursion-limit fix prevents GraphRecursionError at high round counts
# ---------------------------------------------------------------------------


async def test_large_max_debate_rounds_completes_without_graph_recursion_error(
    settings: Settings,
) -> None:
    """[Integration] orchestrator dynamic panel: The (len(panel)+2)*max_rounds+5 budget prevents GraphRecursionError.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the (len(panel)+2)*max_rounds+5 budget prevents GraphRecursionError.
    """
    max_rounds = 7
    # Settings override: only max_debate_rounds changes; other core defaults hold.
    high_round_settings = Settings(core={"max_debate_rounds": max_rounds})

    # All agents return confidence well below the arbiter confirmation threshold
    # (0.65) and the consensus threshold (0.85), guaranteeing that all 7 rounds
    # run to exhaustion before the router escalates to HITL.
    low = 0.30
    responses: list[Any] = []
    for _ in range(max_rounds):
        responses.extend([_os(low), _code(low), _historian(low), _skeptic_no()])

    orch = Orchestrator(
        settings=high_round_settings,
        ai_backend=MockAIBackend(responses=responses),
    )

    # Must complete without raising langgraph.errors.GraphRecursionError.
    report = await orch.run(_log_only_source())

    assert isinstance(report, RCAReport), f"Expected RCAReport, got {type(report)}"
    assert report.hitl_request is not None, (
        "Expected HITL escalation after all non-converging rounds; report.hitl_request is None"
    )
    assert report.consensus_rounds == max_rounds, (
        f"Expected consensus_rounds={max_rounds}; got {report.consensus_rounds}"
    )
