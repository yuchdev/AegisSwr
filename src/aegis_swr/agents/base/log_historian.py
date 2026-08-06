"""Log Historian Agent - historical pattern correlator"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Optional

from loguru import logger

from aegis_swr.agents.base import AgentCategory, BaseAgent
from aegis_swr.backends.base import VectorStore
from aegis_swr.core.exceptions import VectorStoreError
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.incident_similarity import analyze_history
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    InvestigationState,
    LogHistorianOutput,
    RCAReport,
)

_SYSTEM_PROMPT = """\
You are a production incident historian. You analyze temporal log patterns, \
compare current failure signatures to historical baselines, and determine whether \
this incident is a first occurrence or a recurrence. You adjust confidence scores \
based on pattern recurrence evidence.

The user message includes a `recurrence_analysis` block precomputed by matching \
this incident's forensic signature (faulting module/function, source location, \
exception code, failure bucket) against stored reports. Treat it as ground truth: \
- If `matched_incidents` is non-empty this is a RECURRENCE - say so explicitly, \
  cite how many prior reports match and the recurrence probability, and adjust \
  confidence UPWARD (use `suggested_confidence_adjustment` as your guide). \
- Only call the incident first-observed when `matched_incidents` is empty. \
Never claim "no historical incidents were provided" when `history_size` > 0.

Always respond with a structured JSON object matching the LogHistorianOutput schema. \
Set confidence_adjustment between -0.2 and +0.2.\
"""


class LogHistorianAgent(BaseAgent):
    """Agent that determines whether an incident is a recurrence by comparing
    the current incident's forensic signature against historical reports and
    optional semantic vector-search candidates.

    The agent produces a LogHistorianOutput object that adjusts the overall
    incident confidence based on recurrence evidence.

    :raises: None — failures in optional vector-store enrichment are handled
             internally and do not propagate.
    """

    agent_key: ClassVar[str] = "log_historian"
    display_name: ClassVar[str] = "Log Historian Agent"
    category: ClassVar[AgentCategory] = "base"
    role: ClassVar[AgentRole] = AgentRole.INVESTIGATOR
    default_weight: ClassVar[float] = 0.17

    @property
    def system_prompt(self) -> str:
        """Return the log-historian investigator system prompt for this agent."""
        return _SYSTEM_PROMPT

    async def run(
        self,
        state: InvestigationState,
        vector_store: Optional[VectorStore] = None,
        history: Optional[list[RCAReport]] = None,
    ) -> AgentTurn:
        """Run the LogHistorianAgent for one round.

        Correlates the provided incident brief with historical reports and an
        optional VectorStore to determine recurrence and suggest a confidence
        adjustment.

        :param state: Current investigation state (contains incident_id,
                      round_number, incident_brief, and latest_turn_this_round).
        :param vector_store: Optional vector store used for semantic similarity
                             searches.
        :param history: Optional list of prior RCAReport objects to compare
                        against.
        :returns: An AgentTurn summarising the historian's finding and updated
                  confidence score.
        """
        round_num = state.get("round_number", 1)
        brief = state.get("incident_brief", {})

        # Correlate the current incident's forensic signature against prior
        # reports by metadata (module, function, source line, exception code,
        # failure bucket).  This is the primary recurrence signal - it works
        # whenever stored reports are available, with or without a vector store.
        reports = list(history or [])
        if vector_store is not None:
            reports.extend(await self._vector_candidates(brief, vector_store))

        analysis = analyze_history(brief, reports, exclude_incident_id=state.get("incident_id"))

        # Read the immediately-preceding investigator turn as context.
        code_turn: dict[str, Any] = state.get("latest_turn_this_round") or {}

        context: dict[str, object] = {
            "incident_brief": brief,
            "code_analyst_analysis": code_turn,
            "recurrence_analysis": analysis.as_context(),
            "round": round_num,
        }
        messages = [{"role": "user", "content": json.dumps(context)}]
        output = await self._ai.generate(self.system_prompt, messages, LogHistorianOutput)
        assert isinstance(output, LogHistorianOutput)

        agent_turn = self.make_turn(
            turn_number=round_num,
            message=output.history_note,
            confidence_score=output.updated_confidence,
        )
        self._accumulate_tokens(state)
        return agent_turn

    @staticmethod
    async def _vector_candidates(brief: dict[str, object], vector_store: VectorStore) -> list[RCAReport]:
        """Best-effort fetch of similar reports from a semantic vector store.

        Optional enrichment on top of the relational history; failures here are
        swallowed so a missing/empty vector store never blocks the metadata
        comparison.
        """
        fault_str = brief.get("fault_class") or "unknown"
        try:
            fault_class = FaultClass(fault_str)
        except ValueError:
            fault_class = FaultClass.UNKNOWN
        faulting_module = str(brief.get("faulting_module") or "")
        try:
            return await vector_store.search_similar(
                fault_class=fault_class,
                faulting_module=faulting_module or None,
                top_k=5,
            )
        except VectorStoreError as exc:
            logger.debug("LogHistorian: vector-store similarity search failed; returning empty candidates: {}", exc)
            return []
