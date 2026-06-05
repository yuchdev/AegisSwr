"""MAS orchestration engine.

Builds a LangGraph :class:`StateGraph` that routes the investigation through
four specialised agents (OS Kernel → Code Analyst → Log Historian → Skeptic),
evaluates weighted consensus after every round, and terminates by routing to
either the output synthesiser or the HITL handler.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from loguru import logger

from aegis_swr.agents.code_analyst import CodeAnalystAgent
from aegis_swr.agents.log_historian import LogHistorianAgent
from aegis_swr.agents.os_kernel import OSKernelAgent
from aegis_swr.agents.skeptic import SkepticAgent
from aegis_swr.core.consensus import ConsensusEvaluator
from aegis_swr.core.data_adapter import DataAdapter
from aegis_swr.core.events import (
    AgentSpoke,
    ConsensusEvaluated,
    DomainEvent,
    EventBus,
    EvidenceExtracted,
    HumanInputRequired,
    InvestigationCompleted,
    InvestigationStarted,
)
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    AgentTurn,
    ConfidenceLevel,
    HITLRequest,
    Hypothesis,
    IncidentMode,
    InvestigationState,
    RCAReport,
)

from aegis_swr.backends.base import (
    AIAPIBackend,
    CodeBackend,
    DebugBackend,
    LogBackend,
    ObjectStore,
    RelationalStore,
    VectorStore,
)
from aegis_swr.config.settings import Settings
from aegis_swr.core.schemas import IncidentSource


class Orchestrator:
    """Assembles and drives the Synthetic War Room state graph"""

    def __init__(
        self,
        settings: Settings,
        ai_backend: AIAPIBackend,
        debug_backend: Optional[DebugBackend] = None,
        relational_store: Optional[RelationalStore] = None,
        object_store: Optional[ObjectStore] = None,
        vector_store: Optional[VectorStore] = None,
        log_backend: Optional[LogBackend] = None,
        code_backend: Optional[CodeBackend] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._settings = settings
        self._bus = event_bus or EventBus()
        self._ai = ai_backend
        self._debug = debug_backend
        self._relational = relational_store
        self._object = object_store
        self._vector = vector_store
        self._log = log_backend
        self._code = code_backend

        self._adapter = DataAdapter(settings)
        self._evaluator = ConsensusEvaluator(settings.agent_weights)
        self._os_agent = OSKernelAgent(ai_backend, settings)
        self._code_agent = CodeAnalystAgent(ai_backend, settings)
        self._historian = LogHistorianAgent(ai_backend, settings)
        self._skeptic = SkepticAgent(ai_backend, settings)

        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def run(self, source: IncidentSource) -> RCAReport:
        """Run the full investigation pipeline and return the final report"""
        # Deduplication gate — return cached report when available.
        if self._relational and source.dump_hash:
            cached = await self._relational.find_by_hash(source.dump_hash)
            if cached is not None:
                logger.info(f"Cache hit for dump_hash {source.dump_hash} — skipping analysis")
                return cached

        initial = self._initial_state(source)
        final = await self._graph.ainvoke(initial)
        return self._extract_report(final)

    @property
    def events(self) -> EventBus:
        """The bus on which this orchestrator publishes :class:`DomainEvent`s"""
        return self._bus

    async def stream_events(
        self,
        source: IncidentSource,
    ) -> AsyncGenerator[DomainEvent, None]:
        """Run the investigation, publishing and yielding neutral domain events.

        Views (Rich CLI, TUI, GUI) should subscribe to :attr:`events` rather
        than consume this generator; the yielded stream exists for drivers
        that need the final report or a transport translation (SSE).
        """
        initial = self._initial_state(source)
        started = InvestigationStarted(
            incident_id=str(initial["incident_id"]), source=source
        )
        self._bus.publish(started)
        yield started
        async for chunk in self._graph.astream(initial, stream_mode="updates"):
            for node_name, update in chunk.items():
                for event in self._events_from_update(node_name, update):
                    self._bus.publish(event)
                    yield event

    @staticmethod
    def _events_from_update(
        node_name: str, update: dict[str, Any]
    ) -> list[DomainEvent]:
        """Translate one LangGraph node update into domain events"""
        events: list[DomainEvent] = []
        if node_name == "data_adapter_node" and "incident_brief" in update:
            events.append(EvidenceExtracted(brief=update["incident_brief"]))
        history: list[dict[str, Any]] = update.get("discussion_history", [])
        if history:
            turn = AgentTurn.model_validate(history[-1])
            events.append(AgentSpoke(node=node_name, turn=turn))
        if "consensus_score" in update:
            events.append(
                ConsensusEvaluated(
                    score=float(update["consensus_score"]),
                    round_number=update.get("round_number"),
                )
            )
        if update.get("result") is not None:
            report = RCAReport.model_validate(update["result"])
            if update.get("hitl_pending", False):
                events.append(HumanInputRequired(report=report))
            else:
                events.append(InvestigationCompleted(report=report))
        return events

    async def run_streaming(
        self,
        source: IncidentSource,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run the investigation and yield SSE-compatible event dicts.

        Thin transport translation over :meth:`stream_events`; the dict shapes
        are the public streaming API contract.
        """
        async for event in self.stream_events(source):
            if isinstance(event, EvidenceExtracted):
                yield {"type": "data_adapter_complete", "data": event.brief}
            elif isinstance(event, AgentSpoke):
                yield {
                    "type": "agent_turn",
                    "node": event.node,
                    "data": event.turn.model_dump(mode="json"),
                }
            elif isinstance(event, ConsensusEvaluated):
                yield {
                    "type": "consensus_update",
                    "data": {"score": event.score, "round": event.round_number},
                }
            elif isinstance(event, InvestigationCompleted):
                yield {"type": "complete", "data": json.loads(event.report.model_dump_json())}
            elif isinstance(event, HumanInputRequired):
                yield {"type": "hitl_request", "data": json.loads(event.report.model_dump_json())}

    async def continue_investigation(
        self,
        incident_id: str,
        user_data: dict[str, Any],
    ) -> RCAReport:
        """Resume a HITL-pending investigation with data supplied by the user"""
        raise NotImplementedError(
            "continue_investigation requires Phase 6 storage backends. "
            "Implement after PostgresStore is available."
        )

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> Any:
        builder: StateGraph = StateGraph(InvestigationState)

        builder.add_node("data_adapter_node", self._data_adapter_node)
        builder.add_node("os_kernel_node", self._os_kernel_node)
        builder.add_node("code_analyst_node", self._code_analyst_node)
        builder.add_node("log_historian_node", self._log_historian_node)
        builder.add_node("skeptic_node", self._skeptic_node)
        builder.add_node("output_synthesizer_node", self._output_synthesizer_node)
        builder.add_node("hitl_node", self._hitl_node)

        builder.add_edge(START, "data_adapter_node")
        builder.add_edge("data_adapter_node", "os_kernel_node")
        builder.add_edge("os_kernel_node", "code_analyst_node")
        builder.add_edge("code_analyst_node", "log_historian_node")
        builder.add_edge("log_historian_node", "skeptic_node")
        builder.add_conditional_edges("skeptic_node", self._route_after_skeptic)
        builder.add_edge("output_synthesizer_node", END)
        builder.add_edge("hitl_node", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    async def _data_adapter_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        source = self._deserialise_source(state)
        brief = await self._adapter.process(
            source,
            debug_backend=self._debug,
            code_backend=self._code,
            log_backend=self._log,
        )
        return {"incident_brief": brief.model_dump(mode="json")}

    async def _os_kernel_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        turn = await self._os_agent.run(state)
        # Read token_tracker AFTER the agent call — _accumulate_tokens mutated it.
        tracker = dict(state.get("token_tracker") or {})
        history = list(state.get("discussion_history") or [])
        history.append(turn.model_dump(mode="json"))
        scores = dict(state.get("current_round_scores") or {})
        scores["os_kernel"] = turn.confidence_score
        primary = turn.hypotheses[0].model_dump(mode="json") if turn.hypotheses else None
        update: dict[str, Any] = {
            "discussion_history": history,
            "current_round_scores": scores,
            "token_tracker": tracker,
        }
        if primary:
            update["primary_hypothesis"] = primary
        return update

    async def _code_analyst_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        turn = await self._code_agent.run(state)
        tracker = dict(state.get("token_tracker") or {})
        history = list(state.get("discussion_history") or [])
        history.append(turn.model_dump(mode="json"))
        scores = dict(state.get("current_round_scores") or {})
        scores["code_analyst"] = turn.confidence_score
        primary = turn.hypotheses[0].model_dump(mode="json") if turn.hypotheses else None
        update: dict[str, Any] = {
            "discussion_history": history,
            "current_round_scores": scores,
            "token_tracker": tracker,
        }
        if primary:
            update["primary_hypothesis"] = primary
        return update

    async def _log_historian_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        turn = await self._historian.run(state, vector_store=self._vector)
        tracker = dict(state.get("token_tracker") or {})
        history = list(state.get("discussion_history") or [])
        history.append(turn.model_dump(mode="json"))
        scores = dict(state.get("current_round_scores") or {})
        scores["log_historian"] = turn.confidence_score
        return {
            "discussion_history": history,
            "current_round_scores": scores,
            "token_tracker": tracker,
        }

    async def _skeptic_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        turn = await self._skeptic.run(state)
        tracker = dict(state.get("token_tracker") or {})
        history = list(state.get("discussion_history") or [])
        history.append(turn.model_dump(mode="json"))
        scores = dict(state.get("current_round_scores") or {})
        scores["skeptic"] = turn.confidence_score

        # Calculate weighted consensus for this round.
        brief = state.get("incident_brief") or {}
        fault_str = brief.get("fault_class") or "unknown"
        try:
            fault_class = FaultClass(fault_str)
        except ValueError:
            fault_class = FaultClass.UNKNOWN
        cs = self._evaluator.calculate(scores, fault_class)

        # Determine convergence: Skeptic confirmed AND score meets threshold.
        skeptic_confirmed = turn.confidence_score >= 0.65  # MEDIUM or above
        prev_key = state.get("previous_hypothesis_key")
        primary = state.get("primary_hypothesis") or {}
        current_key = str(primary.get("root_cause") or "")
        same_hypothesis = prev_key is None or prev_key == current_key
        converged = skeptic_confirmed and self._evaluator.is_converged(
            cs, self._settings.core.consensus_threshold, same_hypothesis
        )

        round_num = state.get("round_number", 1)
        return {
            "discussion_history": history,
            "current_round_scores": scores,
            "consensus_score": cs,
            "is_converged": converged,
            "round_number": round_num + 1,
            "previous_hypothesis_key": current_key,
            "token_tracker": tracker,
        }

    async def _output_synthesizer_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        report = self._build_report(state, hitl_pending=False)
        if self._relational:
            try:
                await self._relational.save_report(report)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Could not save report to relational store: {exc}")
        if self._vector:
            try:
                await self._vector.upsert_incident(report)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Could not upsert report to vector store: {exc}")
        return {"result": json.loads(report.model_dump_json()), "hitl_pending": False}

    async def _hitl_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        report = self._build_report(state, hitl_pending=True)
        if self._relational:
            try:
                await self._relational.save_report(report)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Could not save HITL report: {exc}")
        return {"result": json.loads(report.model_dump_json()), "hitl_pending": True}

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _route_after_skeptic(self, state: InvestigationState) -> str:
        if state.get("is_converged"):
            return "output_synthesizer_node"
        # round_number has already been incremented by _skeptic_node.
        rounds_completed = (state.get("round_number") or 2) - 1
        max_rounds = self._settings.core.max_debate_rounds
        if rounds_completed >= max_rounds:
            return "hitl_node"
        return "os_kernel_node"

    # ------------------------------------------------------------------
    # Report construction
    # ------------------------------------------------------------------

    def _build_report(self, state: InvestigationState, *, hitl_pending: bool) -> RCAReport:
        history_raw = state.get("discussion_history") or []
        history = [AgentTurn.model_validate(t) for t in history_raw]
        cs = state.get("consensus_score") or 0.0
        primary_raw = state.get("primary_hypothesis") or {}
        primary = Hypothesis(
            root_cause=str(primary_raw.get("root_cause") or "Unknown"),
            faulting_module=primary_raw.get("faulting_module") or None,
            faulting_function=primary_raw.get("faulting_function") or None,
            evidence=list(primary_raw.get("evidence") or []),
            confidence=cs,
        )

        # Extract all alternative hypotheses from the agent turns.
        alt_hypotheses: list[Hypothesis] = []
        skeptic_challenges: list[str] = []
        mitigation: list[str] = []
        probabilistic_fix: Optional[str] = None
        for turn in history:
            if turn.agent == "Skeptic Agent":
                for h in turn.hypotheses:
                    skeptic_challenges.extend(h.evidence)
            if turn.agent == "Code Analyst Agent":
                for h in turn.hypotheses[1:]:
                    alt_hypotheses.append(h)
                # Extract fix from evidence annotation.
                if turn.hypotheses:
                    for ev in turn.hypotheses[0].evidence:
                        if ev.startswith("__fix__:"):
                            parts = ev.split(":", 2)
                            if len(parts) == 3:
                                probabilistic_fix = parts[2]

        tracker = state.get("token_tracker") or {}
        rounds_completed = max(1, (state.get("round_number") or 2) - 1)

        hitl_request: Optional[HITLRequest] = None
        if hitl_pending:
            hitl_request = HITLRequest(
                question=(
                    "The panel reached the debate limit without reaching consensus. "
                    "Please provide additional context to resume the investigation."
                ),
                context_summary=(
                    f"Consensus score after {rounds_completed} rounds: {cs:.0%}. "
                    f"Primary hypothesis: {primary.root_cause}"
                ),
                requested_data=[
                    "Any recent configuration changes or deployments.",
                    "Whether similar incidents occurred in the past 30 days.",
                    "Current resource utilisation (CPU, memory, disk) at incident time.",
                ],
            )

        brief = state.get("incident_brief") or {}
        brief_mode = brief.get("mode") or IncidentMode.CRASH_DUMP.value
        return RCAReport(
            mode=IncidentMode(brief_mode),
            dump_hash=brief.get("dump_hash"),
            symbol_resolution_score=brief.get("symbol_resolution_score"),
            root_cause=primary.root_cause,
            faulting_module=primary.faulting_module,
            faulting_function=primary.faulting_function,
            confidence_score=cs,
            confidence_level=ConfidenceLevel.from_score(cs),
            primary_hypothesis=primary,
            alternative_hypotheses=alt_hypotheses,
            skeptic_challenges=skeptic_challenges,
            agent_dialogue=history,
            consensus_rounds=rounds_completed,
            mitigation_instructions=mitigation,
            probabilistic_fix=probabilistic_fix,
            fix_confidence=cs if probabilistic_fix else None,
            hitl_request=hitl_request,
            total_input_tokens=tracker.get("input_tokens", 0),
            total_output_tokens=tracker.get("output_tokens", 0),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _initial_state(self, source: IncidentSource) -> InvestigationState:
        return InvestigationState(
            incident_id=str(uuid.uuid4()),
            source=json.loads(source.model_dump_json()),
            discussion_history=[],
            round_number=1,
            consensus_score=0.0,
            is_converged=False,
            primary_hypothesis=None,
            previous_hypothesis_key=None,
            current_round_scores={},
            hitl_pending=False,
            token_tracker={"input_tokens": 0, "output_tokens": 0},
            result=None,
            error=None,
        )

    @staticmethod
    def _deserialise_source(state: InvestigationState) -> IncidentSource:
        from aegis_swr.core.schemas import IncidentSource as IS
        return IS.model_validate(state.get("source") or {})

    @staticmethod
    def _extract_report(final_state: dict[str, Any]) -> RCAReport:
        result = final_state.get("result")
        if result is None:
            raise RuntimeError("Graph terminated without producing a report.")
        return RCAReport.model_validate(result)
