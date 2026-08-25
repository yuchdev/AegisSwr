"""End-to-end harness selection → composition → delegate smoke test (Task 12.0/03).

Exercises the milestone's headline deliverable — the neutral composition root
and the C2 single-active-backend selection contract — end-to-end against a
**live** backend, rather than constructing a tool directly as the per-backend
suites do. With exactly one presence signal configured and that backend
available, this smoke drives the full path an operator deployment takes:

``HarnessSettings`` resolves ``active_backend`` (C2)
→ :func:`~aegis_swr.harness.composition.build_code_agent` branches to the
single active family (C4)
→ a :class:`~aegis_swr.code_intel.agent.CodeAgent` is composed
→ a real ``investigate()`` flows through and returns a
:class:`~aegis_swr.code_intel.backend.CodeResult`.

Skipped as a whole when zero or more than one backend is both signalled and
live; the multi-signal rejection path (``HarnessConfigError``) is tested
unconditionally in ``test_selection_outcomes.py`` instead.
"""

from __future__ import annotations

import uuid
from contextlib import AsyncExitStack

from aegis_swr.code_intel.backend import CodeResult
from aegis_swr.core.events import EventBus
from aegis_swr.harness.composition import build_code_agent
from aegis_swr.harness.config import HarnessSettings
from tests.integration.harness.conftest import require_single_live_backend

require_single_live_backend()  # module-level: skip unless exactly one live backend


async def test_active_backend_resolves_to_the_single_live_family(
    active_backend_name: str,
):
    """[Integration] harness selection: HarnessSettings.active_backend auto-selects the single live family (C2).

    Scenario: with the selector unset and exactly one presence signal active,
    HarnessSettings.active_backend resolves to that family's name without any
    explicit configuration.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify only one backend presence signal is set in
    the environment and that AEGIS_CODE_INTEL_BACKEND is not overriding
    auto-selection.
    """
    settings = HarnessSettings()  # selector unset; sources per-family env signals
    assert settings.active_backend == active_backend_name


async def test_composition_then_live_delegate_flows_end_to_end(
    active_backend_name: str,
):
    """[Integration] harness selection: build_code_agent composes a CodeAgent whose live investigate() works (C4).

    Scenario: the neutral build_code_agent() composition root selects and
    assembles the active backend, investigate() delegates to a real live call,
    and the AsyncExitStack tears down any registered sidecar on block exit so
    nothing survives.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: inspect which backend is active (active_backend_name
    fixture) and verify its individual live suite passes first, since this smoke
    exercises the composition wiring rather than per-backend internals.
    """
    settings = HarnessSettings()
    bus = EventBus()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(
            settings,
            bus,
            stack,
            run_id=str(uuid.uuid4()),
        )
        result: CodeResult = await agent.investigate(
            task="Report the single token HARNESS_SMOKE_OK.",
            run_id=uuid.uuid4(),
        )
        assert result.available is True
        assert result.content.strip()
        assert result.token_estimate > 0
    # stack exit tears down any sidecar; nothing survives the block
