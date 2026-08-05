"""Unit tests for the panel-selection strategies.

Covers :class:`~aegis_swr.core.panel_strategy.ExplicitPanelStrategy`,
:class:`~aegis_swr.core.panel_strategy.AgenticManagerStrategy` (now registry-
driven), and the :class:`~aegis_swr.core.panel_strategy.PanelResolver`
dispatcher.
"""

from __future__ import annotations

import pytest

from aegis_swr.agents.base import AgentSpec
from aegis_swr.config.settings import Settings
from aegis_swr.core.panel_strategy import (
    AgenticManagerStrategy,
    ExplicitPanelStrategy,
    PanelResolver,
)


@pytest.fixture
def settings() -> Settings:
    """Helper that provides settings for the panel strategy tests."""
    return Settings()


# ---------------------------------------------------------------------------
# ExplicitPanelStrategy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_strategy_returns_its_specs_untouched():
    """[Unit] explicit: select returns the supplied specs, ignoring the brief.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: select returns the supplied specs, ignoring the brief.
    """
    specs = [AgentSpec(agent_key="os_kernel", priority=5), AgentSpec(agent_key="skeptic")]
    strategy = ExplicitPanelStrategy(specs)
    result = await strategy.select({"fault_class": "stack_overflow"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]
    assert result[0].priority == 5


# ---------------------------------------------------------------------------
# AgenticManagerStrategy (registry-driven)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agentic_manager_proposes_base_agents_plus_matching_specialists(settings: Settings):
    """[Unit] agentic: base agents always, plus specialists authoritative for the fault.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: base agents always, plus specialists authoritative for the fault.
    """
    strategy = AgenticManagerStrategy(settings)
    keys = [s.agent_key for s in await strategy.select({"fault_class": "memory_access_violation"})]
    # Base agents always present.
    for base in ("os_kernel", "code_analyst", "log_historian", "skeptic"):
        assert base in keys
    # memory_forensics is authoritative for MAV; concurrency_analyst is not.
    assert "memory_forensics" in keys
    assert "concurrency_analyst" not in keys
    assert all(s.priority == 3 for s in await strategy.select({"fault_class": "memory_access_violation"}))


@pytest.mark.asyncio
async def test_agentic_manager_honors_a_custom_registry(settings: Settings):
    """[Unit] agentic: a custom registry override defines the candidate roster and order.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a custom registry override defines the candidate roster and order.
    """
    custom_registry = {"os_kernel": object, "skeptic": object}
    strategy = AgenticManagerStrategy(settings, registry=custom_registry)
    result = await strategy.select({"fault_class": "stack_overflow"})
    assert [s.agent_key for s in result] == ["os_kernel", "skeptic"]


@pytest.mark.asyncio
async def test_agentic_manager_is_fault_aware(settings: Settings):
    """[Unit] agentic: forensic specialists are gated by the brief's fault class.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: forensic specialists are gated by the brief's fault class.
    """
    strategy = AgenticManagerStrategy(settings)
    for_memory = [s.agent_key for s in await strategy.select({"fault_class": "memory_access_violation"})]
    for_deadlock = [s.agent_key for s in await strategy.select({"fault_class": "deadlock"})]
    for_divzero = [s.agent_key for s in await strategy.select({"fault_class": "integer_divide_by_zero"})]
    for_empty = [s.agent_key for s in await strategy.select({})]

    assert "memory_forensics" in for_memory and "concurrency_analyst" not in for_memory
    assert "concurrency_analyst" in for_deadlock and "memory_forensics" not in for_deadlock
    # A fault class no specialist claims (and no fault at all) yields the base four.
    base_four = ["os_kernel", "code_analyst", "log_historian", "skeptic"]
    assert for_divzero == base_four
    assert for_empty == base_four


# ---------------------------------------------------------------------------
# PanelResolver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolver_delegates_to_explicit_when_specs_present(settings: Settings):
    """[Unit] resolver: explicit specs win and the brief is ignored.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: explicit specs win and the brief is ignored.
    """
    resolver = PanelResolver(settings)
    explicit = [AgentSpec(agent_key="code_analyst"), AgentSpec(agent_key="skeptic")]
    result = await resolver.resolve({"fault_class": "stack_overflow"}, explicit_specs=explicit)
    assert [s.agent_key for s in result] == ["code_analyst", "skeptic"]


@pytest.mark.asyncio
async def test_resolver_uses_auto_when_specs_absent(settings: Settings):
    """[Unit] resolver: None explicit specs route to the fault-aware auto manager.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: none explicit specs route to the fault-aware auto manager.
    """
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "memory_access_violation"}, explicit_specs=None)
    keys = [s.agent_key for s in result]
    for base in ("os_kernel", "code_analyst", "log_historian", "skeptic"):
        assert base in keys
    assert "memory_forensics" in keys


@pytest.mark.asyncio
async def test_resolver_treats_empty_explicit_list_as_auto(settings: Settings):
    """[Unit] resolver: an empty explicit list falls through to (fault-aware) auto selection.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: an empty explicit list falls through to (fault-aware) auto selection.
    """
    resolver = PanelResolver(settings)
    result = await resolver.resolve({"fault_class": "integer_divide_by_zero"}, explicit_specs=[])
    # integer_divide_by_zero matches no forensic specialist, so auto yields the base four.
    assert [s.agent_key for s in result] == [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "skeptic",
    ]
