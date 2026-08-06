"""Unit tests for the four Synthetic War Room agents"""

from __future__ import annotations

import json
from typing import Any, Optional

from aegis_swr.agents.base import (
    CodeAnalystAgent,
    LogHistorianAgent,
    OSKernelAgent,
    SkepticAgent,
)
from aegis_swr.backends.base import VectorStore
from aegis_swr.config.settings import Settings
from aegis_swr.core.exceptions import VectorStoreError
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    CodeAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    IncidentMode,
    InvestigationState,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    RCAReport,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


class RecordingVectorStore(VectorStore):
    """Minimal vector store stub that records search calls."""

    def __init__(
        self,
        responses: Optional[list[RCAReport]] = None,
        error: Optional[Exception] = None,
    ):
        """Helper that provides init for the agents tests."""
        self._responses = list(responses or [])
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def upsert_incident(self, report: RCAReport):
        """Helper that provides upsert incident for the agents tests."""
        self.calls.append({"operation": "upsert", "report": report})

    async def search_similar(
        self,
        fault_class: FaultClass,
        faulting_module: Optional[str],
        top_k: int = 5,
    ) -> list[RCAReport]:
        """Helper that provides search similar for the agents tests."""
        self.calls.append(
            {
                "operation": "search",
                "fault_class": fault_class,
                "faulting_module": faulting_module,
                "top_k": top_k,
            }
        )
        if self._error is not None:
            raise self._error
        return list(self._responses)


def _base_state(**extra: Any) -> InvestigationState:
    """Helper that provides base state for the agents tests."""
    state: InvestigationState = {
        "incident_id": "test-id",
        "incident_brief": {
            "fault_class": "memory_access_violation",
            "exception_code_raw": "0xc0000005",
            "exception_address": "0x00007ff8016a1c3f",
            "faulting_module": "db_writer",
            "faulting_function": "db_writer::serialize",
            "stack_frames": [
                {
                    "frame_number": 0,
                    "module": "db_writer",
                    "function": "db_writer::serialize",
                    "instruction_address": "0x00007ff8016a1c3f",
                },
                {
                    "frame_number": 1,
                    "module": "db_writer",
                    "function": "db_writer::flush",
                    "instruction_address": "0x00007ff8016a2210",
                },
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
    """Helper that provides os kernel response for the agents tests."""
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
    """Helper that provides code analyst response for the agents tests."""
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
    """Helper that provides log historian response for the agents tests."""
    return LogHistorianOutput(
        pattern_match=None,
        confidence_adjustment=0.0,
        updated_confidence=0.85,
        history_note="No recurrence detected in the last 10 incidents.",
    )


def _skeptic_confirmed() -> SkepticVerdict:
    """Helper that provides skeptic confirmed for the agents tests."""
    return SkepticVerdict(
        confirmed=True,
        confidence=ConfidenceLevel.HIGH,
        challenges=[],
        corrections=[],
    )


def _skeptic_rejected() -> SkepticVerdict:
    """Helper that provides skeptic rejected for the agents tests."""
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["Stated module not consistent with exception code"],
        corrections=["Re-examine the exception address"],
    )


# ---------------------------------------------------------------------------
# OS Kernel Agent
# ---------------------------------------------------------------------------


async def test_os_kernel_requests_correct_schema(settings: Settings):
    """
    [Unit] agents: verifies os kernel requests correct schema.

    Scenario:
        Given test inputs and fixtures for os kernel requests correct schema
        When test_os_kernel_requests_correct_schema executes the target flow
        Then the expected outcome for os kernel requests correct schema is confirmed.

    Boundaries:
        - Focus: os kernel requests correct schema
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to os kernel requests correct schema
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert turn.agent == "OS Kernel Agent"
    assert turn.confidence_score == 0.85
    # The generate() call must have used OSKernelOutput as the schema.
    assert ai.calls[0]["schema"] is OSKernelOutput


async def test_os_kernel_prepends_low_symbol_warning(settings: Settings):
    """
    [Unit] agents: verifies os kernel prepends low symbol warning.

    Scenario:
        Given test inputs and fixtures for os kernel prepends low symbol warning
        When test_os_kernel_prepends_low_symbol_warning executes the target flow
        Then the expected outcome for os kernel prepends low symbol warning is confirmed.

    Boundaries:
        - Focus: os kernel prepends low symbol warning
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to os kernel prepends low symbol warning
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    state = _base_state()
    state["incident_brief"]["low_symbol_coverage_warning"] = "[LOW SYMBOL COVERAGE: 30%]"
    await agent.run(state)
    sent_content = ai.calls[0]["messages"][0]["content"]
    assert "LOW SYMBOL COVERAGE" in sent_content


async def test_os_kernel_injects_skeptic_corrections_on_round_2(settings: Settings):
    """
    [Unit] agents: verifies os kernel injects skeptic corrections on round 2.

    Scenario:
        Given test inputs and fixtures for os kernel injects skeptic corrections on round 2
        When test_os_kernel_injects_skeptic_corrections_on_round_2 executes the target flow
        Then the expected outcome for os kernel injects skeptic corrections on round 2 is confirmed.

    Boundaries:
        - Focus: os kernel injects skeptic corrections on round 2
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to os kernel injects skeptic corrections on round 2
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    state = _base_state(
        round_number=2,
        latest_arbiter_feedback=["Re-examine frame 3"],
    )
    await agent.run(state)
    sent = ai.calls[0]["messages"][0]["content"]
    assert "Re-examine frame 3" in sent


async def test_os_kernel_ignores_non_matching_history_on_round_2(settings: Settings):
    """
    [Unit] agents: verifies os kernel ignores non matching history on round 2.

    Scenario:
        Given test inputs and fixtures for os kernel ignores non matching history on round 2
        When test_os_kernel_ignores_non_matching_history_on_round_2 executes the target flow
        Then the expected outcome for os kernel ignores non matching history on round 2 is confirmed.

    Boundaries:
        - Focus: os kernel ignores non matching history on round 2
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to os kernel ignores non matching history on round 2
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_os_kernel_response()])
    agent = OSKernelAgent(ai, settings)
    unrelated_turn = AgentTurn(
        agent="Code Analyst Agent",
        turn_number=1,
        message="Not a skeptic turn",
        confidence_score=0.55,
    )
    await agent.run(
        _base_state(
            round_number=2,
            discussion_history=[unrelated_turn.model_dump(mode="json")],
        )
    )
    sent = json.loads(ai.calls[0]["messages"][0]["content"])
    assert "skeptic_corrections_from_previous_round" not in sent


