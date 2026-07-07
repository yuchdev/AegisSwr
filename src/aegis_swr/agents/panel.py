"""Panel resolution and consensus-weight resolution.

Turns a list of per-incident :class:`~aegis_swr.agents.base.AgentSpec` objects
into a live panel of :class:`~aegis_swr.agents.base.BaseAgent` instances and
derives the consensus weight map the orchestrator hands to
:meth:`~aegis_swr.core.consensus.ConsensusEvaluator.calculate`.

Two correctness policies live here:

- **Unknown-key tolerance** - an :class:`AgentSpec` naming an unregistered key
  (e.g. a CLI typo) is warned about and skipped, never fatal.
- **Exactly-one-arbiter enforcement** - a resolved panel must contain exactly
  one :class:`~aegis_swr.core.schemas.AgentRole.ARBITER`; zero (no convergence
  gate) or two-plus (ambiguous gate) is a hard :class:`PanelResolutionError`,
  not a warn-and-skip.
"""

from __future__ import annotations

from loguru import logger

from aegis_swr.agents.base import AgentSpec, BaseAgent
from aegis_swr.agents.registry import UnknownAgentError, create_agent
from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import Settings
from aegis_swr.core.exceptions import AegisSWRError
from aegis_swr.core.schemas import AgentRole


class PanelResolutionError(AegisSWRError):
    """Raised when a resolved panel violates a hard structural invariant.

    Currently this means the arbiter count is not exactly one. Unlike the
    unknown-key tolerance (a warn-and-skip), an incorrect convergence gate is a
    correctness regression and must never proceed silently.
    """


def resolve_panel(
    specs: list[AgentSpec],
    ai_backend: AIAPIBackend,
    settings: Settings,
) -> list[BaseAgent]:
    """Instantiate the enabled specs into a validated panel of agents.

    Disabled specs are dropped. Each remaining spec is instantiated via
    :func:`aegis_swr.agents.registry.create_agent`; a spec naming an
    unregistered ``agent_key`` is warned about and skipped rather than aborting
    the run. The resulting panel is then validated to contain exactly one
    :class:`~aegis_swr.core.schemas.AgentRole.ARBITER`.

    Ordering of the returned list mirrors the input spec order; priority-based
    graph ordering is a later concern and not applied here.

    :param specs: Per-incident agent specs proposed by a selection strategy.
    :type specs: list[AgentSpec]
    :param ai_backend: Shared LLM backend passed to every agent's constructor.
    :type ai_backend: AIAPIBackend
    :param settings: Application settings passed to every agent's constructor.
    :type settings: Settings
    :return: The instantiated, structurally valid panel.
    :rtype: list[BaseAgent]
    :raises PanelResolutionError: If the panel does not contain exactly one
        arbiter.
    """
    panel: list[BaseAgent] = []
    for spec in specs:
        if not spec.enabled:
            continue
        try:
            panel.append(create_agent(spec, ai_backend, settings))
        except UnknownAgentError:
            logger.warning(
                "Skipping unknown agent key {!r} in resolved panel; not present in the agent registry.",
                spec.agent_key,
            )

    arbiters = [agent for agent in panel if agent.role is AgentRole.ARBITER]
    if len(arbiters) != 1:
        raise PanelResolutionError(
            f"A resolved panel must contain exactly one ARBITER agent; "
            f"found {len(arbiters)} "
            f"({[agent.agent_key for agent in arbiters]}). Zero arbiters leaves "
            f"no convergence gate; two or more makes the gate ambiguous."
        )
    return panel


def resolve_consensus_weights(
    panel: list[BaseAgent],
    specs: list[AgentSpec],
) -> dict[str, float]:
    """Resolve the per-agent consensus weight map for *panel*.

    Weight is an intrinsic property of each agent (its
    :attr:`~aegis_swr.agents.base.BaseAgent.default_weight` class attribute), not
    an external per-fault-class matrix. Resolution applies a two-tier precedence
    (highest wins) per agent:

    1. **Explicit override** - ``AgentSpec.weight`` when set (non-``None``).
    2. **Agent's own declared weight** - ``agent.default_weight`` otherwise.

    No whole-map renormalization is performed:
    :meth:`~aegis_swr.core.consensus.ConsensusEvaluator.calculate` divides by the
    sum of the map it receives, so the returned values self-normalize over
    whatever panel is live.

    :param panel: The instantiated agents whose weights are being resolved.
    :type panel: list[BaseAgent]
    :param specs: The specs the panel was built from; used to look up each
        agent's explicit weight override by ``agent_key`` (an agent's own
        ``.spec`` is used as a fallback when no matching spec is present).
    :type specs: list[AgentSpec]
    :return: Mapping of each panel agent's ``agent_key`` to its resolved weight.
    :rtype: dict[str, float]
    """
    spec_by_key: dict[str, AgentSpec] = {spec.agent_key: spec for spec in specs}

    resolved: dict[str, float] = {}
    for agent in panel:
        spec = spec_by_key.get(agent.agent_key, agent.spec)
        resolved[agent.agent_key] = spec.weight if spec.weight is not None else agent.default_weight

    return {agent.agent_key: resolved[agent.agent_key] for agent in panel}
