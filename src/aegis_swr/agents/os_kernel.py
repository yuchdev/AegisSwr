"""OS Kernel Agent — system-environment specialist."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aegis_swr.agents.base import BaseAgent
from aegis_swr.core.schemas import AgentTurn, Hypothesis, OSKernelOutput

if TYPE_CHECKING:
    from aegis_swr.core.schemas import InvestigationState

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
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    async def run(self, state: InvestigationState) -> AgentTurn:
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})
        history = state.get("discussion_history", [])

        # Incorporate any Skeptic corrections from the previous round.
        corrections: list[str] = []
        if round_num > 1:
            for hist_turn in reversed(history):
                if (
                    hist_turn.get("agent") == "Skeptic Agent"
                    and hist_turn.get("turn_number") == round_num - 1
                ):
                    corrections = hist_turn.get("corrections", [])
                    break

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
        turn = AgentTurn(
            agent="OS Kernel Agent",
            turn_number=round_num,
            message=output.exception_summary.interpretation,
            hypotheses=hypotheses,
            confidence_score=output.confidence_score,
        )
        self._accumulate_tokens(state)
        return turn


