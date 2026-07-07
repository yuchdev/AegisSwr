"""Unit tests for the panel-selection strategies.

Covers :class:`~aegis_swr.core.panel_strategy.ExplicitPanelStrategy`,
:class:`~aegis_swr.core.panel_strategy.AgenticManagerStrategy` (now registry-
driven), and the :class:`~aegis_swr.core.panel_strategy.PanelResolver`
dispatcher.
"""

from __future__ import annotations

import pytest

from aegis_swr.agents.base import AgentSpec
from aegis_swr.agents.registry import AGENT_REGISTRY
from aegis_swr.config.settings import Settings
from aegis_swr.core.panel_strategy import (
    AgenticManagerStrategy,
    ExplicitPanelStrategy,
    PanelResolver,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# ExplicitPanelStrategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_strategy_returns_its_specs_untouched():
    """[Unit] explicit: select returns the supplied specs, ignoring the brief."""
    specs = [AgentSpec(agent_key="os_kernel", priority=5), AgentSpec(agent_key="skeptic")]
    strategy = ExplicitPanelStrategy(specs)
    result = await strategy.select({"fault_class": "stack_overflow"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]
    assert result[0].priority == 5


# ---------------------------------------------------------------------------
# AgenticManagerStrategy (registry-driven)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agentic_manager_proposes_the_full_registered_roster(settings: Settings):
    """[Unit] agentic: the candidate pool is every registered agent, in registry order."""
    strategy = AgenticManagerStrategy(settings)
    result = await strategy.select({"fault_class": "memory_access_violation"})
    assert [s.agent_key for s in result] == list(AGENT_REGISTRY)
    assert all(s.priority == 3 for s in result)


@pytest.mark.asyncio
async def test_agentic_manager_honors_a_custom_registry(settings: Settings):
    """[Unit] agentic: a custom registry override defines the candidate roster and order."""
    custom_registry = {"os_kernel": object, "skeptic": object}
    strategy = AgenticManagerStrategy(settings, registry=custom_registry)
    result = await strategy.select({"fault_class": "stack_overflow"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


@pytest.mark.asyncio
async def test_agentic_manager_ignores_the_brief(settings: Settings):
    """[Unit] agentic: selection is roster-driven and independent of the brief contents."""
    strategy = AgenticManagerStrategy(settings)
    from_full_brief = await strategy.select({"fault_class": "deadlock"})
    from_empty_brief = await strategy.select({})
    assert [s.agent_key for s in from_full_brief] == [s.agent_key for s in from_empty_brief] == list(AGENT_REGISTRY)


# ---------------------------------------------------------------------------
# PanelResolver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_delegates_to_explicit_when_specs_present(settings: Settings):
    """[Unit] resolver: explicit specs win and the brief is ignored."""
    resolver = PanelResolver(settings)
    explicit = [AgentSpec(agent_key="code_analyst"), AgentSpec(agent_key="skeptic")]
    result = await resolver.resolve({"fault_class": "stack_overflow"}, explicit_specs=explicit)
    assert [s.agent_key for s in result] == ["code_analyst", "skeptic"]


@pytest.mark.asyncio
async def test_resolver_uses_auto_when_specs_absent(settings: Settings):
    """[Unit] resolver: None explicit specs route to the registry-driven auto manager."""
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "memory_access_violation"}, explicit_specs=None)
    assert [s.agent_key for s in result] == list(AGENT_REGISTRY)


@pytest.mark.asyncio
async def test_resolver_treats_empty_explicit_list_as_auto(settings: Settings):
    """[Unit] resolver: an empty explicit list falls through to auto selection."""
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "deadlock"}, explicit_specs=[])
    assert [s.agent_key for s in result] == list(AGENT_REGISTRY)
