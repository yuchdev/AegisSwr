"""Unit tests for the agent registry and panel resolution.

Covers :mod:`aegis_swr.agents.registry` (lookup + unknown-key error) and
:mod:`aegis_swr.agents.panel` (``resolve_panel`` happy path, unknown-key
warn-and-skip, arbiter-count enforcement, and the three-tier
``resolve_consensus_weights`` precedence).
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from aegis_swr.agents import registry
from aegis_swr.agents.base import AgentSpec, BaseAgent
from aegis_swr.agents.code_analyst import CodeAnalystAgent
from aegis_swr.agents.log_historian import LogHistorianAgent
from aegis_swr.agents.os_kernel import OSKernelAgent
from aegis_swr.agents.panel import (
    PanelResolutionError,
    resolve_consensus_weights,
    resolve_panel,
)
from aegis_swr.agents.registry import (
    AGENT_REGISTRY,
    UnknownAgentError,
    create_agent,
)
from aegis_swr.agents.skeptic import SkepticAgent
from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.config.settings import (
    AgentWeightEntry,
    AgentWeightsSettings,
    Settings,
)
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import AgentRole, AgentTurn, InvestigationState
from tests.unit.fixtures.mock_ai_backend import MockAIBackend


@pytest.fixture
def ai_backend() -> AIAPIBackend:
    return MockAIBackend()


@pytest.fixture
def settings() -> Settings:
    return Settings()


class _SecondArbiter(BaseAgent):
    """A throwaway second arbiter used to exercise the >1-arbiter guard."""

    agent_key: ClassVar[str] = "second_arbiter"
    display_name: ClassVar[str] = "Second Arbiter"
    category: ClassVar[str] = "base"
    role: ClassVar[AgentRole] = AgentRole.ARBITER

    @property
    def system_prompt(self) -> str:
        return "second arbiter"

    async def run(self, state: InvestigationState) -> AgentTurn:
        return self.make_turn(turn_number=1, message="x", confidence_score=0.5)


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_registry_maps_every_agent_key_to_its_class():
    """[Unit] registry: the four concrete agents register under their keys."""
    assert AGENT_REGISTRY == {
        "os_kernel": OSKernelAgent,
        "code_analyst": CodeAnalystAgent,
        "log_historian": LogHistorianAgent,
        "skeptic": SkepticAgent,
    }


def test_create_agent_instantiates_registered_class(ai_backend, settings):
    """[Unit] registry: create_agent builds the right class and attaches the spec."""
    spec = AgentSpec(agent_key="skeptic", priority=4)
    agent = create_agent(spec, ai_backend, settings)
    assert isinstance(agent, SkepticAgent)
    assert agent.spec is spec
    assert agent.spec.priority == 4


def test_create_agent_unknown_key_raises(ai_backend, settings):
    """[Unit] registry: an unregistered key raises UnknownAgentError."""
    spec = AgentSpec(agent_key="does_not_exist")
    with pytest.raises(UnknownAgentError):
        create_agent(spec, ai_backend, settings)


# ---------------------------------------------------------------------------
# resolve_panel
# ---------------------------------------------------------------------------


def test_resolve_panel_happy_path(ai_backend, settings):
    """[Unit] panel: enabled specs resolve to agents preserving order."""
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="code_analyst"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = resolve_panel(specs, ai_backend, settings)
    assert [a.agent_key for a in panel] == ["os_kernel", "code_analyst", "skeptic"]


def test_resolve_panel_drops_disabled_specs(ai_backend, settings):
    """[Unit] panel: disabled specs are excluded from the resolved panel."""
    specs = [
        AgentSpec(agent_key="os_kernel", enabled=False),
        AgentSpec(agent_key="code_analyst"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = resolve_panel(specs, ai_backend, settings)
    assert [a.agent_key for a in panel] == ["code_analyst", "skeptic"]


def test_resolve_panel_unknown_key_warns_and_skips(ai_backend, settings):
    """[Unit] panel: an unknown key is skipped, not fatal (warn-and-skip)."""
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="typo_agent"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = resolve_panel(specs, ai_backend, settings)
    assert [a.agent_key for a in panel] == ["os_kernel", "skeptic"]


def test_resolve_panel_zero_arbiters_raises(ai_backend, settings):
    """[Unit] panel: a panel with no arbiter is a hard error."""
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="code_analyst"),
    ]
    with pytest.raises(PanelResolutionError):
        resolve_panel(specs, ai_backend, settings)


def test_resolve_panel_two_arbiters_raises(ai_backend, settings, monkeypatch):
    """[Unit] panel: two arbiters make the convergence gate ambiguous - raise."""
    monkeypatch.setitem(registry.AGENT_REGISTRY, "second_arbiter", _SecondArbiter)
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="skeptic"),
        AgentSpec(agent_key="second_arbiter"),
    ]
    with pytest.raises(PanelResolutionError):
        resolve_panel(specs, ai_backend, settings)


# ---------------------------------------------------------------------------
# resolve_consensus_weights (three-tier precedence)
# ---------------------------------------------------------------------------


def _panel(ai_backend, settings, specs: list[AgentSpec]) -> list[BaseAgent]:
    """Instantiate *specs* into agents without the arbiter-count gate."""
    return [create_agent(spec, ai_backend, settings) for spec in specs]


def test_weights_explicit_override_wins(ai_backend, settings):
    """[Unit] weights: an explicit AgentSpec.weight beats the curated value."""
    specs = [
        AgentSpec(agent_key="os_kernel", weight=0.9),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs, FaultClass.MEMORY_ACCESS_VIOLATION, AgentWeightsSettings())
    # Curated os_kernel weight for this fault class is 0.40; explicit wins.
    assert weights["os_kernel"] == 0.9


def test_weights_curated_wins_over_priority(ai_backend, settings):
    """[Unit] weights: the curated fault-class value beats the priority default."""
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs, FaultClass.MEMORY_ACCESS_VIOLATION, AgentWeightsSettings())
    assert weights["os_kernel"] == pytest.approx(0.40)
    assert weights["skeptic"] == pytest.approx(0.10)


def test_weights_priority_fallback_normalizes(ai_backend, settings):
    """[Unit] weights: tier-3 agents normalize by priority/sum-of-tier-3."""
    # An empty curated entry for UNKNOWN forces every agent through to tier 3.
    weights_settings = AgentWeightsSettings(unknown=AgentWeightEntry(weights={}))
    specs = [
        AgentSpec(agent_key="os_kernel", priority=4),
        AgentSpec(agent_key="code_analyst", priority=2),
        AgentSpec(agent_key="skeptic", priority=3),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs, FaultClass.UNKNOWN, weights_settings)
    # Tier-3 priority sum = 4 + 2 + 3 = 9.
    assert weights["os_kernel"] == pytest.approx(4 / 9)
    assert weights["code_analyst"] == pytest.approx(2 / 9)
    assert weights["skeptic"] == pytest.approx(3 / 9)
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weights_mixed_tiers_do_not_cross_contaminate(ai_backend, settings):
    """[Unit] weights: tier-3 normalization ignores tier-1/2 resolved weights."""
    # os_kernel: explicit (tier 1). code_analyst: curated (tier 2).
    # log_historian + skeptic: priority default (tier 3), curated emptied.
    weights_settings = AgentWeightsSettings(unknown=AgentWeightEntry(weights={"code_analyst": 0.5}))
    specs = [
        AgentSpec(agent_key="os_kernel", weight=0.7),
        AgentSpec(agent_key="code_analyst"),
        AgentSpec(agent_key="log_historian", priority=1),
        AgentSpec(agent_key="skeptic", priority=3),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs, FaultClass.UNKNOWN, weights_settings)
    assert weights["os_kernel"] == 0.7
    assert weights["code_analyst"] == pytest.approx(0.5)
    # Tier-3 sum of priorities is 1 + 3 = 4 (os_kernel/code_analyst excluded).
    assert weights["log_historian"] == pytest.approx(1 / 4)
    assert weights["skeptic"] == pytest.approx(3 / 4)
