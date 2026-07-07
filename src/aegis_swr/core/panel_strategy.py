"""Panel-selection strategies (Factory-Strategy convention).

Team formation happens *before* the orchestrator builds anything: a strategy
inspects the incident brief (or a user-supplied explicit selection) and produces
the list of :class:`~aegis_swr.agents.base.AgentSpec` objects that
``agents/panel.py`` then instantiates and validates.

Two concrete strategies ship today:

- :class:`ExplicitPanelStrategy` - returns specs supplied ahead of time via
  config/CLI, ignoring the brief.
- :class:`AgenticManagerStrategy` - a heuristic that maps the brief's fault
  class to a curated candidate pool. It is deliberately fronted by the abstract
  :class:`PanelSelectionStrategy` interface so an LLM-backed manager can replace
  the heuristic later without any change to the orchestrator or this module's
  callers.

:class:`PanelResolver` is the top-level entry point later phases call: hand it
the brief plus whatever explicit specs came from config/CLI (or ``None``) and it
picks the right strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

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
    """Heuristic auto-selection of a panel from the incident's fault class.

    Reads the ops-curated candidate pool from :class:`AgentPanelSettings`: a
    per-fault-class override list when one exists for the brief's fault class,
    otherwise the default panel. Candidate keys are filtered to those present in
    the agent registry (an unknown key in ops policy contributes nothing here),
    and each surviving key becomes an :class:`AgentSpec` with the default
    priority.

    This heuristic intentionally implements the same
    :class:`PanelSelectionStrategy` interface an LLM-backed manager would, so a
    smarter selector can be swapped in later with no change to callers.

    :ivar _settings: Application settings, read for the curated panel policy.
    :ivar _registry: The agent registry used to validate candidate keys.
    """

    def __init__(
        self,
        settings: Settings,
        registry: Optional[dict[str, Any]] = None,
    ) -> None:
        """Construct the manager over the curated policy and agent registry.

        :param settings: Application settings; ``settings.agent_panel`` supplies
            the default and per-fault-class candidate pools.
        :type settings: Settings
        :param registry: Agent registry used to filter candidate keys to
            registered agents. Defaults to
            :data:`~aegis_swr.agents.registry.AGENT_REGISTRY`.
        :type registry: Optional[dict[str, Any]]
        """
        self._settings = settings
        self._registry = registry if registry is not None else AGENT_REGISTRY

    async def select(self, incident_brief: dict[str, Any]) -> list[AgentSpec]:
        """Select candidate specs from the brief's fault class.

        :param incident_brief: The serialized incident brief; its
            ``fault_class`` value drives the candidate-pool lookup.
        :type incident_brief: dict[str, Any]
        :return: One default-priority spec per registered candidate key.
        :rtype: list[AgentSpec]
        """
        fault_class = self._fault_class(incident_brief)
        panel_settings = self._settings.agent_panel
        candidates = panel_settings.per_fault_class.get(fault_class.value, panel_settings.default_panel)
        return [AgentSpec(agent_key=key) for key in candidates if key in self._registry]

    @staticmethod
    def _fault_class(incident_brief: dict[str, Any]) -> FaultClass:
        """Extract the brief's fault class, defaulting to ``UNKNOWN``.

        Mirrors the orchestrator's existing extraction: read ``fault_class``
        from the brief, coerce it to a :class:`FaultClass`, and fall back to
        :attr:`FaultClass.UNKNOWN` on an unrecognized value.
        """
        fault_str = incident_brief.get("fault_class") or "unknown"
        try:
            return FaultClass(fault_str)
        except ValueError:
            return FaultClass.UNKNOWN


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
