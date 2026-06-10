"""MAS orchestration engine.

Builds a LangGraph :class:`StateGraph` that routes the investigation through
four specialized agents (OS Kernel → Code Analyst → Log Historian → Skeptic),
evaluates weighted consensus after every round, and terminates by routing to
either the output synthesizer or the HITL handler.
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
        """Initialize the Orchestrator with required backends and storage.

        Args:
            settings: Application configuration and tuning parameters.
            ai_backend: LLM provider (Gemini, OpenAI, etc.) for agent reasoning.
            debug_backend: Optional debugger backend for crash dump extraction.
            relational_store: Optional database for persisting and querying reports.
            object_store: Optional object storage for large artifacts.
            vector_store: Optional vector database for semantic similarity search of prior incidents.
            log_backend: Optional log aggregation source for forensic analysis.
            code_backend: Optional source code repository access for symbol lookup.
            event_bus: Optional custom event publisher; uses default if None.
        """
        self._settings = settings
        self._bus = event_bus or EventBus()
        self._ai = ai_backend
        self._debug = debug_backend
        self._relational = relational_store
        self._object = object_store
        self._vector = vector_store
        self._log = log_backend
        self._code = code_backend

        # Prior reports for the Log Historian's recurrence check, loaded lazily
        # once per investigation and reused across debate rounds.
        self._history_cache: Optional[list[RCAReport]] = None

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
        """Run the full investigation pipeline and return the final report
        Deduplication gate - return cached report when available.
        """
        if self._relational and source.dump_hash:
            cached = await self._relational.find_by_hash(source.dump_hash)
            if cached is not None:
                logger.info(f"Cache hit for dump_hash {source.dump_hash} - skipping analysis")
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
        """Construct the LangGraph state machine for multi-agent investigation.

        Builds a directed acyclic graph with nodes for data extraction, four
        specialized agents, and conditional routing. Routes converged cases to
        output synthesis or max-round cases to HITL.

        Returns:
            A compiled LangGraph StateGraph ready for streaming or batch invocation.
        """
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
        """Orchestrate forensic data extraction from all available sources.

        Calls the DataAdapter to ingest and normalize the incident dump, logs,
        and code via pluggable backends. Produces a structured brief containing
        fault class, symbol resolution score, and extracted evidence.

        Args:
            state: Current investigation state containing the incident source.

        Returns:
            Update dict with the 'incident_brief' key containing the forensic summary.
        """
        source = self._deserialize_source(state)
        brief = await self._adapter.process(
            source,
            debug_backend=self._debug,
            code_backend=self._code,
            log_backend=self._log,
        )
        return {"incident_brief": brief.model_dump(mode="json")}

    @staticmethod
    def _fold_turn(
        state: InvestigationState, turn: AgentTurn, agent_key: str
    ) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
        """Fold a finished agent turn into fresh copies of the shared state.

        Reads ``token_tracker`` AFTER the agent call (agents mutate it via
        ``_accumulate_tokens``), appends the turn to the discussion history,
        and records the turn's confidence score under ``agent_key``. The
        returned containers are copies safe to mutate and return in a node's
        update dict.

        Args:
            state: Current investigation state.
            turn: The agent turn that just completed.
            agent_key: Score key under which to record the turn's confidence.

        Returns:
            Tuple of (token_tracker, discussion_history, current_round_scores).
        """
        tracker = dict(state.get("token_tracker") or {})
        history = list(state.get("discussion_history") or [])
        history.append(turn.model_dump(mode="json"))
        scores = dict(state.get("current_round_scores") or {})
        scores[agent_key] = turn.confidence_score
        return tracker, history, scores

    async def _os_kernel_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        """Invoke the OS/Kernel Agent for system-level fault analysis.

        The OS Kernel Agent examines kernel context (interrupts, CPU state, memory
        state) to form primary and alternative hypotheses. Its confidence score
        is recorded for weighted consensus calculation.

        Args:
            state: Current investigation state with extracted evidence.

        Returns:
            Update dict containing agent turn, scores, and updated discussion history.
        """
        turn = await self._os_agent.run(state)
        tracker, history, scores = self._fold_turn(state, turn, "os_kernel")
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
        """Invoke the Code Analyst Agent for application-level fault diagnosis.

        The Code Analyst examines stack traces, register contents, and symbols to
        diagnose application faults. Can extract probabilistic fixes from its
        evidence annotations (prefixed with '__fix__:').

        Args:
            state: Current investigation state.

        Returns:
            Update dict with agent turn, confidence scores, and hypotheses.
        """
        turn = await self._code_agent.run(state)
        tracker, history, scores = self._fold_turn(state, turn, "code_analyst")
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
        """Invoke the Log Historian Agent for temporal and recurrence analysis.

        The Log Historian compares the current incident against prior reports in
        the vector store (loaded once and cached) to identify recurrence patterns,
        escalation sequences, and trending behaviors.

        Args:
            state: Current investigation state.

        Returns:
            Update dict with agent turn and consensus scores.
        """
        history = await self._load_history()
        turn = await self._historian.run(
            state, vector_store=self._vector, history=history
        )
        tracker, history, scores = self._fold_turn(state, turn, "log_historian")
        return {
            "discussion_history": history,
            "current_round_scores": scores,
            "token_tracker": tracker,
        }

    async def _skeptic_node(
        self, state: InvestigationState
    ) -> dict[str, Any]:
        """Invoke the Skeptic Agent to challenge the emerging consensus.

        The Skeptic critically examines all prior agent hypotheses and evidence,
        raising alternative explanations and gaps. After the Skeptic's turn,
        consensus is calculated, and convergence is evaluated: if the Skeptic
        confirmed AND consensus meets the threshold AND hypothesis remained stable,
        the investigation converges.

        Args:
            state: Current investigation state with all prior agent turns.

        Returns:
            Update dict with consensus score, convergence flag, and round tracking.
        """
        turn = await self._skeptic.run(state)
        tracker, history, scores = self._fold_turn(state, turn, "skeptic")

        # Calculate weighted consensus for this round.
        brief = state.get("incident_brief") or {}
        fault_str = brief.get("fault_class") or "unknown"
        try:
            fault_class = FaultClass(fault_str)
        except ValueError:
            fault_class = FaultClass.UNKNOWN
        cs = self._evaluator.calculate(scores, fault_class)

        # Determine convergence: Skeptic confirmed AND the score meets threshold.
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
        """Build the final RCA report when consensus is reached.

        Synthesises all agent turns, hypotheses, and scores into a structured
        RCAReport. Persists the report to relational and vector stores for
        future recurrence matching (best-effort; failures are logged but not fatal).

        Args:
            state: Converged investigation state with consensus above the threshold.

        Returns:
            Update dict with 'result' containing the final RCAReport and
            'hitl_pending' set to False.
        """
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
        """Build a Human-In-The-Loop report when max debate rounds are exhausted.

        When the panel cannot converge within the configured debate limit, the
        current state is packaged into an RCAReport with an embedded HITLRequest
        prompting the user for additional context. The report is persisted to
        relational storage for resumption in Phase 6.

        Args:
            state: Investigation state after max rounds reached.

        Returns:
            Update dict with 'result' containing RCAReport and 'hitl_pending'
            set to True, signaling a pause for user input.
        """
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
        """Determine the next node after the Skeptic has reported.

        The routing logic is:
          - If converged (consensus ≥ threshold + Skeptic MEDIUM+ confidence):
            synthesize and return the final report.
          - Else if max_rounds for debate is reached: invoke HITL for user input.
          - Else: loop back to OS Kernel Agent for the next debate round.

        Args:
            state: Current investigation state with a convergence flag set.

        Returns:
            Node name: 'output_synthesizer_node', 'hitl_node', or 'os_kernel_node'.
        """
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

    @staticmethod
    def _build_report(state: InvestigationState, *, hitl_pending: bool) -> RCAReport:
        """Synthesize investigation state into a complete RCA report.

        Extracts the primary hypothesis, alternative hypotheses, Code Analyst
        probabilistic fixes (annotated with '__fix__:' prefix), Skeptic challenges,
        and consensus metrics. Builds an HITLRequest if the investigation is
        inconclusive and awaiting user input.

        Args:
            state: Final investigation state with all agent dialogue and scores.
            hitl_pending: If True, includes a HITLRequest and sets the flag in
                         the report. If False, produces a completed report.

        Returns:
            RCAReport with all synthesized findings, evidence, and metadata.
        """
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

    """Upper bound on prior reports pulled for the recurrence comparison."""
    _HISTORY_LIMIT = 200

    async def _load_history(self) -> list[RCAReport]:
        """Prior reports for recurrence matching, loaded once and cached.

        Reads from the relational store (the same place completed reports are
        persisted), so the Log Historian compares against every incident saved
        under the active ``--store``/``--store-config``.  Returns an empty list
        if no store is configured or the load fails.
        """
        if self._history_cache is not None:
            return self._history_cache
        if self._relational is None:
            self._history_cache = []
            return self._history_cache
        try:
            self._history_cache = await self._relational.load_recent(
                limit=self._HISTORY_LIMIT
            )
        except Exception as exc:  # noqa: BLE001 - history is best-effort
            logger.warning("Failed to load incident history: {}", exc)
            self._history_cache = []
        return self._history_cache

    @staticmethod
    def _initial_state(source: IncidentSource) -> InvestigationState:
        """Construct the initial state for a new investigation.

        Generates a unique incident ID (UUID4) and seeds the state with empty
        discussion history, zero consensus, and token tracking set to zero.
        The incident source is serialized as JSON for transparent state passing.

        Args:
            source: Incident source (crash dump, log file reference, etc.).

        Returns:
            InvestigationState ready for graph execution.
        """
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
    def _deserialize_source(state: InvestigationState) -> IncidentSource:
        """Reconstruct IncidentSource from a serialized state.

        Extracts and validates the 'source' dict from the investigation state,
        which was stored as JSON during state initialization.

        Args:
            state: Investigation state containing a serialized source dict.

        Returns:
            Validated IncidentSource object.
        """
        return IncidentSource.model_validate(state.get("source") or {})

    @staticmethod
    def _extract_report(final_state: dict[str, Any]) -> RCAReport:
        """Extract and validate the final RCA report from the graph state.

        The final state dict is produced by either the output synthesizer or HITL
        node and contains a 'result' key with the serialised RCAReport.

        Args:
            final_state: Terminal graph state dict.

        Returns:
            Validated RCAReport.

        Raises:
            RuntimeError: If the graph terminated without producing a report.
        """
        result = final_state.get("result")
        if result is None:
            raise RuntimeError("Graph terminated without producing a report.")
        return RCAReport.model_validate(result)
