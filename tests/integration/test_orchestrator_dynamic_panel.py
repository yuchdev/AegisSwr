"""Integration tests for the dynamic-panel orchestrator redesign (Phase 6).

Covers the four verification gates from the design document's "Verification"
section, plus a config-artifact check that the reshaped agents.example.json
parses correctly through Settings:

1. Config shape: agents.example.json uses the new {'weights':…,'panel':…}
   envelope and all numeric values are byte-identical to the pre-refactor matrix.

2. Back-compat equivalence: stream_events() with the default 4-agent auto-
   selected panel produces the same discussion order and report values as the
   pre-refactor implementation, and the new PanelResolved event is published
   with correct agent roles.

3. Variable-panel: an explicit 5-agent panel (one custom test-double beyond the
   four built-in agents) runs in descending-priority order, weight tier-1
   explicit beats tier-2 curated, and _build_report's role/capability-driven
   synthesis extracts the probabilistic fix without any display-name string.

4. Recursion-limit: a high max_debate_rounds value that would exhaust LangGraph's
   default 25-step recursion limit without the (len(panel)+2)*rounds+5 budget
   formula completes successfully and returns a valid HITL report.

All tests run fully in-process with MockAIBackend; no network, subprocess, or
file-system side effects are introduced beyond reading the example config file.
"""

from __future__ import annotations

import json
from pathlib import Path
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

_REPO_ROOT = Path(__file__).parent.parent.parent
_AGENTS_EXAMPLE = _REPO_ROOT / "agents.example.json"


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

    @property
    def system_prompt(self) -> str:
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
    return LogHistorianOutput(
        confidence_adjustment=0.0,
        updated_confidence=confidence,
        history_note="No recurrence found.",
    )


def _skeptic_yes(confidence: ConfidenceLevel = ConfidenceLevel.HIGH) -> SkepticVerdict:
    return SkepticVerdict(confirmed=True, confidence=confidence)


def _skeptic_no() -> SkepticVerdict:
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
# Test 1: agents.example.json config-artifact shape verification
# ---------------------------------------------------------------------------


