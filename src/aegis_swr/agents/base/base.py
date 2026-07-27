from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Literal, Optional

from pydantic import BaseModel, Field

from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import AgentRole, AgentTurn, Hypothesis, InvestigationState

# Broad taxonomy bucket an agent belongs to. Declared as a module-level alias
# (rather than an inline ``Literal[...]`` annotation) so ``UP037`` does not strip
# the quotes off the string members under ``from __future__ import annotations``.
AgentCategory = Literal["base", "forensic", "synthesis"]


class AgentSpec(BaseModel):
    """
    Per-incident configuration for a single agent in a resolved panel.

    An :class:`AgentSpec` captures what varies *per invocation* about an agent -
    as opposed to the class-level :class:`ClassVar` descriptors on
    :class:`BaseAgent`, which describe what the agent inherently *is*. A
    panel-selection strategy produces these specs and the registry consumes them
    to instantiate the concrete agents for a run.

    :ivar agent_key: Canonical identifier of the agent this spec configures
        (matches :attr:`BaseAgent.agent_key`).
    :type agent_key: str
    :ivar priority: Relative ordering of the agent within the panel, constrained
        to the inclusive range 1-5 (higher speaks earlier). Defaults to ``3``.
        Priority controls *debate/speaking order only*; it no longer contributes
        to consensus weight.
    :type priority: int
    :ivar weight: Explicit consensus-weight override for this incident. When
        ``None`` the agent's own intrinsic :attr:`BaseAgent.default_weight`
        class property is used instead.
    :type weight: Optional[float]
    :ivar enabled: Whether this agent participates in the resolved panel.
    :type enabled: bool
    """

    agent_key: str
    priority: int = Field(ge=1, le=5, default=3)
    weight: Optional[float] = None
    enabled: bool = True


class BaseAgent(ABC):
    """
    Abstract base for all Synthetic War Room agents.

    Concrete subclasses declare their identity and behavioural role via the
    class-level :class:`ClassVar` descriptors below so the orchestrator can drive
    a dynamically resolved panel purely off generic, self-declared facts (role,
    category, capability, consensus weight) rather than any hardcoded display
    name or external policy file.

    :cvar agent_key: Canonical, stable identifier of the agent (e.g.
        ``"skeptic"``). Used for all role/capability lookups.
    :cvar display_name: Human-facing label shown in views and serialized into the
        RCA report's ``agent_dialogue``.
    :cvar category: Broad taxonomy bucket the agent belongs to.
    :cvar role: Behavioural role the agent plays in the debate.
    :cvar contributes_fix: Whether the agent produces a probabilistic fix
        mid-debate (orthogonal to :attr:`role`).
    :cvar default_weight: Intrinsic consensus weight - how much this agent's
        confidence counts when the :class:`~aegis_swr.core.consensus.ConsensusEvaluator`
        blends the panel's per-round scores. This is a property of the agent
        itself (not an external per-fault-class matrix); every concrete agent
        must declare it, and a missing declaration fails loudly at panel
        resolution rather than being silently defaulted. A per-incident
        :attr:`AgentSpec.weight` override takes precedence when set. The
        evaluator normalizes by the summed weights of the live panel, so the
        declared values need not sum to any particular total.
    :cvar authoritative_fault_classes: The set of
        :class:`~aegis_swr.core.fault_codes.FaultClass` values for which this
        agent is a decisive voter and should be auto-selected into the debate
        panel. Generalist (``base``-category) agents leave this empty and are
        always selected regardless of the fault; forensic specialists declare
        the fault classes they are authoritative for so
        :class:`~aegis_swr.core.panel_strategy.AgenticManagerStrategy` only adds
        them to incidents in their domain. An empty set therefore means "no
        fault-based auto-selection" - relied upon by base agents (always in) and
        honored for forensic agents (never auto-added on their own).
    """

    agent_key: ClassVar[str]
    display_name: ClassVar[str]
    category: ClassVar[AgentCategory]
    role: ClassVar[AgentRole]
    contributes_fix: ClassVar[bool] = False
    default_weight: ClassVar[float]
    authoritative_fault_classes: ClassVar[frozenset[FaultClass]] = frozenset()

    def __init__(
        self,
        ai_backend: AIAPIBackend,
        settings: Settings,
        spec: Optional[AgentSpec] = None,
    ):
        self._ai = ai_backend
        self._settings = settings
        # Exposed publicly (not ``self._spec``): later phases - panel/consensus
        # wiring and priority-ordered graph construction - read
        # ``.spec.priority``/``.spec.weight`` externally. When no spec is supplied
        # (the pre-panel-migration call path) a default is derived from the class's
        # own ``agent_key`` so ``self.spec`` is always a concrete AgentSpec.
        self.spec: AgentSpec = spec if spec is not None else AgentSpec(agent_key=self.agent_key)

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The stable system-level persona instruction for this agent"""
        pass

    @abstractmethod
    async def run(self, state: InvestigationState) -> AgentTurn:
        """Execute this agent's analysis pass and return a completed AgentTurn"""
        pass

    def make_turn(
        self,
        *,
        turn_number: int,
        message: str,
        confidence_score: float,
        hypotheses: Optional[list[Hypothesis]] = None,
        corrections: Optional[list[str]] = None,
    ) -> AgentTurn:
        """
        Construct an :class:`AgentTurn` stamped with this agent's identity.

        Auto-stamps both ``agent`` (the human :attr:`display_name`) and
        ``agent_key`` (the canonical :attr:`agent_key`) so a subclass can never
        hardcode a mismatched identity string into a turn.

        :param turn_number: Sequential number of the turn within the debate.
        :type turn_number: int
        :param message: Human-readable summary the agent conveys for this turn.
        :type message: str
        :param confidence_score: Confidence associated with this turn's output.
        :type confidence_score: float
        :param hypotheses: Hypotheses generated during the turn, if any.
        :type hypotheses: Optional[list[Hypothesis]]
        :param corrections: Corrections raised during the turn, if any.
        :type corrections: Optional[list[str]]
        :return: A completed turn carrying this agent's ``agent``/``agent_key``.
        :rtype: AgentTurn
        """
        return AgentTurn(
            agent=self.display_name,
            agent_key=self.agent_key,
            turn_number=turn_number,
            message=message,
            hypotheses=hypotheses or [],
            confidence_score=confidence_score,
            corrections=corrections or [],
        )

    @staticmethod
    def _append_turn(
        state: InvestigationState,
        turn: AgentTurn,
    ):
        """Append a completed turn to the state's discussion history"""
        history: list[dict[str, Any]] = state.get("discussion_history", [])
        history.append(turn.model_dump(mode="json"))
        state["discussion_history"] = history

    def _accumulate_tokens(self, state: InvestigationState):
        """Add this backend call's token usage to state["token_tracker"]"""
        usage = getattr(self._ai, "last_usage", None)
        if usage is None:
            return
        tracker: dict[str, int] = dict(state.get("token_tracker") or {})
        tracker["input_tokens"] = tracker.get("input_tokens", 0) + usage.get("input_tokens", 0)
        tracker["output_tokens"] = tracker.get("output_tokens", 0) + usage.get("output_tokens", 0)
        state["token_tracker"] = tracker
