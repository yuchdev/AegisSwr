"""Code Analyst Agent - software architecture and logic error specialist"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    CodeAnalystOutput,
    Hypothesis,
    InvestigationState,
)

_SYSTEM_PROMPT = """\
You are a senior software engineer specialized in debugging algorithmic flaws, \
memory management errors, race conditions, uninitialized pointers, and \
language-specific anti-patterns. You receive an ExceptionSummary from the OS Kernel \
Agent and the full stack trace. Your task is to identify the specific code-level \
root cause: faulting function, line of code, and the logical path that led to \
the fault.

Always respond with a structured JSON object matching the CodeAnalystOutput schema. \
Include a probabilistic_fix (unified diff) when you have high confidence in the fix.\
"""


class CodeAnalystAgent(BaseAgent):
    agent_key: ClassVar[str] = "code_analyst"
    display_name: ClassVar[str] = "Code Analyst Agent"
    category: ClassVar[AgentCategory] = "base"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    contributes_fix: ClassVar[bool] = True
    default_weight: ClassVar[float] = 0.35

    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        # Read the immediately-preceding investigator turn as context.
        os_kernel_output: dict[str, Any] = state.get("latest_turn_this_round") or {}

        context: dict[str, object] = {
            "incident_brief": brief,
            "os_kernel_analysis": os_kernel_output,
            "round": round_num,
        }
        if brief.get("user_assumption"):
            context["user_assumption"] = brief["user_assumption"]

        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, CodeAnalystOutput)
        assert isinstance(output, CodeAnalystOutput)

        primary = Hypothesis(
            root_cause=output.rca.root_cause,
            faulting_module=output.rca.faulting_module,
            faulting_function=output.rca.faulting_function,
            evidence=output.rca.evidence,
            confidence=output.rca.confidence,
        )
        # Encode any probabilistic fix into the top hypothesis's evidence list
        # so the output synthesizer can extract it later without a separate field.
        primary_evidence = list(primary.evidence)
        if output.probabilistic_fix:
            primary_evidence.append(f"__fix__:{output.fix_language or 'unknown'}:{output.probabilistic_fix}")
        primary = Hypothesis(
            root_cause=primary.root_cause,
            faulting_module=primary.faulting_module,
            faulting_function=primary.faulting_function,
            evidence=primary_evidence,
            confidence=primary.confidence,
        )
        agent_turn = self.make_turn(
            turn_number=round_num,
            message=f"Root cause: {output.rca.root_cause}",
            hypotheses=[primary] + list(output.alternative_hypotheses),
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return agent_turn
