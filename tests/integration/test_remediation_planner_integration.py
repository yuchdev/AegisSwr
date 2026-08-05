"""Integration tests: RemediationPlannerAgent wired into the full orchestrator.

Uses mocked AI and debug backends. Confirms a converged investigation yields a
remediation plan, a HITL (deadlocked) investigation does not, and the plan is
`/playbook-validate`-compatible.
"""

from __future__ import annotations

from typing import Any

from aegis_swr.agents.synthesis.remediation_planner import remediation_plan_to_playbook_dict
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    CodeAnalystOutput,
    ConfidenceLevel,
    ExceptionSummary,
    Hypothesis,
    IncidentMode,
    IncidentSource,
    LogHistorianOutput,
    OSKernelOutput,
    RCAHypothesis,
    RemediationPlan,
    RemediationStep,
    SkepticVerdict,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _os(conf: float) -> OSKernelOutput:
    """Helper that provides os for the remediation planner integration tests."""
    return OSKernelOutput(
        exception_summary=ExceptionSummary(
            fault_class=FaultClass.UNKNOWN,
            exception_code_raw="0x0",
            exception_address="0x0",
            interpretation="fd leak crash.",
        ),
        hypotheses=[Hypothesis(root_cause="fd leak", confidence=conf)],
        confidence_score=conf,
    )


def _code(conf: float) -> CodeAnalystOutput:
    """Helper that provides code for the remediation planner integration tests."""
    return CodeAnalystOutput(rca=RCAHypothesis(root_cause="fd leak", confidence=conf), confidence_score=conf)


def _historian(conf: float) -> LogHistorianOutput:
    """Helper that provides historian for the remediation planner integration tests."""
    return LogHistorianOutput(confidence_adjustment=0.0, updated_confidence=conf, history_note="No recurrence.")


def _skeptic_yes() -> SkepticVerdict:
    """Helper that provides skeptic yes for the remediation planner integration tests."""
    return SkepticVerdict(confirmed=True, confidence=ConfidenceLevel.HIGH)


def _skeptic_no() -> SkepticVerdict:
    """Helper that provides skeptic no for the remediation planner integration tests."""
    return SkepticVerdict(
        confirmed=False,
        confidence=ConfidenceLevel.LOW,
        challenges=["not confirmed"],
        corrections=["re-examine"],
    )


def _plan() -> RemediationPlan:
    """Helper that provides plan for the remediation planner integration tests."""
    return RemediationPlan(
        steps=[
            RemediationStep(order=1, action="isolate", idempotent=True, rollback="rejoin"),
            RemediationStep(order=2, action="raise ulimit", idempotent=True, rollback="restore"),
        ],
        summary="Contain then remediate the fd leak.",
        confidence=0.9,
        requires_human_approval=False,
    )


def _log_source() -> IncidentSource:
    """Helper that provides log source for the remediation planner integration tests."""
    return IncidentSource(mode=IncidentMode.LOG_FORENSICS)


async def test_converged_investigation_yields_remediation_plan(settings: Settings):
    # Default (log-only) panel is the four base agents; converge in round 1, then
    # the synthesizer calls the planner (5th response).
    """[Integration] remediation planner integration: verifies converged investigation yields remediation plan.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verifies converged investigation yields remediation plan.
    """
    responses: list[Any] = [_os(0.9), _code(0.9), _historian(0.9), _skeptic_yes(), _plan()]
    orch = Orchestrator(settings=settings, ai_backend=MockAIBackend(responses=responses))

    report = await orch.run(_log_source())

    assert report.remediation_plan is not None
    assert report.remediation_plan.steps
    assert all(step.rollback for step in report.remediation_plan.steps)
    assert report.hitl_request is None


async def test_hitl_investigation_yields_no_remediation_plan(settings: Settings):
    """[Integration] remediation planner integration: verifies hitl investigation yields no remediation plan.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verifies hitl investigation yields no remediation plan.
    """
    settings.core.max_debate_rounds = 1
    # Round 1 the arbiter rejects; the debate limit is hit -> HITL, no synthesis.
    responses: list[Any] = [_os(0.5), _code(0.5), _historian(0.5), _skeptic_no()]
    orch = Orchestrator(settings=settings, ai_backend=MockAIBackend(responses=responses))

    report = await orch.run(_log_source())

    assert report.remediation_plan is None
    assert report.hitl_request is not None


async def test_playbook_validate_compatible_output(settings: Settings):
    """[Integration] remediation planner integration: verifies playbook validate compatible output.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verifies playbook validate compatible output.
    """
    responses: list[Any] = [_os(0.9), _code(0.9), _historian(0.9), _skeptic_yes(), _plan()]
    orch = Orchestrator(settings=settings, ai_backend=MockAIBackend(responses=responses))

    report = await orch.run(_log_source())
    assert report.remediation_plan is not None

    playbook = remediation_plan_to_playbook_dict(report.remediation_plan, report)
    for field in ("id", "name", "trigger", "steps", "owner", "severity"):
        assert field in playbook
    for step in playbook["steps"]:
        for field in (
            "id",
            "description",
            "action",
            "idempotent",
            "rollback",
            "requires_authorisation",
            "timeout",
        ):
            assert field in step