def test_agents_example_json_loads_with_new_nested_shape(settings: Settings) -> None:
    """The reshaped agents.example.json uses the new {'weights':…,'panel':…} top-level envelope.

    Loads agents.example.json directly (bypassing the autouse isolation fixture
    which replaces _read_json_object with a no-op) and passes the parsed data
    through Settings() as init kwargs - the highest-precedence source, which
    wins over the JSON settings source. Asserts:

    - The file has exactly the two top-level keys 'weights' and 'panel', not
      the old flat fault-class-at-root shape.
    - Every fault class's numeric weights are byte-identical to the pre-refactor
      matrix (same floats, just nested under 'weights').
    - The 'panel' section seeds agent_panel.default_panel with the four built-in
      keys and agent_panel.per_fault_class is empty.

    This is the config-artifact gate for Phase 6 Step 1.
    """
    raw = json.loads(_AGENTS_EXAMPLE.read_text(encoding="utf-8"))

    # The reshaped file must have exactly these two top-level keys.
    assert set(raw.keys()) == {"weights", "panel"}, (
        f"agents.example.json must have exactly top-level keys 'weights' and 'panel'; found: {sorted(raw.keys())}"
    )

    # The old flat fault-class keys must NOT appear at the top level.
    assert "memory_access_violation" not in raw, (
        "agents.example.json must not use the old flat shape where fault-class names appear directly at the top level"
    )

    # Parse via Settings init kwargs (highest-precedence source; the autouse
    # _isolate_runtime_config fixture only patches _read_json_object, not init).
    loaded = Settings(agent_weights=raw["weights"], agent_panel=raw["panel"])

    # Spot-check all 10 fault classes with representative keys.
    mav = loaded.agent_weights.memory_access_violation.weights
    assert mav["os_kernel"] == pytest.approx(0.40)
    assert mav["code_analyst"] == pytest.approx(0.35)
    assert mav["log_historian"] == pytest.approx(0.15)
    assert mav["skeptic"] == pytest.approx(0.10)

    npd = loaded.agent_weights.null_pointer_dereference.weights
    assert npd["os_kernel"] == pytest.approx(0.40)
    assert npd["code_analyst"] == pytest.approx(0.35)

    uaf = loaded.agent_weights.use_after_free.weights
    assert uaf["os_kernel"] == pytest.approx(0.35)
    assert uaf["code_analyst"] == pytest.approx(0.40)
    assert uaf["log_historian"] == pytest.approx(0.15)
    assert uaf["skeptic"] == pytest.approx(0.10)

    stack = loaded.agent_weights.stack_overflow.weights
    assert stack["os_kernel"] == pytest.approx(0.45)
    assert stack["code_analyst"] == pytest.approx(0.30)
    assert stack["log_historian"] == pytest.approx(0.10)
    assert stack["skeptic"] == pytest.approx(0.15)

    idz = loaded.agent_weights.integer_divide_by_zero.weights
    assert idz["os_kernel"] == pytest.approx(0.35)
    assert idz["code_analyst"] == pytest.approx(0.40)
    assert idz["log_historian"] == pytest.approx(0.10)
    assert idz["skeptic"] == pytest.approx(0.15)

    dl = loaded.agent_weights.deadlock.weights
    assert dl["os_kernel"] == pytest.approx(0.35)
    assert dl["code_analyst"] == pytest.approx(0.30)
    assert dl["log_historian"] == pytest.approx(0.20)
    assert dl["skeptic"] == pytest.approx(0.15)

    af = loaded.agent_weights.assertion_failure.weights
    assert af["os_kernel"] == pytest.approx(0.25)
    assert af["code_analyst"] == pytest.approx(0.45)

    re_entry = loaded.agent_weights.resource_exhaustion.weights
    assert re_entry["os_kernel"] == pytest.approx(0.35)
    assert re_entry["code_analyst"] == pytest.approx(0.25)
    assert re_entry["log_historian"] == pytest.approx(0.30)
    assert re_entry["skeptic"] == pytest.approx(0.10)

    ue = loaded.agent_weights.unhandled_exception.weights
    assert ue["os_kernel"] == pytest.approx(0.30)
    assert ue["code_analyst"] == pytest.approx(0.35)

    unk = loaded.agent_weights.unknown.weights
    assert unk["os_kernel"] == pytest.approx(0.30)
    assert unk["code_analyst"] == pytest.approx(0.35)
    assert unk["log_historian"] == pytest.approx(0.20)
    assert unk["skeptic"] == pytest.approx(0.15)

    # Panel section wires the default roster and leaves per_fault_class empty.
    assert loaded.agent_panel.default_panel == [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "skeptic",
    ]
    assert loaded.agent_panel.per_fault_class == {}


# ---------------------------------------------------------------------------
# Test 2: back-compat equivalence via stream_events()
# ---------------------------------------------------------------------------


