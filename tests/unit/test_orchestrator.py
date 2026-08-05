"""Unit tests for the MAS orchestrator: full pipeline, routing, HITL"""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from aegis_swr.agents.base import (
    AgentSpec,
    BaseAgent,
    CodeAnalystAgent,
    LogHistorianAgent,
    OSKernelAgent,
    SkepticAgent,
)
from aegis_swr.config.settings import Settings
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
# Helpers - scripted agent responses
# ---------------------------------------------------------------------------


def _os(confidence: float = 0.90) -> OSKernelOutput:
    """Build a canned OS-kernel agent output at the given confidence."""
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
    """Build a canned code-analyst agent output at the given confidence."""
    return CodeAnalystOutput(
        rca=RCAHypothesis(
            root_cause="UAF in serialize()",
            faulting_module="db_writer",
            confidence=confidence,
        ),
        confidence_score=confidence,
    )


def _historian(confidence: float = 0.90) -> LogHistorianOutput:
    """Build a canned log-historian agent output at the given confidence."""
    return LogHistorianOutput(
        confidence_adjustment=0.0,
        updated_confidence=confidence,
        history_note="No recurrence.",
    )


def _skeptic_yes(confidence: ConfidenceLevel = ConfidenceLevel.HIGH) -> SkepticVerdict:
    """Build a confirming skeptic verdict at the given confidence level."""
    return SkepticVerdict(confirmed=True, confidence=confidence)


def _skeptic_no() -> SkepticVerdict:
    """Build a challenging skeptic verdict that rejects the hypothesis."""
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["module not confirmed"],
        corrections=["re-examine"],
    )


def _one_round(confidence: float = 0.90) -> list[Any]:
    """Build one full round of scripted agent outputs ending in a confirming skeptic."""
    return [_os(confidence), _code(confidence), _historian(confidence), _skeptic_yes()]


def _make_orchestrator(settings: Settings, responses: list[Any]) -> Orchestrator:
    """Build an :class:`Orchestrator` driven by a mock AI backend with *responses*."""
    ai = MockAIBackend(responses=responses)
    return Orchestrator(settings=settings, ai_backend=ai)


def _log_only_source() -> IncidentSource:
    """Build a log-forensics :class:`IncidentSource` with no dump."""
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
        _os(0.90),
        _code(0.90),
        _historian(0.90),
        _skeptic_no(),
        # Round 2: Skeptic confirms.
        _os(0.90),
        _code(0.90),
        _historian(0.90),
        _skeptic_yes(),
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
    assert "consensus" in report.hitl_request.question.lower() or "limit" in report.hitl_request.question.lower()


