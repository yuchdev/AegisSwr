"""Code Analyst Agent - software architecture and logic error specialist"""
from __future__ import annotations

import json

from aegis_swr.agents.base import BaseAgent
from aegis_swr.core.schemas import AgentTurn, CodeAnalystOutput, Hypothesis

from aegis_swr.core.schemas import InvestigationState

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
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})
        history = state.get("discussion_history", [])

        # Find the most recent OS Kernel turn for this round.
        os_kernel_output: dict[str, object] = {}
        for hist_turn in reversed(history):
            if (
                hist_turn.get("agent") == "OS Kernel Agent"
                and hist_turn.get("turn_number") == round_num
            ):
                os_kernel_output = hist_turn
                break

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
            primary_evidence.append(
                f"__fix__:{output.fix_language or 'unknown'}:{output.probabilistic_fix}"
            )
        primary = Hypothesis(
            root_cause=primary.root_cause,
            faulting_module=primary.faulting_module,
            faulting_function=primary.faulting_function,
            evidence=primary_evidence,
            confidence=primary.confidence,
        )
        agent_turn = AgentTurn(
            agent="Code Analyst Agent",
            turn_number=round_num,
            message=f"Root cause: {output.rca.root_cause}",
            hypotheses=[primary] + list(output.alternative_hypotheses),
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return agent_turn
