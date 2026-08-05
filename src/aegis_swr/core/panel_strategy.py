"""Panel-selection strategies (Factory-Strategy convention).

Team formation happens *before* the orchestrator builds anything: a strategy
inspects the incident brief (or a user-supplied explicit selection) and produces
the list of :class:`~aegis_swr.agents.base.AgentSpec` objects that
``agents/panel.py`` then instantiates and validates.

Two concrete strategies ship today:

- :class:`ExplicitPanelStrategy` - returns specs supplied ahead of time via
  config/CLI, ignoring the brief.
- :class:`AgenticManagerStrategy` - a heuristic that proposes the full roster of
  registered agents as the candidate pool. It is deliberately fronted by the
  abstract :class:`PanelSelectionStrategy` interface so an LLM-backed manager can
  replace the heuristic later without any change to the orchestrator or this
  module's callers.

:class:`PanelResolver` is the top-level entry point later phases call: hand it
the brief plus whatever explicit specs came from config/CLI (or ``None``) and it
picks the right strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from loguru import logger

from aegis_swr.agents.base import AgentSpec
from aegis_swr.agents.registry import AGENT_REGISTRY
from aegis_swr.config.settings import Settings
from aegis_swr.core.fault_codes import FaultClass


class PanelSelectionStrategy(ABC):
    """Abstract strategy that selects the agent specs for one incident.

    Implementations decide *which* agents should form the panel; instantiation
    and structural validation of the chosen specs is the separate concern of
    :func:`aegis_swr.agents.panel.resolve_panel`.
    """

    @abstractmethod
    async def select(self, incident_brief: dict[str, Any]) -> list[AgentSpec]:
        """Return the agent specs that should form the panel for this incident.

        :param incident_brief: The serialized incident brief (the same
            ``dict[str, Any]`` shape carried in
            :data:`~aegis_swr.core.schemas.InvestigationState` under
            ``incident_brief``).
        :type incident_brief: dict[str, Any]
        :return: The selected specs, in the order the strategy prefers.
        :rtype: list[AgentSpec]
        """
        raise NotImplementedError


class ExplicitPanelStrategy(PanelSelectionStrategy):
    """Return a fixed, pre-computed list of specs, ignoring the brief.

    Used when the user has selected the panel explicitly (via config or the
    ``--agent`` CLI flag); the incident brief plays no part in the decision.

    :ivar _specs: The specs to return verbatim from :meth:`select`.
    """

    def __init__(self, specs: list[AgentSpec]) -> None:
        """Store the explicit specs to be returned unchanged.

        :param specs: The specs supplied ahead of time via config/CLI.
        :type specs: list[AgentSpec]
        """
        self._specs = specs

    async def select(self, incident_brief: dict[str, Any]) -> list[AgentSpec]:
        """Return the stored specs unchanged.

        :param incident_brief: Ignored - the selection is fixed.
        :type incident_brief: dict[str, Any]
        :return: The specs supplied at construction, in order.
        :rtype: list[AgentSpec]
        """
        return list(self._specs)


class AgenticManagerStrategy(PanelSelectionStrategy):
    """Fault-aware auto-selection of a panel from the registered agent roster.

    Proposes one default-priority :class:`AgentSpec` per *eligible* registered
    agent, in registry order. Eligibility depends on the agent's category and
    the incident's fault class:

    - **Generalist (``base``) agents** - always proposed, so the default panel
      is byte-identical to Milestone 0001 for any incident (this is what keeps
      the back-compat gate: with only base agents registered, or on an incident
      whose fault class matches no specialist, exactly the four base agents are
      returned).
    - **Forensic specialists** - proposed only when the incident's
      :class:`~aegis_swr.core.fault_codes.FaultClass` is in the agent's
      :attr:`~aegis_swr.agents.base.BaseAgent.authoritative_fault_classes`, so a
      specialist joins the debate only for incidents in its domain.
    - **Synthesis-tier agents** - never proposed here; they run once after the
      debate converges, not as weighted debate voters.

    The registry is the single source of truth for which agents exist, so adding
    a specialist to the registry (with its authoritative fault classes declared)
    automatically makes it a fault-gated candidate here - no separate ops-curated
    panel file to keep in sync.

    This heuristic intentionally implements the same
    :class:`PanelSelectionStrategy` interface an LLM-backed manager would, so a
    smarter selector can be swapped in later with no change to callers.

    :ivar _settings: Application settings, retained for a future LLM-backed
        manager.
    :ivar _registry: The agent registry supplying the candidate roster.
    """

    def __init__(
        self,
        settings: Settings,
        registry: Optional[dict[str, Any]] = None,
    ) -> None:
        """Construct the manager over the agent registry.

        :param settings: Application settings; retained for a future
            brief-aware/LLM-backed selection policy.
        :type settings: Settings
        :param registry: Agent registry supplying the candidate roster. Defaults
            to :data:`~aegis_swr.agents.registry.AGENT_REGISTRY`.
        :type registry: Optional[dict[str, Any]]
        """
        self._settings = settings
        self._registry = registry if registry is not None else AGENT_REGISTRY

    async def select(self, incident_brief: dict[str, Any]) -> list[AgentSpec]:
        """Select one default-priority spec per *eligible* registered agent.

        Base agents are always selected; forensic specialists are selected only
        when the brief's fault class is one they are authoritative for; synthesis
        agents are never selected. Selection preserves registry order.

        :param incident_brief: The serialized incident brief; its
            ``"fault_class"`` field gates forensic-specialist inclusion.
        :type incident_brief: dict[str, Any]
        :return: One default-priority spec per eligible agent, in registry order.
        :rtype: list[AgentSpec]
        """
        fault = self._fault_class_of(incident_brief)
        return [AgentSpec(agent_key=key) for key, cls in self._registry.items() if self._is_candidate(cls, fault)]

    @staticmethod
    def _fault_class_of(incident_brief: dict[str, Any]) -> Optional[FaultClass]:
        """Extract the brief's :class:`FaultClass`, tolerating strings and ``None``.

        :param incident_brief: The serialized incident brief.
        :type incident_brief: dict[str, Any]
        :return: The parsed fault class, or ``None`` when absent/unrecognized.
        :rtype: Optional[FaultClass]
        """
        raw = incident_brief.get("fault_class")
        if raw is None:
            return None
        if isinstance(raw, FaultClass):
            return raw
        try:
            return FaultClass(str(raw))
        except ValueError:
            logger.debug("PanelStrategy: unrecognised fault_class value {!r}; treating as None", raw)
            return None

    @staticmethod
    def _is_candidate(agent_cls: Any, fault: Optional[FaultClass]) -> bool:
        """Return whether *agent_cls* should join the auto-selected panel.

        Non-forensic agents (base generalists, and any registry test-double
        lacking a ``category``) are always candidates; a synthesis agent is never
        a debate candidate; a forensic specialist is a candidate only when
        *fault* is one of its authoritative fault classes.

        :param agent_cls: The registered agent class (or test-double) to judge.
        :type agent_cls: Any
        :param fault: The incident's fault class, or ``None``.
        :type fault: Optional[FaultClass]
        :return: ``True`` when the agent should be proposed for the panel.
        :rtype: bool
        """
        category = getattr(agent_cls, "category", "base")
        if category == "synthesis":
            return False
        if category == "forensic":
            authoritative = getattr(agent_cls, "authoritative_fault_classes", frozenset())
            return fault is not None and fault in authoritative
        return True


class PanelResolver:
    """Top-level entry point choosing between explicit and auto selection.

    Explicit config wins when present; otherwise the
    :class:`AgenticManagerStrategy` runs against the incident brief. This is the
    single call site later phases use to obtain the panel specs, regardless of
    where the selection came from.

    :ivar _auto_strategy: The strategy used when no explicit specs are supplied.
    """

    def __init__(
        self,
        settings: Settings,
        registry: Optional[dict[str, Any]] = None,
    ) -> None:
        """Construct the resolver over the auto-selection strategy.

        :param settings: Application settings, forwarded to
            :class:`AgenticManagerStrategy`.
        :type settings: Settings
        :param registry: Optional agent registry override, forwarded to
            :class:`AgenticManagerStrategy`.
        :type registry: Optional[dict[str, Any]]
        """
        self._auto_strategy = AgenticManagerStrategy(settings, registry=registry)

    async def resolve(
        self,
        incident_brief: dict[str, Any],
        explicit_specs: Optional[list[AgentSpec]] = None,
    ) -> list[AgentSpec]:
        """Resolve the panel specs for this incident.

        When *explicit_specs* is non-empty the explicit selection is honored and
        the brief is ignored; otherwise the auto-selection manager runs. A
        ``None`` or empty *explicit_specs* both route to auto selection, so a
        caller can simply pass "whatever explicit specs came from config/CLI, or
        ``None``".

        :param incident_brief: The serialized incident brief.
        :type incident_brief: dict[str, Any]
        :param explicit_specs: Explicit specs from config/CLI, or ``None``.
        :type explicit_specs: Optional[list[AgentSpec]]
        :return: The resolved panel specs.
        :rtype: list[AgentSpec]
        """
        if explicit_specs:
            return await ExplicitPanelStrategy(explicit_specs).select(incident_brief)
        return await self._auto_strategy.select(incident_brief)