# ---------------------------------------------------------------------------
# Code Analyst Agent
# ---------------------------------------------------------------------------


async def test_code_analyst_requests_correct_schema(settings: Settings):
    """
    [Unit] agents: verifies code analyst requests correct schema.

    Scenario:
        Given test inputs and fixtures for code analyst requests correct schema
        When test_code_analyst_requests_correct_schema executes the target flow
        Then the expected outcome for code analyst requests correct schema is confirmed.

    Boundaries:
        - Focus: code analyst requests correct schema
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to code analyst requests correct schema
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_code_analyst_response()])
    agent = CodeAnalystAgent(ai, settings)
    os_turn = AgentTurn(
        agent="OS Kernel Agent",
        turn_number=1,
        message="UAF",
        hypotheses=[Hypothesis(root_cause="UAF", confidence=0.85)],
        confidence_score=0.85,
    )
    state = _base_state(discussion_history=[os_turn.model_dump(mode="json")])
    turn = await agent.run(state)
    assert isinstance(turn, AgentTurn)
    assert ai.calls[0]["schema"] is CodeAnalystOutput


async def test_code_analyst_includes_user_assumption(settings: Settings):
    """
    [Unit] agents: verifies code analyst includes user assumption.

    Scenario:
        Given test inputs and fixtures for code analyst includes user assumption
        When test_code_analyst_includes_user_assumption executes the target flow
        Then the expected outcome for code analyst includes user assumption is confirmed.

    Boundaries:
        - Focus: code analyst includes user assumption
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to code analyst includes user assumption
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_code_analyst_response()])
    agent = CodeAnalystAgent(ai, settings)
    state = _base_state()
    state["incident_brief"]["user_assumption"] = "DB pool was reduced yesterday"
    await agent.run(state)
    sent = ai.calls[0]["messages"][0]["content"]
    assert "DB pool was reduced yesterday" in sent


