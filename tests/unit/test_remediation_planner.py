"""Unit tests for the Remediation Planner synthesis agent, adapter, and wiring."""

from __future__ import annotations

from typing import Any

import pytest

from aegis_swr.agents.synthesis.remediation_planner import (
    RemediationPlannerAgent,
    remediation_plan_to_playbook_dict,
)
from aegis_swr.config.settings import Settings
from aegis_swr.core.events import AgentSpoke
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.schemas import (
    AgentTurn,
    ConfidenceLevel,
    Hypothesis,
    IncidentMode,
    RCAReport,
    RemediationPlan,
    RemediationStep,
)
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


def _plan(*, confidence: float = 0.9, requires_human_approval: bool = False) -> RemediationPlan:
    return RemediationPlan(
        steps=[
            RemediationStep(order=1, action="isolate node", idempotent=True, rollback="rejoin node"),
            RemediationStep(
                order=2,
                action="raise fd ulimit",
                idempotent=True,
                rollback="restore prior ulimit",
                requires_human_approval=True,
            ),
        ],
        summary="Contain, remediate, verify the fd leak.",
        confidence=confidence,
        requires_human_approval=requires_human_approval,
    )


def _report(**kw: Any) -> RCAReport:
    base = {
        "mode": IncidentMode.LOG_FORENSICS,
        "root_cause": "file-descriptor leak in accept loop",
        "faulting_module": "net_server",
        "confidence_score": 0.9,
        "confidence_level": ConfidenceLevel.HIGH,
        "primary_hypothesis": Hypothesis(root_cause="fd leak", evidence=["fd count climbs"], confidence=0.9),
        "consensus_rounds": 1,
        "mitigation_instructions": ["increase ulimit", "fix leak"],
    }
    base.update(kw)
    return RCAReport(**base)


# ---------------------------------------------------------------------------
# ClassVars / run() exclusion
# ---------------------------------------------------------------------------


def test_class_vars():
    assert RemediationPlannerAgent.agent_key == "remediation_planner"
    assert RemediationPlannerAgent.category == "synthesis"
    assert RemediationPlannerAgent.display_name == "Remediation Planner Agent"


async def test_run_raises_not_implemented(settings: Settings):
    agent = RemediationPlannerAgent(MockAIBackend(), settings)
    with pytest.raises(NotImplementedError):
        await agent.run({})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# run_synthesis
# ---------------------------------------------------------------------------


async def test_run_synthesis_returns_plan_with_all_steps_idempotent(settings: Settings):
    ai = MockAIBackend(responses=[_plan()])
    agent = RemediationPlannerAgent(ai, settings)
    turn, plan = await agent.run_synthesis(_report())
    assert isinstance(turn, AgentTurn)
    assert isinstance(plan, RemediationPlan)
    assert all(step.idempotent for step in plan.steps)


async def test_run_synthesis_plan_has_rollback_on_every_step(settings: Settings):
    ai = MockAIBackend(responses=[_plan()])
    _turn, plan = await RemediationPlannerAgent(ai, settings).run_synthesis(_report())
    assert all(step.rollback for step in plan.steps)


async def test_run_synthesis_turn_has_synthesis_agent_label(settings: Settings):
    ai = MockAIBackend(responses=[_plan()])
    turn, _plan_out = await RemediationPlannerAgent(ai, settings).run_synthesis(_report())
    assert turn.agent == "Remediation Planner Agent"
    assert turn.turn_number == 0


async def test_run_synthesis_does_not_include_raw_payload(settings: Settings):
    ai = MockAIBackend(responses=[_plan()])
    agent = RemediationPlannerAgent(ai, settings)
    report = _report()
    await agent.run_synthesis(report)
    sent = ai.calls[-1]["messages"][0]["content"]
    assert "raw_text_excerpt" not in sent
    assert "agent_dialogue" not in sent


# ---------------------------------------------------------------------------
# Playbook adapter
# ---------------------------------------------------------------------------


def test_playbook_adapter_contains_required_fields():
    result = remediation_plan_to_playbook_dict(_plan(), _report())
    for field in ("id", "name", "trigger", "steps", "owner", "severity"):
        assert field in result


def test_playbook_adapter_step_fields():
    result = remediation_plan_to_playbook_dict(_plan(), _report())
    for step in result["steps"]:
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


def test_playbook_adapter_requires_authorisation_maps_correctly():
    result = remediation_plan_to_playbook_dict(_plan(), _report())
    # Step 2 sets requires_human_approval=True -> requires_authorisation True.
    assert result["steps"][1]["requires_authorisation"] is True
    assert result["steps"][0]["requires_authorisation"] is False


def test_playbook_adapter_step_id_format():
    plan = RemediationPlan(
        steps=[
            RemediationStep(order=1, action="a", idempotent=True, rollback="r"),
            RemediationStep(order=2, action="b", idempotent=True, rollback="r"),
            RemediationStep(order=3, action="c", idempotent=True, rollback="r"),
        ],
        summary="s",
        confidence=0.9,
        requires_human_approval=False,
    )
    result = remediation_plan_to_playbook_dict(plan, _report())
    assert result["steps"][2]["id"] == "step-03"


# ---------------------------------------------------------------------------
# Orchestrator synthesis wiring
# ---------------------------------------------------------------------------


def _orch(ai: MockAIBackend, settings: Settings) -> Orchestrator:
    return Orchestrator(settings=settings, ai_backend=ai)


async def test_synthesize_attaches_remediation_plan(settings: Settings):
    orch = _orch(MockAIBackend(responses=[_plan()]), settings)
    result = await orch._synthesize_remediation(_report())
    assert result.remediation_plan is not None
    assert result.remediation_plan.steps


async def test_synthesize_disabled_leaves_plan_none(settings: Settings):
    settings.panel.enabled_synthesis = []
    orch = _orch(MockAIBackend(responses=[_plan()]), settings)
    result = await orch._synthesize_remediation(_report())
    assert result.remediation_plan is None


async def test_synthesize_exception_is_soft_failure(settings: Settings):
    # No scripted response -> MockAIBackend raises; the node must swallow it.
    orch = _orch(MockAIBackend(responses=[]), settings)
    result = await orch._synthesize_remediation(_report())
    assert result.remediation_plan is None


async def test_agent_spoke_emitted_after_synthesis(settings: Settings):
    orch = _orch(MockAIBackend(responses=[_plan()]), settings)
    seen: list[Any] = []
    orch.events.subscribe(AgentSpoke, lambda e: seen.append(e))
    await orch._synthesize_remediation(_report())
    spoke = [e for e in seen if isinstance(e, AgentSpoke)]
    assert any(e.turn.agent == "Remediation Planner Agent" for e in spoke)
