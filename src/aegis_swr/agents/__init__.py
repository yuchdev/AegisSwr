"""Aegis SWR agent fleet.

Re-exports the base debate agents and shared primitives from
:mod:`aegis_swr.agents.base` so ``from aegis_swr.agents import OSKernelAgent``
(and the other four) keeps resolving after the base agents moved into the
``base`` subpackage. Category subpackages (:mod:`aegis_swr.agents.forensic`,
:mod:`aegis_swr.agents.synthesis`) hold the specialist and synthesis tiers.
"""

from aegis_swr.agents.base import (
    AgentCategory,
    AgentSpec,
    BaseAgent,
    CodeAnalystAgent,
    LogHistorianAgent,
    OSKernelAgent,
    SkepticAgent,
)

__all__ = [
    "AgentCategory",
    "AgentSpec",
    "BaseAgent",
    "OSKernelAgent",
    "CodeAnalystAgent",
    "LogHistorianAgent",
    "SkepticAgent",
]