async def test_code_analyst_uses_latest_kernel_turn_and_encodes_fix(settings: Settings):
    """
    [Unit] agents: verifies code analyst uses latest kernel turn and encodes fix.

    Scenario:
        Given test inputs and fixtures for code analyst uses latest kernel turn and encodes fix
        When test_code_analyst_uses_latest_kernel_turn_and_encodes_fix executes the target flow
        Then the expected outcome for code analyst uses latest kernel turn and encodes fix is confirmed.

    Boundaries:
        - Focus: code analyst uses latest kernel turn and encodes fix
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to code analyst uses latest kernel turn and encodes fix
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(
        responses=[
            CodeAnalystOutput(
                rca=RCAHypothesis(
                    root_cause="Race condition exposes UAF in serialize()",
                    faulting_module="db_writer",
                    faulting_function="db_writer::serialize",
                    evidence=["frame 0 is serialize", "frame 1 is flush"],
                    confidence=0.91,
                    code_location="db_writer.cpp:142",
                ),
                alternative_hypotheses=[Hypothesis(root_cause="Allocator poisoning", confidence=0.25)],
                confidence_score=0.91,
                probabilistic_fix="@@ -1 +1 @@\n-old\n+new",
                fix_language="python",
            )
        ]
    )
    agent = CodeAnalystAgent(ai, settings)
    latest_turn = AgentTurn(
        agent="OS Kernel Agent",
        turn_number=2,
        message="Current kernel interpretation",
        hypotheses=[Hypothesis(root_cause="Current UAF", confidence=0.82)],
        confidence_score=0.82,
    )
    turn = await agent.run(
        _base_state(
            round_number=2,
            latest_turn_this_round=latest_turn.model_dump(mode="json"),
        )
    )
    sent = json.loads(ai.calls[0]["messages"][0]["content"])
    assert sent["os_kernel_analysis"]["message"] == "Current kernel interpretation"
    assert turn.hypotheses[0].evidence[-1] == "__fix__:python:@@ -1 +1 @@\n-old\n+new"
    assert len(turn.hypotheses) == 2


# ---------------------------------------------------------------------------
# Log Historian Agent
# ---------------------------------------------------------------------------


async def test_log_historian_requests_correct_schema(settings: Settings):
    """
    [Unit] agents: verifies log historian requests correct schema.

    Scenario:
        Given test inputs and fixtures for log historian requests correct schema
        When test_log_historian_requests_correct_schema executes the target flow
        Then the expected outcome for log historian requests correct schema is confirmed.

    Boundaries:
        - Focus: log historian requests correct schema
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian requests correct schema
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_log_historian_response()])
    agent = LogHistorianAgent(ai, settings)
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert ai.calls[0]["schema"] is LogHistorianOutput


def _prior_report() -> RCAReport:
    """A stored report for the same defect as ``_base_state`` (new dump hash)."""
    return RCAReport(
        mode=IncidentMode.CRASH_DUMP,
        dump_hash="sha256:previous-session",
        root_cause="Use-after-free in db_writer::serialize at db_writer.cpp:142.",
        faulting_module="db_writer",
        faulting_function="db_writer::serialize",
        confidence_score=0.9,
        confidence_level=ConfidenceLevel.HIGH,
        primary_hypothesis=Hypothesis(
            root_cause="UAF in serialize",
            faulting_module="db_writer",
            faulting_function="db_writer::serialize",
            evidence=["Exception 0xc0000005 at db_writer.cpp:142"],
            confidence=0.9,
        ),
        consensus_rounds=1,
    )


