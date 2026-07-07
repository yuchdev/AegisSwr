"""Agent registry and single-agent factory.

Maps each concrete agent's canonical :attr:`~aegis_swr.agents.base.BaseAgent.agent_key`
to its class and provides :func:`create_agent`, the one place that turns a
per-incident :class:`~aegis_swr.agents.base.AgentSpec` into a live
:class:`~aegis_swr.agents.base.BaseAgent`. Panel-level resolution (enabling,
arbiter enforcement, unknown-key tolerance) lives in ``agents/panel.py`` and is
built on top of this module.
"""

from __future__ import annotations

from aegis_swr.agents.base import AgentSpec, BaseAgent
from aegis_swr.agents.code_analyst import CodeAnalystAgent
from aegis_swr.agents.log_historian import LogHistorianAgent
from aegis_swr.agents.os_kernel import OSKernelAgent
from aegis_swr.agents.skeptic import SkepticAgent
from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import Settings
from aegis_swr.core.exceptions import AegisSWRError


class UnknownAgentError(AegisSWRError):
    """Raised when an :class:`AgentSpec` names an unregistered ``agent_key``.

    Subclasses the project-wide :class:`~aegis_swr.core.exceptions.AegisSWRError`
    base so it participates in the standard exception hierarchy. Panel resolution
    (:func:`aegis_swr.agents.panel.resolve_panel`) catches this specific type to
    warn-and-skip a stray key (e.g. a CLI typo) rather than aborting the run.
    """


#: Canonical registry mapping each concrete agent's ``agent_key`` to its class.
#: This is the single source of truth for which agents can be instantiated; a
#: panel-selection strategy proposes keys and :func:`create_agent` looks them up
#: here. New agents register by adding an entry.
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    OSKernelAgent.agent_key: OSKernelAgent,
    CodeAnalystAgent.agent_key: CodeAnalystAgent,
    LogHistorianAgent.agent_key: LogHistorianAgent,
    SkepticAgent.agent_key: SkepticAgent,
}


def create_agent(
    spec: AgentSpec,
    ai_backend: AIAPIBackend,
    settings: Settings,
) -> BaseAgent:
    """Instantiate the concrete agent named by *spec*.

    Looks up ``spec.agent_key`` in :data:`AGENT_REGISTRY` and constructs the
    matching class with the shared backend, settings, and this per-incident spec.

    :param spec: Per-incident configuration naming the agent to build and
        carrying its priority/weight/enabled state.
    :type spec: AgentSpec
    :param ai_backend: Shared LLM backend passed to the agent's constructor.
    :type ai_backend: AIAPIBackend
    :param settings: Application settings passed to the agent's constructor.
    :type settings: Settings
    :return: A freshly instantiated agent for this spec.
    :rtype: BaseAgent
    :raises UnknownAgentError: If ``spec.agent_key`` is not in
        :data:`AGENT_REGISTRY`.
    """
    cls = AGENT_REGISTRY.get(spec.agent_key)
    if cls is None:
        raise UnknownAgentError(
            f"No agent registered under key {spec.agent_key!r}; known keys: {sorted(AGENT_REGISTRY)}"
        )
    return cls(ai_backend, settings, spec)
