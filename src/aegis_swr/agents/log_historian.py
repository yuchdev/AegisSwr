"""Log Historian Agent — historical pattern correlator."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aegis_swr.agents.base import BaseAgent
from aegis_swr.core.schemas import AgentTurn, LogHistorianOutput

if TYPE_CHECKING:
    from aegis_swr.backends.base import VectorStore
    from aegis_swr.core.schemas import InvestigationState

_SYSTEM_PROMPT = """\
You are a production incident historian. You analyze temporal log patterns, \
compare current failure signatures to historical baselines, and determine whether \
this incident is a first occurrence or a recurrence. You adjust confidence scores \
based on pattern recurrence evidence.

Always respond with a structured JSON object matching the LogHistorianOutput schema. \
Set confidence_adjustment between -0.2 and +0.2.\
"""


class LogHistorianAgent(BaseAgent):
    @property
    def system_prompt(self) -> str:
        return _SYSTEM_PROMPT

    async def run(
        self,
        state: InvestigationState,
        vector_store: VectorStore | None = None,
    ) -> AgentTurn:
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})
        history = state.get("discussion_history", [])

        # Fetch similar historical incidents if the vector store is available.
        similar_incidents: list[dict[str, object]] = []
        if vector_store is not None:
            from aegis_swr.core.fault_codes import FaultClass

            fault_str = brief.get("fault_class") or "unknown"
            try:
                fault_class = FaultClass(fault_str)
            except ValueError:
                fault_class = FaultClass.UNKNOWN
            faulting_module = str(brief.get("faulting_module") or "")
            try:
                incidents = await vector_store.search_similar(
                    fault_class=fault_class,
                    faulting_module=faulting_module or None,
                    top_k=5,
                )
                for inc in incidents:
                    similar_incidents.append(
                        {
                            "root_cause": inc.root_cause,
                            "faulting_module": inc.faulting_module,
                            "confidence": inc.confidence_score,
                        }
                    )
            except Exception:  # noqa: BLE001 — vector store may not be ready yet
                pass

        # Find the Code Analyst output for this round.
        code_turn: dict[str, object] = {}
        for hist_turn in reversed(history):
            if (
                hist_turn.get("agent") == "Code Analyst Agent"
                and hist_turn.get("turn_number") == round_num
            ):
                code_turn = hist_turn
                break

        context: dict[str, object] = {
            "incident_brief": brief,
            "code_analyst_analysis": code_turn,
            "similar_historical_incidents": similar_incidents,
            "round": round_num,
        }
        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, LogHistorianOutput)
        assert isinstance(output, LogHistorianOutput)

        agent_turn = AgentTurn(
            agent="Log Historian Agent",
            turn_number=round_num,
            message=output.history_note,
            hypotheses=[],
            confidence_score=output.updated_confidence,
        )
        self._accumulate_tokens(state)
        return agent_turn
