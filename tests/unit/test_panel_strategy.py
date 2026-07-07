"""Unit tests for the panel-selection strategies.

Covers :class:`~aegis_swr.core.panel_strategy.ExplicitPanelStrategy`,
:class:`~aegis_swr.core.panel_strategy.AgenticManagerStrategy`, and the
:class:`~aegis_swr.core.panel_strategy.PanelResolver` dispatcher.
"""

from __future__ import annotations

import pytest

from aegis_swr.agents.base import AgentSpec
from aegis_swr.config.settings import AgentPanelSettings, Settings
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.panel_strategy import (
    AgenticManagerStrategy,
    ExplicitPanelStrategy,
    PanelResolver,
)


def _settings_with_panel(panel: AgentPanelSettings) -> Settings:
    """Return a Settings whose agent_panel is *panel*."""
    return Settings(agent_panel=panel)


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
# AgenticManagerStrategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agentic_manager_uses_default_panel_when_no_override():
    """[Unit] agentic: a fault class with no override falls back to default_panel."""
    settings = _settings_with_panel(AgentPanelSettings(default_panel=["os_kernel", "skeptic"], per_fault_class={}))
    strategy = AgenticManagerStrategy(settings)
    result = await strategy.select({"fault_class": "memory_access_violation"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]
    assert all(s.priority == 3 for s in result)


@pytest.mark.asyncio
async def test_agentic_manager_prefers_fault_class_override():
    """[Unit] agentic: a per-fault-class list wins over the default panel."""
    settings = _settings_with_panel(
        AgentPanelSettings(
            default_panel=["os_kernel", "code_analyst", "log_historian", "skeptic"],
            per_fault_class={"stack_overflow": ["os_kernel", "skeptic"]},
        )
    )
    strategy = AgenticManagerStrategy(settings)
    result = await strategy.select({"fault_class": "stack_overflow"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


@pytest.mark.asyncio
async def test_agentic_manager_filters_unregistered_candidate_keys():
    """[Unit] agentic: candidate keys not in the registry are dropped."""
    settings = _settings_with_panel(AgentPanelSettings(default_panel=["os_kernel", "ghost_agent", "skeptic"]))
    strategy = AgenticManagerStrategy(settings)
    result = await strategy.select({})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


@pytest.mark.asyncio
async def test_agentic_manager_unknown_fault_class_falls_back_to_default():
    """[Unit] agentic: an unrecognized fault_class string uses the default panel."""
    settings = _settings_with_panel(
        AgentPanelSettings(
            default_panel=["os_kernel", "skeptic"],
            per_fault_class={FaultClass.STACK_OVERFLOW.value: ["code_analyst", "skeptic"]},
        )
    )
    strategy = AgenticManagerStrategy(settings)
    result = await strategy.select({"fault_class": "not_a_real_fault"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


# ---------------------------------------------------------------------------
# PanelResolver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_delegates_to_explicit_when_specs_present():
    """[Unit] resolver: explicit specs win and the brief is ignored."""
    settings = _settings_with_panel(AgentPanelSettings(default_panel=["os_kernel", "skeptic"]))
    resolver = PanelResolver(settings)
    explicit = [AgentSpec(agent_key="code_analyst"), AgentSpec(agent_key="skeptic")]
    result = await resolver.resolve({"fault_class": "stack_overflow"}, explicit_specs=explicit)
    assert [s.agent_key for s in result] == ["code_analyst", "skeptic"]


@pytest.mark.asyncio
async def test_resolver_uses_auto_when_specs_absent():
    """[Unit] resolver: None explicit specs route to the auto manager."""
    settings = _settings_with_panel(AgentPanelSettings(default_panel=["os_kernel", "skeptic"]))
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "memory_access_violation"}, explicit_specs=None)
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


@pytest.mark.asyncio
async def test_resolver_treats_empty_explicit_list_as_auto():
    """[Unit] resolver: an empty explicit list falls through to auto selection."""
    settings = _settings_with_panel(AgentPanelSettings(default_panel=["os_kernel", "skeptic"]))
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "deadlock"}, explicit_specs=[])
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]
