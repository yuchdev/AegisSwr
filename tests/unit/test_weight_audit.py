"""Milestone 0002 exit gate: per-fault panel & consensus-weight audit (Task 08.0).

The roadmap's config-file weight matrix was superseded by intrinsic per-agent
``default_weight`` (self-normalized by the live panel) plus fault-aware
auto-selection driven by each agent's ``authoritative_fault_classes``. This
audit therefore verifies the *authority matrix* directly: for every
:class:`FaultClass`, the auto-resolved, ordered debate panel matches the ratified
composition (subtask 01), ``skeptic`` is always last, the default (no-fault)
panel is the legacy four, and the resolved consensus weights normalize to 1.0.
"""

from __future__ import annotations

import pytest

from aegis_swr.agents.panel import resolve_consensus_weights, resolve_panel
from aegis_swr.config.settings import Settings
from aegis_swr.core.consensus import ConsensusEvaluator
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.orchestrator import Orchestrator
from aegis_swr.core.panel_strategy import AgenticManagerStrategy
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

_BASE_FOUR = ["os_kernel", "code_analyst", "log_historian", "skeptic"]

# Ratified per-fault panels (subtask 01 authority matrix), skeptic always last.
_RATIFIED_PANELS: dict[FaultClass, list[str]] = {
    FaultClass.MEMORY_ACCESS_VIOLATION: [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "memory_forensics",
        "exploitability",
        "skeptic",
    ],
    FaultClass.NULL_POINTER_DEREFERENCE: ["os_kernel", "code_analyst", "log_historian", "memory_forensics", "skeptic"],
    FaultClass.USE_AFTER_FREE: [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "memory_forensics",
        "concurrency_analyst",
        "exploitability",
        "skeptic",
    ],
    FaultClass.STACK_OVERFLOW: [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "exploitability",
        "resource_exhaustion",
        "skeptic",
    ],
    FaultClass.INTEGER_DIVIDE_BY_ZERO: _BASE_FOUR,
    FaultClass.DEADLOCK: [
        "os_kernel",
        "code_analyst",
        "log_historian",
        "concurrency_analyst",
        "resource_exhaustion",
        "skeptic",
    ],
    FaultClass.ASSERTION_FAILURE: ["os_kernel", "code_analyst", "log_historian", "concurrency_analyst", "skeptic"],
    FaultClass.RESOURCE_EXHAUSTION: ["os_kernel", "code_analyst", "log_historian", "resource_exhaustion", "skeptic"],
    FaultClass.UNHANDLED_EXCEPTION: _BASE_FOUR,
    FaultClass.UNKNOWN: _BASE_FOUR,
}


@pytest.fixture
def settings() -> Settings:
    """Helper that provides settings for the weight audit tests."""
    return Settings()


async def _ordered_panel_keys(fault: FaultClass, settings: Settings) -> list[str]:
    """Helper that provides ordered panel keys for the weight audit tests."""
    ai = MockAIBackend()
    specs = await AgenticManagerStrategy(settings).select({"fault_class": fault.value})
    panel = resolve_panel(specs, ai, settings)
    ordered = Orchestrator._order_panel(panel)
    return [agent.agent_key for agent in ordered]


async def test_default_panel_is_legacy_four(settings: Settings):
    """[Unit] weight audit: No fault class (auto) resolves to the legacy four-agent chain (back-compat).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: no fault class (auto) resolves to the legacy four-agent chain (back-compat).
    """
    ai = MockAIBackend()
    specs = await AgenticManagerStrategy(settings).select({})
    ordered = Orchestrator._order_panel(resolve_panel(specs, ai, settings))
    assert [a.agent_key for a in ordered] == _BASE_FOUR


@pytest.mark.parametrize("fault", list(FaultClass))
async def test_specialist_panel_matches_authority_matrix(fault: FaultClass, settings: Settings):
    """[Unit] weight audit: Each fault class auto-resolves to its ratified panel composition and order.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: each fault class auto-resolves to its ratified panel composition and order.
    """
    assert await _ordered_panel_keys(fault, settings) == _RATIFIED_PANELS[fault]


@pytest.mark.parametrize("fault", list(FaultClass))
async def test_skeptic_always_last(fault: FaultClass, settings: Settings):
    """[Unit] weight audit: The arbiter (skeptic) is the terminal node in every resolved panel.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the arbiter (skeptic) is the terminal node in every resolved panel.
    """
    assert (await _ordered_panel_keys(fault, settings))[-1] == "skeptic"


@pytest.mark.parametrize(
    "fault",
    [FaultClass.INTEGER_DIVIDE_BY_ZERO, FaultClass.UNHANDLED_EXCEPTION, FaultClass.UNKNOWN],
)
async def test_back_compat_base_only_classes(fault: FaultClass, settings: Settings):
    """[Unit] weight audit: Fault classes with no specialist keep exactly the four base agents.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: fault classes with no specialist keep exactly the four base agents.
    """
    assert await _ordered_panel_keys(fault, settings) == _BASE_FOUR


@pytest.mark.parametrize("fault", list(FaultClass))
async def test_consensus_weights_normalize_to_one(fault: FaultClass, settings: Settings):
    """[Unit] weight audit: Resolved per-panel weights are all positive and normalize to 1.0.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: resolved per-panel weights are all positive and normalize to 1.0.
    """
    ai = MockAIBackend()
    specs = await AgenticManagerStrategy(settings).select({"fault_class": fault.value})
    panel = resolve_panel(specs, ai, settings)
    weight_map = resolve_consensus_weights(panel, specs)

    assert all(w > 0.0 for w in weight_map.values())
    scores = dict.fromkeys(weight_map, 1.0)
    assert ConsensusEvaluator().calculate(scores, weight_map) == pytest.approx(1.0)
