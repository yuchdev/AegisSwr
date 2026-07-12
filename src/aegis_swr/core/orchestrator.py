"""MAS orchestration engine.

Builds, per run, a LangGraph :class:`StateGraph` that routes the investigation
through a *dynamically resolved* panel of agents: the investigators (chained in
priority order) then exactly one arbiter, which gates convergence. Weighted
consensus is evaluated after every round, and the graph terminates by routing to
either the output synthesizer or the HITL handler.

The Orchestrator is a pure container/driver - it never chooses the panel. Team
formation happens up front: the incident brief is extracted directly, a
:class:`~aegis_swr.core.panel_strategy.PanelResolver` turns it (plus any explicit
config/CLI selection) into :class:`~aegis_swr.agents.base.AgentSpec` objects,
and :func:`~aegis_swr.agents.panel.resolve_panel` instantiates the live panel the
graph is then built from.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from loguru import logger

from aegis_swr.agents.base import AgentSpec, BaseAgent, LogHistorianAgent
from aegis_swr.agents.panel import resolve_consensus_weights, resolve_panel
from aegis_swr.agents.synthesis.remediation_planner import RemediationPlannerAgent
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
    PanelAgentDescriptor,
    PanelResolved,
)
from aegis_swr.core.exceptions import AegisSWRError, RelationalStoreError, VectorStoreError
from aegis_swr.core.panel_strategy import PanelResolver
from aegis_swr.core.schemas import (
    AgentRole,
    AgentTurn,
    ConfidenceLevel,
    HITLRequest,
    Hypothesis,
    IncidentBrief,
    IncidentMode,
    IncidentSource,
    InvestigationState,
    RCAReport,
)

# A LangGraph node is an async callable taking the shared state and returning a
# partial state-update dict. The generic node factory produces these.
AgentNode = Callable[[InvestigationState], Awaitable[dict[str, Any]]]


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
        panel_resolver: Optional[PanelResolver] = None,
        explicit_specs: Optional[list[AgentSpec]] = None,
    ):
        """Initialize the Orchestrator with required backends and storage.

        The Orchestrator no longer instantiates a fixed set of agents or builds a
        static graph at construction time. Instead it holds the collaborators used
        to *resolve* and *build* a fresh panel/graph on every :meth:`run` /
        :meth:`stream_events` call.

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
            panel_resolver: Optional panel-selection resolver; defaults to a
                :class:`~aegis_swr.core.panel_strategy.PanelResolver` over
                ``settings``. Injectable so tests can supply deterministic panels.
            explicit_specs: Optional per-incident agent specs supplied via
                config/CLI. When non-empty they win over auto-selection; when
                ``None`` the resolver auto-selects the panel from the brief.
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
        # ConsensusEvaluator is now stateless (weight resolution lives in
        # agents/panel.py); one shared instance is enough.
        self._evaluator = ConsensusEvaluator()
        self._panel_resolver = panel_resolver or PanelResolver(settings)
        self._explicit_specs = explicit_specs

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

        # Phase 1: extract the brief directly (no longer a graph node).
        brief = await self._extract_brief(source)
        # Phases 2-3: resolve the panel and compile a fresh graph for this run.
        _panel, graph, recursion_limit = await self._resolve_and_build(brief)
        initial = self._initial_state(source, brief)
        final = await graph.ainvoke(initial, config={"recursion_limit": recursion_limit})
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

        Because the data adapter and panel resolution are no longer graph nodes,
        the :class:`~aegis_swr.core.events.EvidenceExtracted` and
        :class:`~aegis_swr.core.events.PanelResolved` events are published
        manually - right after the brief is extracted and right after the panel
        is resolved - before entering the debate-only ``astream`` loop.
        """
        incident_id = str(uuid.uuid4())
        started = InvestigationStarted(incident_id=incident_id, source=source)
        self._bus.publish(started)
        yield started

        # Phase 1: extract the brief directly, then announce it.
        brief = await self._extract_brief(source)
        evidence = EvidenceExtracted(brief=brief.model_dump(mode="json"))
        self._bus.publish(evidence)
        yield evidence

        # Phases 2-3: resolve the panel, announce it, then compile the graph.
        panel, graph, recursion_limit = await self._resolve_and_build(brief)
        resolved = PanelResolved(
            panel=[
                PanelAgentDescriptor(
                    node_name=self._node_name(agent),
                    display_name=agent.display_name,
                    role=agent.role,
                )
                for agent in panel
            ]
        )
        self._bus.publish(resolved)
        yield resolved

        initial = self._initial_state(source, brief, incident_id=incident_id)
        async for chunk in graph.astream(
            initial,
            stream_mode="updates",
            config={"recursion_limit": recursion_limit},
        ):
            for node_name, update in chunk.items():
                for event in self._events_from_update(node_name, update):
                    self._bus.publish(event)
                    yield event

    @staticmethod
    def _events_from_update(node_name: str, update: dict[str, Any]) -> list[DomainEvent]:
        """Translate one LangGraph node update into domain events"""
        events: list[DomainEvent] = []
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
            elif isinstance(event, PanelResolved):
                yield {
                    "type": "panel_resolved",
                    "data": [
                        {
                            "node_name": descriptor.node_name,
                            "display_name": descriptor.display_name,
                            "role": descriptor.role.value,
                        }
                        for descriptor in event.panel
                    ],
                }
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
            "continue_investigation requires Phase 6 storage backends. Implement after PostgresStore is available."
        )

    # ------------------------------------------------------------------
    # Panel resolution + graph construction (per run)
    # ------------------------------------------------------------------

    async def _extract_brief(self, source: IncidentSource) -> IncidentBrief:
        """Run the data adapter directly to produce the incident brief.

        This was formerly the graph's first node; hoisting it out means the
        resolved panel can be chosen *from* the brief (the AgenticManager needs
        the fault class/tags to pick specialists) before any graph is built.

        :param source: The incident source (crash dump, logs, etc.).
        :type source: IncidentSource
        :return: The structured forensic brief for this incident.
        :rtype: IncidentBrief
        """
        return await self._adapter.process(
            source,
            debug_backend=self._debug,
            code_backend=self._code,
            log_backend=self._log,
        )

    async def _resolve_and_build(
        self,
        brief: IncidentBrief,
    ) -> tuple[list[BaseAgent], Any, int]:
        """Resolve the panel for *brief* and compile a fresh graph for this run.

        Resolves panel specs (explicit config/CLI wins, else auto-selection),
        instantiates the live panel, derives the consensus weight map from each
        agent's own declared weight (with per-incident overrides), orders the
        panel (investigators by descending priority, arbiter last), and compiles
        a :class:`StateGraph` around it.

        :param brief: The incident brief driving auto-selection.
        :type brief: IncidentBrief
        :return: A tuple of (ordered panel, compiled graph, recursion limit).
        :rtype: tuple[list[BaseAgent], Any, int]
        """
        brief_dict = brief.model_dump(mode="json")
        specs = await self._panel_resolver.resolve(brief_dict, self._explicit_specs)
        panel = resolve_panel(specs, self._ai, self._settings)
        ordered = self._order_panel(panel)

        weight_map = resolve_consensus_weights(panel, specs)

        graph = self._build_graph(ordered, weight_map)
        # LangGraph counts every node visit toward its default 25-step recursion
        # limit; a large panel over many rounds can exceed it. Budget one step
        # per panel agent per round plus a margin for the terminal nodes.
        recursion_limit = (len(panel) + 2) * self._settings.core.max_debate_rounds + 5
        return ordered, graph, recursion_limit

    @staticmethod
    def _order_panel(panel: list[BaseAgent]) -> list[BaseAgent]:
        """Order *panel* for graph construction: investigators first, arbiter last.

        Investigators (any non-arbiter role) are ordered by descending
        :attr:`AgentSpec.priority`. Ties preserve the panel's incoming order
        (Python's sort is stable), which keeps the default four-agent panel in
        its historical ``os_kernel → code_analyst → log_historian`` sequence and
        so preserves the pre-refactor discussion order and per-turn data flow.
        The single arbiter (guaranteed by :func:`resolve_panel`) is always
        scheduled last regardless of its own priority.

        :param panel: The resolved, unordered panel.
        :type panel: list[BaseAgent]
        :return: Investigators in priority order followed by the arbiter.
        :rtype: list[BaseAgent]
        """
        investigators = sorted(
            (agent for agent in panel if agent.role is not AgentRole.ARBITER),
            key=lambda agent: -agent.spec.priority,
        )
        arbiter = next(agent for agent in panel if agent.role is AgentRole.ARBITER)
        return [*investigators, arbiter]

    @staticmethod
    def _node_name(agent: BaseAgent) -> str:
        """Return the graph node name for *agent* (``"<agent_key>_node"``)."""
        return f"{agent.agent_key}_node"

    def _build_graph(self, ordered_panel: list[BaseAgent], weight_map: dict[str, float]) -> Any:
        """Compile the LangGraph state machine for one resolved panel.

        Builds one node per panel agent via :meth:`_make_agent_node`, chains the
        investigators in the given order, edges the last investigator into the
        arbiter, and wires the arbiter's conditional routing (converge → output
        synthesis, exhaust rounds → HITL, else loop back to the first
        investigator).

        :param ordered_panel: Panel ordered by :meth:`_order_panel` (arbiter last).
        :type ordered_panel: list[BaseAgent]
        :param weight_map: Consensus weight map handed to the arbiter node.
        :type weight_map: dict[str, float]
        :return: A compiled LangGraph StateGraph ready for streaming/invocation.
        :rtype: Any
        """
        builder: StateGraph = StateGraph(InvestigationState)

        node_names = [self._node_name(agent) for agent in ordered_panel]
        first_node = node_names[0]

        for agent in ordered_panel:
            builder.add_node(self._node_name(agent), self._make_agent_node(agent, weight_map))
        builder.add_node("output_synthesizer_node", self._make_synthesizer_node(ordered_panel))
        builder.add_node("hitl_node", self._make_hitl_node(ordered_panel))

        builder.add_edge(START, first_node)
        # Chain every consecutive node (investigators then arbiter, which is last).
        for src, dst in zip(node_names, node_names[1:], strict=False):
            builder.add_edge(src, dst)
        # The arbiter (last node) gates convergence via conditional routing.
        builder.add_conditional_edges(node_names[-1], self._make_router(first_node))
        builder.add_edge("output_synthesizer_node", END)
        builder.add_edge("hitl_node", END)

        return builder.compile()

    # ------------------------------------------------------------------
    # Node implementations
    # ------------------------------------------------------------------

    async def _invoke_agent(self, agent: BaseAgent, state: InvestigationState) -> AgentTurn:
        """Run *agent*, threading the log-historian's extra data dependencies.

        Every agent's public contract is ``run(state)``; the Log Historian is the
        sole exception - it also needs the prior-report history and the vector
        store to correlate recurrences. This is a data-dependency difference (the
        one legitimate per-agent-type special case), not an identity check on any
        display name or reporting behaviour.

        :param agent: The panel agent to invoke.
        :type agent: BaseAgent
        :param state: The current investigation state.
        :type state: InvestigationState
        :return: The completed turn.
        :rtype: AgentTurn
        """
        if isinstance(agent, LogHistorianAgent):
            history = await self._load_history()
            return await agent.run(state, vector_store=self._vector, history=history)
        return await agent.run(state)

    def _make_agent_node(self, agent: BaseAgent, weight_map: dict[str, float]) -> AgentNode:
        """Build a LangGraph node closure for *agent*.

        The returned async closure invokes the agent, folds its turn into the
        shared state (history, per-agent score, token tracker), and then applies
        role-specific updates:

        - **Investigators** publish their turn as ``latest_turn_this_round`` (the
          next investigator in the chain reads it) and, when the turn carries
          hypotheses, promote the leading one to ``primary_hypothesis``.
        - The **arbiter** computes weighted consensus, evaluates convergence, and
          publishes its corrections as ``latest_arbiter_feedback`` (read by the
          first investigator of the next round).

        :param agent: The panel agent this node drives.
        :type agent: BaseAgent
        :param weight_map: Consensus weight map (only the arbiter node uses it).
        :type weight_map: dict[str, float]
        :return: An async node callable for :meth:`StateGraph.add_node`.
        :rtype: AgentNode
        """

        async def _node(state: InvestigationState) -> dict[str, Any]:
            turn = await self._invoke_agent(agent, state)
            tracker, history, scores = self._fold_turn(state, turn, agent.agent_key)
            update: dict[str, Any] = {
                "discussion_history": history,
                "current_round_scores": scores,
                "token_tracker": tracker,
            }
            if agent.role is AgentRole.ARBITER:
                update.update(self._arbiter_updates(state, turn, scores, weight_map))
            else:
                if turn.hypotheses:
                    update["primary_hypothesis"] = turn.hypotheses[0].model_dump(mode="json")
                update["latest_turn_this_round"] = turn.model_dump(mode="json")
            return update

        return _node

    def _arbiter_updates(
        self,
        state: InvestigationState,
        turn: AgentTurn,
        scores: dict[str, float],
        weight_map: dict[str, float],
    ) -> dict[str, Any]:
        """Compute the arbiter node's convergence/consensus state updates.

        Mirrors the legacy Skeptic behaviour generically: the arbiter's turn
        confirms when its confidence is MEDIUM or above; convergence additionally
        requires the weighted consensus to meet the threshold on a stable
        primary hypothesis. The round counter is advanced and the arbiter's
        corrections carried forward for the next round's first investigator.

        :param state: The current investigation state (pre-update).
        :type state: InvestigationState
        :param turn: The arbiter's just-completed turn.
        :type turn: AgentTurn
        :param scores: The current round's per-agent confidence scores.
        :type scores: dict[str, float]
        :param weight_map: The resolved consensus weight map for this run.
        :type weight_map: dict[str, float]
        :return: The arbiter-specific slice of the node's state update.
        :rtype: dict[str, Any]
        """
        cs = self._evaluator.calculate(scores, weight_map)

        # Convergence: arbiter confirmed (MEDIUM+) AND score meets threshold on a
        # stable hypothesis.
        arbiter_confirmed = turn.confidence_score >= 0.65
        prev_key = state.get("previous_hypothesis_key")
        primary = state.get("primary_hypothesis") or {}
        current_key = str(primary.get("root_cause") or "")
        same_hypothesis = prev_key is None or prev_key == current_key
        converged = arbiter_confirmed and self._evaluator.is_converged(
            cs, self._settings.core.consensus_threshold, same_hypothesis
        )

        round_num = state.get("round_number", 1)
        return {
            "consensus_score": cs,
            "is_converged": converged,
            "round_number": round_num + 1,
            "previous_hypothesis_key": current_key,
            "latest_arbiter_feedback": list(turn.corrections),
        }

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

    def _make_synthesizer_node(self, panel: list[BaseAgent]) -> AgentNode:
        """Build the output-synthesizer node closure for *panel*.

        The node builds the final RCA report when consensus is reached and
        persists it to relational and vector stores (best-effort; failures are
        logged but never fatal). The panel is closed over so :meth:`_build_report`
        can key report synthesis off each turn's role/capability rather than any
        display-name string.

        :param panel: The resolved panel for this run.
        :type panel: list[BaseAgent]
        :return: An async node callable for :meth:`StateGraph.add_node`.
        :rtype: AgentNode
        """

        async def _node(state: InvestigationState) -> dict[str, Any]:
            report = self._build_report(state, panel, hitl_pending=False)
            # Incident-analyst safety rule: never auto-remediate without
            # AEGIS_PROD_CONFIRMED=1. This node only ATTACHES an advisory plan to
            # the report - it never dispatches any step to an execution engine.
            report = await self._synthesize_remediation(report)
            if self._relational:
                try:
                    await self._relational.save_report(report)
                except NotImplementedError:
                    logger.warning("RelationalStore is a stub; report was not persisted.")
                except RelationalStoreError as exc:  # pragma: no cover
                    logger.warning(f"Could not save report to relational store: {exc}")
            if self._vector:
                try:
                    await self._vector.upsert_incident(report)
                except VectorStoreError as exc:  # pragma: no cover
                    logger.warning(f"Could not upsert report to vector store: {exc}")
            return {"result": json.loads(report.model_dump_json()), "hitl_pending": False}

        return _node

    async def _synthesize_remediation(self, report: RCAReport) -> RCAReport:
        """Attach a :class:`RemediationPlan` to *report* when synthesis is enabled.

        Runs the synthesis-tier :class:`RemediationPlannerAgent` once on a
        confirmed report. Soft-failure boundary: project-level planner/AI
        exceptions are logged (without payload) and the original report is
        returned with ``remediation_plan`` left ``None`` - a synthesis error
        must never block delivery of the confirmed RCA. Only invoked from the
        convergence path; the HITL path never calls this method.

        :param report: The confirmed RCA report.
        :type report: RCAReport
        :return: The report, with ``remediation_plan`` attached on success.
        :rtype: RCAReport
        """
        if "remediation_planner" not in self._settings.panel.enabled_synthesis:
            return report

        planner = RemediationPlannerAgent(self._ai, self._settings)
        try:
            turn, plan = await planner.run_synthesis(report)
        except AegisSWRError as exc:  # soft failure: never block RCA delivery
            logger.warning(
                "Remediation synthesis failed for incident {}: {}",
                report.incident_id,
                type(exc).__name__,
            )
            return report

        if plan.requires_human_approval:
            logger.warning("Remediation plan requires human approval for incident {}", report.incident_id)
        self._bus.publish(AgentSpoke(node="remediation_planner_node", turn=turn))
        return report.model_copy(update={"remediation_plan": plan})

    def _make_hitl_node(self, panel: list[BaseAgent]) -> AgentNode:
        """Build the HITL node closure for *panel*.

        When the panel cannot converge within the configured debate limit, the
        node packages the current state into an RCAReport carrying a
        :class:`~aegis_swr.core.schemas.HITLRequest` and persists it to relational
        storage for later resumption. The panel is closed over for role-driven
        report synthesis.

        :param panel: The resolved panel for this run.
        :type panel: list[BaseAgent]
        :return: An async node callable for :meth:`StateGraph.add_node`.
        :rtype: AgentNode
        """

        async def _node(state: InvestigationState) -> dict[str, Any]:
            return await self._hitl_node(state, panel)

        return _node

    async def _hitl_node(self, state: InvestigationState, panel: list[BaseAgent]) -> dict[str, Any]:
        """Build and persist a Human-In-The-Loop report at the debate limit.

        :param state: Investigation state after max rounds reached.
        :type state: InvestigationState
        :param panel: The resolved panel, for role-driven report synthesis.
        :type panel: list[BaseAgent]
        :return: Update dict with ``result`` (the RCAReport) and ``hitl_pending``.
        :rtype: dict[str, Any]
        """
        report = self._build_report(state, panel, hitl_pending=True)
        if self._relational:
            try:
                await self._relational.save_report(report)
            except NotImplementedError:
                logger.warning("RelationalStore is a stub; HITL report was not persisted.")
            except RelationalStoreError as exc:  # pragma: no cover
                logger.warning(f"Could not save HITL report: {exc}")
        return {"result": json.loads(report.model_dump_json()), "hitl_pending": True}

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def _make_router(self, first_node: str) -> Callable[[InvestigationState], str]:
        """Build the arbiter's conditional-routing function for this run.

        The routing logic (unchanged from the legacy Skeptic gate, generalized):

        - If converged (consensus ≥ threshold and arbiter MEDIUM+ confidence on a
          stable hypothesis): route to output synthesis.
        - Else if the debate limit is reached: route to HITL for user input.
        - Else: loop back to the first investigator for the next round.

        :param first_node: Node name of the first investigator (the loop-back
            target), bound at graph-build time from the ordered panel.
        :type first_node: str
        :return: A routing callable for :meth:`StateGraph.add_conditional_edges`.
        :rtype: Callable[[InvestigationState], str]
        """

        def _route(state: InvestigationState) -> str:
            if state.get("is_converged"):
                return "output_synthesizer_node"
            # round_number has already been incremented by the arbiter node.
            rounds_completed = (state.get("round_number") or 2) - 1
            if rounds_completed >= self._settings.core.max_debate_rounds:
                return "hitl_node"
            return first_node

        return _route

    # ------------------------------------------------------------------
    # Report construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_report(
        state: InvestigationState,
        panel: list[BaseAgent],
        *,
        hitl_pending: bool,
    ) -> RCAReport:
        """Synthesize investigation state into a complete RCA report.

        Extracts the primary hypothesis, alternative hypotheses, the
        fix-contributor's probabilistic fix (annotated with the ``__fix__:``
        prefix), the arbiter's challenges, and consensus metrics. Which turns
        supply challenges vs. fixes is decided by the *panel* each agent's role
        (``ARBITER``) and capability flag (``contributes_fix``), keyed by
        ``agent_key`` - never by any display-name string. Builds an HITLRequest
        when the investigation is inconclusive and awaiting user input.

        :param state: Final investigation state with all agent dialogue/scores.
        :type state: InvestigationState
        :param panel: The resolved panel, supplying the role/capability lookups.
        :type panel: list[BaseAgent]
        :param hitl_pending: When ``True`` include a HITLRequest and set the
            report's flag; otherwise produce a completed report.
        :type hitl_pending: bool
        :return: RCAReport with all synthesized findings, evidence, and metadata.
        :rtype: RCAReport
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

        # Panel-derived, role/capability-driven synthesis (no name-string branch).
        agent_roles = {agent.agent_key: agent.role for agent in panel}
        agent_fix_flags = {agent.agent_key: agent.contributes_fix for agent in panel}

        # Extract all alternative hypotheses from the agent turns.
        alt_hypotheses: list[Hypothesis] = []
        skeptic_challenges: list[str] = []
        mitigation: list[str] = []
        probabilistic_fix: Optional[str] = None
        for turn in history:
            if agent_roles.get(turn.agent_key) is AgentRole.ARBITER:
                for h in turn.hypotheses:
                    skeptic_challenges.extend(h.evidence)
            if agent_fix_flags.get(turn.agent_key):
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
            self._history_cache = await self._relational.load_recent(limit=self._HISTORY_LIMIT)
        except NotImplementedError:
            logger.warning("RelationalStore is a stub; no incident history available.")
            self._history_cache = []
        except RelationalStoreError as exc:
            logger.warning("Failed to load incident history: {}", exc)
            self._history_cache = []
        return self._history_cache

    @staticmethod
    def _initial_state(
        source: IncidentSource,
        brief: IncidentBrief,
        incident_id: Optional[str] = None,
    ) -> InvestigationState:
        """Construct the initial state for a new investigation.

        Seeds the state with the already-extracted incident brief (formerly
        produced by the data-adapter node), empty discussion history, zero
        consensus, and the new panel-coordination fields (``latest_turn_this_round``
        starts unset and ``latest_arbiter_feedback`` empty). The incident source
        is serialized as JSON for transparent state passing.

        :param source: Incident source (crash dump, log file reference, etc.).
        :type source: IncidentSource
        :param brief: The forensic brief extracted before graph execution.
        :type brief: IncidentBrief
        :param incident_id: Optional pre-generated incident ID; a UUID4 is
            generated when omitted. (Streaming supplies the id used by the
            InvestigationStarted event so both agree.)
        :type incident_id: Optional[str]
        :return: InvestigationState ready for graph execution.
        :rtype: InvestigationState
        """
        return InvestigationState(
            incident_id=incident_id or str(uuid.uuid4()),
            incident_brief=brief.model_dump(mode="json"),
            source=json.loads(source.model_dump_json()),
            discussion_history=[],
            latest_turn_this_round=None,
            latest_arbiter_feedback=[],
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
