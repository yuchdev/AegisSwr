"""OS Kernel Agent - system-environment specialist"""

from __future__ import annotations

import json
from typing import ClassVar

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    Hypothesis,
    InvestigationState,
    OSKernelOutput,
)

_SYSTEM_PROMPT = """\
You are an expert OS-level debugger and kernel engineer. Your primary focus is \
environmental constraints: memory allocation state, I/O latency, driver conflicts, \
thread blocking primitives, and hardware signal mapping. You map raw exception codes \
to FaultClass values and construct the first structural hypothesis about what went \
wrong in the system environment.

Always respond with a structured JSON object matching the OSKernelOutput schema. \
Set confidence_score to a value between 0.0 and 1.0 reflecting your certainty.\
"""


class OSKernelAgent(BaseAgent):
    """Investigator agent that reasons about OS/kernel-level crash causes."""

    agent_key: ClassVar[str] = "os_kernel"
    display_name: ClassVar[str] = "OS Kernel Agent"
    category: ClassVar[AgentCategory] = "base"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.35

    @property
    def system_prompt(self) -> str:
        """Return the OS-kernel investigator system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        """Analyse the incident from an OS/kernel angle and return the agent's turn.

        :param state: the current investigation state (brief, arbiter feedback).
        :return: the OS-kernel agent's :class:`AgentTurn`.
        """
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        # Incorporate any arbiter corrections carried over from the previous round.
        corrections: list[str] = state.get("latest_arbiter_feedback") or []

        context: dict[str, object] = {"incident_brief": brief, "round": round_num}
        if brief.get("low_symbol_coverage_warning"):
            context["warning"] = brief["low_symbol_coverage_warning"]
        if corrections:
            context["skeptic_corrections_from_previous_round"] = corrections

        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, OSKernelOutput)
        assert isinstance(output, OSKernelOutput)

        hypotheses = [
            Hypothesis(
                root_cause=h.root_cause,
                faulting_module=h.faulting_module,
                faulting_function=h.faulting_function,
                evidence=h.evidence,
                confidence=h.confidence,
            )
            for h in output.hypotheses
        ]
        turn = self.make_turn(
            turn_number=round_num,
            message=output.exception_summary.interpretation,
            hypotheses=hypotheses,
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return turn