# ---------------------------------------------------------------------------
# Deduplication (cache hit)
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_analysis(settings: Settings):
    """
    [Unit] orchestrator: verifies cache hit skips analysis.

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


# ---------------------------------------------------------------------------
# Dynamic-panel invariants (Phase 4 rewrite)
# ---------------------------------------------------------------------------


async def test_default_panel_preserves_investigator_order_and_consensus(settings: Settings):
    """[Unit] orchestrator: the default panel keeps the pre-refactor node chain.

    Scenario: an orchestrator runs with no explicit specs over one uniform-0.90
    scripted round.

    Boundaries: back-compat sanity check on the default resolved panel ordering and
    consensus math; the AI backend is mocked.

    On failure, first check: the debate order must be ``os_kernel → code_analyst →
    log_historian → skeptic`` and the weighted consensus must equal 0.90.
    """
    orch = _make_orchestrator(settings, _one_round(confidence=0.90))
    report = await orch.run(_log_only_source())

    assert [turn.agent_key for turn in report.agent_dialogue] == [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "skeptic",
    ]
    assert report.confidence_score == pytest.approx(0.90)


def test_order_panel_sorts_by_priority_then_puts_arbiter_last(settings: Settings):
    """[Unit] orchestrator: investigators sort by priority desc; arbiter is last.

    Scenario: a panel of investigators with mixed priorities plus one arbiter is
    ordered.

    Boundaries: exercises panel ordering only; ties must be stable.

    On failure, first check: same-priority investigators keep declared order and the
    sole arbiter is scheduled last regardless of its own priority.
    """
    ai = MockAIBackend()
    # Input order: os_kernel(1), code_analyst(5), log_historian(5), skeptic(5).
    panel: list[BaseAgent] = [
        OSKernelAgent(ai, settings, AgentSpec(agent_key="os_kernel", priority=1)),
        CodeAnalystAgent(ai, settings, AgentSpec(agent_key="code_analyst", priority=5)),
        LogHistorianAgent(ai, settings, AgentSpec(agent_key="log_historian", priority=5)),
        SkepticAgent(ai, settings, AgentSpec(agent_key="skeptic", priority=5)),
    ]
    ordered = Orchestrator._order_panel(panel)

    # code(5) and log(5) tie -> stable input order; os(1) after them; arbiter last.
    assert [agent.agent_key for agent in ordered] == [
        "code_analyst",
        "log_historian",
        "os_kernel",
        "skeptic",
    ]
    assert ordered[-1].role is AgentRole.ARBITER


# ---------------------------------------------------------------------------
# Report synthesis is role/capability-driven, not display-name-driven
# ---------------------------------------------------------------------------


class _CustomArbiter(BaseAgent):
    """Test-double arbiter with a deliberately non-'Skeptic Agent' display name."""

    agent_key = "custom_arbiter"
    display_name = "Custom Adversary 9000"
    category = "base"
    role = AgentRole.ARBITER

    @property
    def system_prompt(self) -> str:
        """Return an empty prompt; this test double never invokes the model."""
        return ""

    async def run(self, state: InvestigationState) -> AgentTurn:  # pragma: no cover
        """Unused by these tests; raise to signal it must not be invoked."""
        raise NotImplementedError


class _CustomFixer(BaseAgent):
    """Test-double fix contributor with a non-'Code Analyst Agent' display name."""

    agent_key = "custom_fixer"
    display_name = "Custom Fixer 9000"
    category = "base"
    role = AgentRole.INVESTIGATOR
    contributes_fix = True

    @property
    def system_prompt(self) -> str:
        """Return an empty prompt; this test double never invokes the model."""
        return ""

    async def run(self, state: InvestigationState) -> AgentTurn:  # pragma: no cover
        """Unused by these tests; raise to signal it must not be invoked."""
        raise NotImplementedError


def test_build_report_extracts_challenges_and_fix_by_role_not_name(settings: Settings):
    """[Unit] orchestrator: _build_report keys off role/capability, not display name.

    Scenario: a synthetic panel whose arbiter and fix-contributor carry custom
    display names builds a report.

    Boundaries: proves synthesis is driven by ``agent_key``/role/``contributes_fix``,
    not by hardcoded display-name strings.

    On failure, first check: challenges, the probabilistic fix, and alternative
    hypotheses must all be extracted despite the non-standard display names.
    """
    ai = MockAIBackend()
    fixer = _CustomFixer(ai, settings)
    arbiter = _CustomArbiter(ai, settings)
    panel: list[BaseAgent] = [fixer, arbiter]

    fixer_turn = AgentTurn(
        agent=fixer.display_name,
        agent_key=fixer.agent_key,
        turn_number=1,
        message="root cause",
        confidence_score=0.9,
        hypotheses=[
            Hypothesis(
                root_cause="UAF in serialize()",
                evidence=["stack shows freed block", "__fix__:python:guard the pointer"],
                confidence=0.9,
            ),
            Hypothesis(root_cause="alt: double free", evidence=["maybe"], confidence=0.4),
        ],
    )
    arbiter_turn = AgentTurn(
        agent=arbiter.display_name,
        agent_key=arbiter.agent_key,
        turn_number=1,
        message="challenged",
        confidence_score=0.3,
        hypotheses=[
            Hypothesis(
                root_cause="UAF in serialize()",
                evidence=["module not in top frames"],
                confidence=0.3,
            )
        ],
    )

    state: InvestigationState = {
        "incident_brief": {"mode": IncidentMode.LOG_FORENSICS.value},
        "discussion_history": [
            fixer_turn.model_dump(mode="json"),
            arbiter_turn.model_dump(mode="json"),
        ],
        "consensus_score": 0.72,
        "primary_hypothesis": {"root_cause": "UAF in serialize()"},
        "round_number": 2,
        "token_tracker": {"input_tokens": 0, "output_tokens": 0},
    }

    report = Orchestrator._build_report(state, panel, hitl_pending=False)

    # Arbiter's hypothesis evidence becomes the challenges.
    assert report.skeptic_challenges == ["module not in top frames"]
    # The fix-contributor's __fix__ annotation is extracted.
    assert report.probabilistic_fix == "guard the pointer"
    # The fixer's non-primary hypotheses become alternatives.
    assert [h.root_cause for h in report.alternative_hypotheses] == ["alt: double free"]