async def test_log_historian_detects_recurrence_from_history(settings: Settings):
    """
    [Unit] agents: verifies log historian detects recurrence from history.

    Scenario:
        Given test inputs and fixtures for log historian detects recurrence from history
        When test_log_historian_detects_recurrence_from_history executes the target flow
        Then the expected outcome for log historian detects recurrence from history is confirmed.

    Boundaries:
        - Focus: log historian detects recurrence from history
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian detects recurrence from history
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_log_historian_response()])
    agent = LogHistorianAgent(ai, settings)

    await agent.run(_base_state(), history=[_prior_report(), _prior_report()])

    sent = json.loads(ai.calls[0]["messages"][0]["content"])
    analysis = sent["recurrence_analysis"]
    assert analysis["history_size"] == 2
    assert analysis["is_recurrence"] is True
    assert analysis["recurrence_count"] == 2
    assert analysis["recurrence_probability"] > 0.5
    # A recurrence reinforces the diagnosis: the nudge is positive.
    assert analysis["suggested_confidence_adjustment"] > 0
    assert "recurrence" in analysis["summary"].lower()


async def test_log_historian_reports_first_observation_without_matches(settings: Settings):
    """
    [Unit] agents: verifies log historian reports first observation without matches.

    Scenario:
        Given test inputs and fixtures for log historian reports first observation without matches
        When test_log_historian_reports_first_observation_without_matches executes the target flow
        Then the expected outcome for log historian reports first observation without matches is confirmed.

    Boundaries:
        - Focus: log historian reports first observation without matches
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian reports first observation without matches
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_log_historian_response()])
    agent = LogHistorianAgent(ai, settings)

    unrelated = _prior_report()
    unrelated.faulting_module = "render_engine"
    unrelated.faulting_function = "render_engine::draw"
    unrelated.root_cause = "Divide-by-zero in render_engine::draw at gfx.cpp:9."
    unrelated.primary_hypothesis = Hypothesis(
        root_cause="div0",
        faulting_module="render_engine",
        faulting_function="render_engine::draw",
        evidence=["Exception 0xc0000094 at gfx.cpp:9"],
        confidence=0.8,
    )

    await agent.run(_base_state(), history=[unrelated])

    sent = json.loads(ai.calls[0]["messages"][0]["content"])
    analysis = sent["recurrence_analysis"]
    assert analysis["history_size"] == 1
    assert analysis["is_recurrence"] is False
    assert analysis["matched_incidents"] == []


async def test_log_historian_uses_latest_code_turn_and_vector_results(settings: Settings):
    """
    [Unit] agents: verifies log historian uses latest code turn and vector results.

    Scenario:
        Given test inputs and fixtures for log historian uses latest code turn and vector results
        When test_log_historian_uses_latest_code_turn_and_vector_results executes the target flow
        Then the expected outcome for log historian uses latest code turn and vector results is confirmed.

    Boundaries:
        - Focus: log historian uses latest code turn and vector results
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian uses latest code turn and vector results
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_log_historian_response()])
    agent = LogHistorianAgent(ai, settings)
    vector_store = RecordingVectorStore(responses=[_prior_report()])
    latest_turn = AgentTurn(
        agent="Code Analyst Agent",
        turn_number=2,
        message="Current code analysis",
        hypotheses=[Hypothesis(root_cause="Current UAF", confidence=0.88)],
        confidence_score=0.88,
    )

    await agent.run(
        _base_state(
            round_number=2,
            latest_turn_this_round=latest_turn.model_dump(mode="json"),
        ),
        vector_store=vector_store,
        history=[_prior_report()],
    )

    sent = json.loads(ai.calls[0]["messages"][0]["content"])
    assert sent["code_analyst_analysis"]["message"] == "Current code analysis"
    assert sent["recurrence_analysis"]["history_size"] == 2
    assert vector_store.calls[0] == {
        "operation": "search",
        "fault_class": FaultClass.MEMORY_ACCESS_VIOLATION,
        "faulting_module": "db_writer",
        "top_k": 5,
    }


async def test_log_historian_vector_candidates_normalize_unknown_faults(settings: Settings):
    """
    [Unit] agents: verifies log historian vector candidates normalize unknown faults.

    Scenario:
        Given test inputs and fixtures for log historian vector candidates normalize unknown faults
        When test_log_historian_vector_candidates_normalize_unknown_faults executes the target flow
        Then the expected outcome for log historian vector candidates normalize unknown faults is confirmed.

    Boundaries:
        - Focus: log historian vector candidates normalize unknown faults
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian vector candidates normalize unknown faults
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    vector_store = RecordingVectorStore(responses=[])
    result = await LogHistorianAgent._vector_candidates(
        {"fault_class": "not-a-real-fault", "faulting_module": ""},
        vector_store,
    )
    assert result == []
    assert vector_store.calls[0] == {
        "operation": "search",
        "fault_class": FaultClass.UNKNOWN,
        "faulting_module": None,
        "top_k": 5,
    }


