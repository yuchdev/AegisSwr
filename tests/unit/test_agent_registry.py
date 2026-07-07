"""Unit tests for the agent registry and panel resolution.

Covers :mod:`aegis_swr.agents.registry` (lookup + unknown-key error) and
:mod:`aegis_swr.agents.panel` (``resolve_panel`` happy path, unknown-key
warn-and-skip, arbiter-count enforcement, and the two-tier
``resolve_consensus_weights`` precedence - explicit override then the agent's
own declared ``default_weight``).
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
from aegis_swr.config.settings import Settings
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
    default_weight: ClassVar[float] = 0.10

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
# resolve_consensus_weights (two-tier precedence: explicit override, then the
# agent's own declared default_weight)
# ---------------------------------------------------------------------------


def _panel(ai_backend, settings, specs: list[AgentSpec]) -> list[BaseAgent]:
    """Instantiate *specs* into agents without the arbiter-count gate."""
    return [create_agent(spec, ai_backend, settings) for spec in specs]


def test_weights_explicit_override_wins(ai_backend, settings):
    """[Unit] weights: an explicit AgentSpec.weight beats the agent's default."""
    specs = [
        AgentSpec(agent_key="os_kernel", weight=0.9),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs)
    # os_kernel's declared default_weight is 0.35; the explicit override wins.
    assert weights["os_kernel"] == 0.9
    # skeptic has no override, so it falls back to its declared default_weight.
    assert weights["skeptic"] == pytest.approx(SkepticAgent.default_weight)


def test_weights_use_agent_declared_default(ai_backend, settings):
    """[Unit] weights: with no override each agent contributes its own default_weight."""
    specs = [
        AgentSpec(agent_key="os_kernel"),
        AgentSpec(agent_key="code_analyst"),
        AgentSpec(agent_key="log_historian"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs)
    assert weights == {
        "os_kernel": pytest.approx(0.35),
        "code_analyst": pytest.approx(0.35),
        "log_historian": pytest.approx(0.17),
        "skeptic": pytest.approx(0.13),
    }
    # The four built-in defaults are authored to sum to exactly 1.0.
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weights_priority_does_not_affect_weight(ai_backend, settings):
    """[Unit] weights: priority is ordering-only and no longer changes the weight."""
    high = [AgentSpec(agent_key="os_kernel", priority=5), AgentSpec(agent_key="skeptic")]
    low = [AgentSpec(agent_key="os_kernel", priority=1), AgentSpec(agent_key="skeptic")]
    w_high = resolve_consensus_weights(_panel(ai_backend, settings, high), high)
    w_low = resolve_consensus_weights(_panel(ai_backend, settings, low), low)
    assert w_high["os_kernel"] == w_low["os_kernel"] == pytest.approx(OSKernelAgent.default_weight)


def test_weights_mixed_override_and_default(ai_backend, settings):
    """[Unit] weights: an override on one agent leaves the others on their defaults."""
    specs = [
        AgentSpec(agent_key="os_kernel", weight=0.7),
        AgentSpec(agent_key="code_analyst"),
        AgentSpec(agent_key="skeptic"),
    ]
    panel = _panel(ai_backend, settings, specs)
    weights = resolve_consensus_weights(panel, specs)
    assert weights["os_kernel"] == 0.7
    assert weights["code_analyst"] == pytest.approx(CodeAnalystAgent.default_weight)
    assert weights["skeptic"] == pytest.approx(SkepticAgent.default_weight)
