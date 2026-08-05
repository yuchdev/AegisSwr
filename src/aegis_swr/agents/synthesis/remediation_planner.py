"""Remediation Planner Agent - the sole synthesis-tier agent (Milestone 0002).

Runs exactly once after the debate converges, turning a confirmed
:class:`~aegis_swr.core.schemas.RCAReport` into an ordered, idempotent,
rollback-covered :class:`~aegis_swr.core.schemas.RemediationPlan`. It is not a
debate voter and carries no consensus weight.

Safety (incident-analyst rule): the plan is advisory. Nothing here dispatches a
step to any execution engine; execution requires an operator to confirm with
``AEGIS_PROD_CONFIRMED=1``, and any ``requires_human_approval`` plan is
surfaced as advisory-only.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    ConfidenceLevel,
    InvestigationState,
    RCAReport,
    RemediationPlan,
)

_SYSTEM_PROMPT = """\
You are a remediation engineer specializing in post-incident playbook \
construction. Your sole task is to convert a confirmed Root Cause Analysis into \
a structured, executable remediation plan.

Every step in your plan MUST be idempotent. A step is idempotent when running \
it a second time produces no additional side-effects. If you cannot make a step \
idempotent, you MUST explain why in the `risk` field and provide a precise \
`rollback` action.

Every step MUST include a `rollback` field. For read-only verification steps, \
use the literal `rollback` value "read-only: no state change". An empty \
`rollback` is never acceptable.

Order steps in the sequence: contain -> remediate -> verify. Do not include any \
detection steps (the RCA already confirms the fault). Do not include steps that \
require information not present in the provided RCA.

Any step that modifies production state MUST set `requires_human_approval` to \
true. When in doubt, require approval.

Respond with a JSON object matching the RemediationPlan schema exactly. Do not \
include commentary outside the JSON object.\
"""

_SEVERITY_BY_CONFIDENCE: dict[ConfidenceLevel, str] = {
    ConfidenceLevel.HIGH: "P1",
    ConfidenceLevel.MEDIUM: "P2",
    ConfidenceLevel.LOW: "P3",
}


class RemediationPlannerAgent(BaseAgent):
    """Synthesis-tier agent that builds a remediation playbook from a confirmed RCA.

    Distinct from every forensic specialist: it is filtered out of
    ``create_agent_panel`` by ``category == "synthesis"``, runs once inside the
    orchestrator's synthesizer node, and is skipped entirely on the HITL path.
    Its verdict is advisory - never an authorization to auto-remediate.
    """

    agent_key: ClassVar[str] = "remediation_planner"
    display_name: ClassVar[str] = "Remediation Planner Agent"
    category: ClassVar[AgentCategory] = "synthesis"
    role: ClassVar[AgentRole] = AgentRole.SYNTHESIS
    default_weight: ClassVar[float] = 0.0

    @property
    def system_prompt(self) -> str:
        """Return the remediation-planner synthesis system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Reject the investigator entry point; this synthesis agent uses ``run_synthesis``."""
        raise NotImplementedError("RemediationPlannerAgent is synthesis-tier; call run_synthesis()")

    async def run_synthesis(self, report: RCAReport) -> tuple[AgentTurn, RemediationPlan]:
        """Build a remediation plan from a confirmed, converged *report*.

        Only planning-relevant, PII-scrubbed report fields are sent to the model;
        raw payload (``raw_text_excerpt``, full ``agent_dialogue``, stack frames)
        is never included.

        :param report: The confirmed RCA report to plan remediation for.
        :type report: RCAReport
        :return: A tuple of the synthesis :class:`AgentTurn` and the plan.
        :rtype: tuple[AgentTurn, RemediationPlan]
        """
        context: dict[str, Any] = {
            "root_cause": report.root_cause,
            "faulting_module": report.faulting_module,
            "faulting_function": report.faulting_function,
            "confidence_score": report.confidence_score,
            "confidence_level": report.confidence_level.value,
            "primary_hypothesis": {
                "root_cause": report.primary_hypothesis.root_cause,
                "evidence": report.primary_hypothesis.evidence,
            },
            "mitigation_instructions": report.mitigation_instructions,
        }
        messages = [{"role": "user", "content": json.dumps(context)}]
        plan = await self._ai.generate(self.system_prompt, messages, RemediationPlan)
        assert isinstance(plan, RemediationPlan)

        turn = self.make_turn(
            turn_number=0,
            message=plan.summary.splitlines()[0] if plan.summary else "Remediation plan produced.",
            hypotheses=[],
            confidence_score=plan.confidence,
        )
        return turn, plan


def remediation_plan_to_playbook_dict(plan: RemediationPlan, report: RCAReport) -> dict[str, Any]:
    """Adapt a :class:`RemediationPlan` into a ``/playbook-validate``-shaped dict.

    Pure function (no I/O, no AI): used for export/validation only, never on the
    hot path. Injects the playbook- and step-level fields the ``/playbook-validate``
    skill requires that the runtime schema does not carry natively.

    :param plan: The remediation plan to export.
    :type plan: RemediationPlan
    :param report: The RCA report the plan was built from (source of id/trigger).
    :type report: RCAReport
    :return: A ``/playbook-validate``-compatible playbook dict.
    :rtype: dict[str, Any]
    """
    return {
        "id": str(report.incident_id),
        "name": f"Remediation for {report.root_cause[:80]}",
        "trigger": f"{report.mode.value}/{report.faulting_module or 'unknown'}",
        "owner": "aegis_swr:remediation_planner",
        "severity": _SEVERITY_BY_CONFIDENCE.get(report.confidence_level, "P3"),
        "steps": [
            {
                "id": f"step-{step.order:02d}",
                "description": step.action,
                "action": step.action,
                "idempotent": step.idempotent,
                "rollback": step.rollback,
                "requires_authorisation": step.requires_human_approval,
                "timeout": "300s",
            }
            for step in plan.steps
        ],
    }