async def test_log_historian_vector_candidates_swallow_store_errors(settings: Settings):
    """
    [Unit] agents: verifies log historian vector candidates swallow store errors.

    Scenario:
        Given test inputs and fixtures for log historian vector candidates swallow store errors
        When test_log_historian_vector_candidates_swallow_store_errors executes the target flow
        Then the expected outcome for log historian vector candidates swallow store errors is confirmed.

    Boundaries:
        - Focus: log historian vector candidates swallow store errors
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to log historian vector candidates swallow store errors
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    vector_store = RecordingVectorStore(error=VectorStoreError("vector search failed"))
    result = await LogHistorianAgent._vector_candidates(_base_state()["incident_brief"], vector_store)
    assert result == []
    assert vector_store.calls[0]["operation"] == "search"


# ---------------------------------------------------------------------------
# Skeptic Agent - LLM path
# ---------------------------------------------------------------------------


async def test_skeptic_confirmed_sets_high_confidence(settings: Settings):
    """
    [Unit] agents: verifies skeptic confirmed sets high confidence.

    Scenario:
        Given test inputs and fixtures for skeptic confirmed sets high confidence
        When test_skeptic_confirmed_sets_high_confidence executes the target flow
        Then the expected outcome for skeptic confirmed sets high confidence is confirmed.

    Boundaries:
        - Focus: skeptic confirmed sets high confidence
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic confirmed sets high confidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_skeptic_confirmed()])
    agent = SkepticAgent(ai, settings)
    state = _base_state(
        primary_hypothesis={"root_cause": "UAF", "faulting_module": "db_writer"},
    )
    turn = await agent.run(state)
    assert isinstance(turn, AgentTurn)
    assert turn.confidence_score >= 0.65  # MEDIUM or HIGH


async def test_skeptic_rejected_sets_low_confidence(settings: Settings):
    """
    [Unit] agents: verifies skeptic rejected sets low confidence.

    Scenario:
        Given test inputs and fixtures for skeptic rejected sets low confidence
        When test_skeptic_rejected_sets_low_confidence executes the target flow
        Then the expected outcome for skeptic rejected sets low confidence is confirmed.

    Boundaries:
        - Focus: skeptic rejected sets low confidence
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic rejected sets low confidence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_skeptic_rejected()])
    agent = SkepticAgent(ai, settings)
    state = _base_state(
        primary_hypothesis={"root_cause": "UAF", "faulting_module": "db_writer"},
    )
    turn = await agent.run(state)
    assert turn.confidence_score < 0.50
    assert len(turn.corrections) > 0


# ---------------------------------------------------------------------------
# Skeptic Agent - programmatic pre-check (no LLM call when module absent)
# ---------------------------------------------------------------------------


async def test_skeptic_fails_prechecks_without_llm_call(settings: Settings):
    """
    [Unit] agents: verifies skeptic fails prechecks without llm call.

    Scenario:
        Given test inputs and fixtures for skeptic fails prechecks without llm call
        When test_skeptic_fails_prechecks_without_llm_call executes the target flow
        Then the expected outcome for skeptic fails prechecks without llm call is confirmed.

    Boundaries:
        - Focus: skeptic fails prechecks without llm call
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic fails prechecks without llm call
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend()  # empty responses - any call would raise
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


async def test_skeptic_skips_precheck_when_no_primary_hypothesis(settings: Settings):
    """
    [Unit] agents: verifies skeptic skips precheck when no primary hypothesis.

    Scenario:
        Given test inputs and fixtures for skeptic skips precheck when no primary hypothesis
        When test_skeptic_skips_precheck_when_no_primary_hypothesis executes the target flow
        Then the expected outcome for skeptic skips precheck when no primary hypothesis is confirmed.

    Boundaries:
        - Focus: skeptic skips precheck when no primary hypothesis
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to skeptic skips precheck when no primary hypothesis
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(responses=[_skeptic_confirmed()])
    agent = SkepticAgent(ai, settings)
    # No primary_hypothesis → pre-check cannot run → falls through to LLM.
    turn = await agent.run(_base_state())
    assert isinstance(turn, AgentTurn)
    assert len(ai.calls) == 1


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------


async def test_token_tracker_accumulated_in_state(settings: Settings):
    """
    [Unit] agents: verifies token tracker accumulated in state.

    Scenario:
        Given test inputs and fixtures for token tracker accumulated in state
        When test_token_tracker_accumulated_in_state executes the target flow
        Then the expected outcome for token tracker accumulated in state is confirmed.

    Boundaries:
        - Focus: token tracker accumulated in state
        - Fixtures/params: settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to token tracker accumulated in state
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by agents
    """
    ai = MockAIBackend(
        responses=[_os_kernel_response()],
        usage={"input_tokens": 300, "output_tokens": 50},
    )
    agent = OSKernelAgent(ai, settings)
    state = _base_state()
    await agent.run(state)
    assert state["token_tracker"]["input_tokens"] == 300
    assert state["token_tracker"]["output_tokens"] == 50