async def test_stream_events_default_panel_preserves_prerefactor_order_and_publishes_panel_resolved(
    settings: Settings,
) -> None:
    """The default 4-agent auto-selected panel is byte-identical to the pre-refactor chain.

    Exercises stream_events() end-to-end with a 2-round debate (round 1 the
    arbiter rejects with explicit challenges, round 2 it confirms at HIGH
    confidence). This is more than a repackaged unit test: it exercises the
    stream_events() path (not just run()), verifies the new PanelResolved event
    introduced by this redesign is wired and carries correct metadata, and
    confirms that the role-driven _build_report extracts skeptic_challenges from
    round 1's arbiter turn without any display-name branch.

    Assertions:
    - InvestigationStarted appears first; InvestigationCompleted last.
    - EvidenceExtracted and PanelResolved appear before any AgentSpoke event.
    - PanelResolved names the four default agents with the correct roles
      (os_kernel/code_analyst/log_historian as INVESTIGATOR; skeptic as ARBITER).
    - Exactly 8 AgentSpoke events (4 agents x 2 rounds) in [os_kernel,
      code_analyst, log_historian, skeptic] order for each round.
    - Exactly 2 ConsensusEvaluated events (one per round).
    - Final RCAReport: consensus_rounds=2, root_cause='UAF in serialize()',
      confidence_score=0.90, confidence_level=HIGH, no HITL request.
    - skeptic_challenges from round 1 appear in the final report (role-driven
      extraction, not 'Skeptic Agent' name match).

    This is the 'back-compat equivalence test' gate from the design doc.
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
# Test 3: variable-panel - explicit 5-agent panel with mixed weight tiers
# ---------------------------------------------------------------------------


async def test_explicit_five_agent_panel_respects_priority_order_and_weight_tiers(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit 5-agent panel runs in priority order with three-tier weight resolution.

    Registers _ExtraAnalystAgent into AGENT_REGISTRY for the duration of this
    test via monkeypatch.setitem, then runs a full investigation with an explicit
    5-agent panel. Verifies:

    - extra_analyst (priority=5) speaks before os_kernel (priority=4) — the
      ordering is descending-priority, not insertion order.
    - skeptic (ARBITER) always runs last regardless of its priority.
    - Probabilistic fix 'guard the pointer with a null check' is extracted from
      code_analyst's turn via the contributes_fix=True capability flag, not via
      any 'Code Analyst Agent' display-name check.
    - consensus_score equals the analytically expected weighted average, proving
      the three-tier weight precedence was applied:
        * extra_analyst:  explicit weight=0.60  (tier 1)
        * os_kernel:      curated unknown=0.30  (tier 2)
        * code_analyst:   curated unknown=0.35  (tier 2)
        * log_historian:  curated unknown=0.20  (tier 2)
        * skeptic:        curated unknown=0.15  (tier 2)
      With scores extra=0.50, all others=0.90:
        CS = (0.60×0.50 + 0.30×0.90 + 0.35×0.90 + 0.20×0.90 + 0.15×0.90)
             / (0.60+0.30+0.35+0.20+0.15) = 1.20/1.60 = 0.75

    A custom consensus_threshold=0.70 is used so that this analytically-derived
    score triggers convergence; the default 0.85 threshold is deliberately
    violated to isolate the weight-tier behaviour under test.

    This is the 'variable-panel test' gate from the design doc.
    """
    monkeypatch.setitem(
        agent_registry_module.AGENT_REGISTRY,
        _ExtraAnalystAgent.agent_key,
        _ExtraAnalystAgent,
    )

    # Lower threshold so the computed CS=0.75 triggers convergence.
    low_threshold_settings = Settings(core={"consensus_threshold": 0.70})

    # Explicit specs: extra_analyst gets tier-1 explicit weight; all real agents
    # will fall to tier-2 curated weights for FaultClass.UNKNOWN (LOG_FORENSICS
    # source produces a brief with fault_class=None → UNKNOWN fallback).
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

    # Verify the three-tier weight precedence took effect by asserting the
    # consensus_score matches the analytically computed expected value.
    # Scores: extra=0.50 (hardcoded), all others 0.90.
    # Weights: extra=0.60 (tier-1 explicit), os=0.30, code=0.35, historian=0.20,
    #          skeptic=0.15 (all tier-2 curated, fault_class=UNKNOWN).
    _weights = {
        "extra_analyst": 0.60,
        "os_kernel": 0.30,
        "code_analyst": 0.35,
        "log_historian": 0.20,
        "skeptic": 0.15,
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
# Test 4: recursion-limit fix prevents GraphRecursionError at high round counts
# ---------------------------------------------------------------------------


async def test_large_max_debate_rounds_completes_without_graph_recursion_error(
    settings: Settings,
) -> None:
    """The (len(panel)+2)*max_rounds+5 budget prevents GraphRecursionError.

    With the default 4-agent panel and max_debate_rounds=7:
      - total node visits = 7 rounds × 4 agents + 1 terminal (hitl) = 29
      - LangGraph's default recursion limit of 25 would be exceeded (29 > 25)
        if the orchestrator did not set a custom recursion_limit.
      - The fix computes (4+2)*7+5 = 47, well above the actual visit count.

    The arbiter always returns LOW confidence so convergence never occurs and
    the debate runs the full 7 rounds before escalating to HITL. The test asserts
    that the investigation completes with a valid HITL RCAReport and consensus_rounds
    equal to max_debate_rounds — confirming the graph ran to normal termination
    rather than being cut short by a recursion error.

    This is the 'recursion_limit test' gate from the design doc.
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
