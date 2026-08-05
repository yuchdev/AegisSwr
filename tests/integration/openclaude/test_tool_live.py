"""Live full-delegation integration tests through the sole ``CodeIntelBackend`` (Task 08.0).

Proves the delegation path against a live model: :meth:`OpenClaudeTool.delegate`
returns a non-empty result, exactly one :class:`OpenClaudeStreamCompleted` carries
a **positive** boundary token estimate (C5), and — the load-bearing assertion —
**at least one** :class:`OpenClaudeToolCall` is emitted, proving OpenClaude
actually navigated the stub project via its own tool loop rather than answering
from priors. This is also the runtime-quality gate: a model too weak to sustain a
multi-step tool flow fails here rather than degrading silently in production.

Skipped as a whole when ``OPENCLAUDE_INTEGRATION`` is unset or the ``openclaude``
binary is absent.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeStreamCompleted, OpenClaudeToolCall
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.tool import OpenClaudeTool
from tests.integration.openclaude.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent


def _task(stub_project: Path) -> str:
    """Build the navigation task string with the stub project's absolute path.

    The sidecar runs under ``_SAFE_CWD`` (not ``stub_project``), so every
    navigation task must reference stub files by their **absolute path** so
    the sidecar can locate them without relying on a particular cwd.
    """
    return (
        f"Read the file at {stub_project / 'app.py'} and describe which module "
        "compute_checksum is defined in, including its return type."
    )


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self) -> None:
        """Helper that provides init for the tool live tests."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        """Helper that provides call for the tool live tests."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Helper that provides of for the tool live tests."""
        return [e for e in self.events if isinstance(e, event_type)]


def _build_tool(client: OpenClaudeGrpcClient, bus: EventBus) -> OpenClaudeTool:
    """Helper that provides build tool for the tool live tests."""
    settings = OpenClaudeSettings(grpc_url="localhost:50051")  # default read-only allowlist
    return OpenClaudeTool(client, settings, bus, CallBudget(max_tokens=10_000_000))


def _live_ctx() -> CodeTaskContext:
    """Helper that provides live ctx for the tool live tests."""
    return CodeTaskContext(run_id=uuid.uuid4(), dry_run=False)


async def test_delegate_returns_non_empty_result(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """[Integration] tool live: A live delegate over a real navigation task returns non-empty result text.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a live delegate over a real navigation task returns non-empty result text.
    """
    tool = _build_tool(live_grpc_client, EventBus())
    result = await tool.delegate(_task(stub_project), _live_ctx())
    assert result.available is True
    assert result.content.strip()


async def test_stream_completed_carries_positive_token_estimate(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """[Integration] tool live: Exactly one ``OpenClaudeStreamCompleted`` is emitted with ``token_estimate > 0`` (C5).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: exactly one ``OpenClaudeStreamCompleted`` is emitted with ``token_estimate > 0`` (C5).
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)
    tool = _build_tool(live_grpc_client, bus)

    await tool.delegate(_task(stub_project), _live_ctx())

    completed = recorder.of(OpenClaudeStreamCompleted)
    assert len(completed) == 1
    assert completed[0].token_estimate > 0


async def test_at_least_one_tool_call_emitted(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """[Integration] tool live: >=1 ``OpenClaudeToolCall`` proves real navigation, not an answer from priors.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: >=1 ``OpenClaudeToolCall`` proves real navigation, not an answer from priors.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)
    tool = _build_tool(live_grpc_client, bus)

    await tool.delegate(_task(stub_project), _live_ctx())

    assert recorder.of(OpenClaudeToolCall), "expected at least one OpenClaudeToolCall event"
