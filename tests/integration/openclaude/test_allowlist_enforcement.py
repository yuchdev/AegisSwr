"""Live allowlist-enforcement integration tests (C7, Task 08.0).

Proves the forensic read-only guarantee against a **real** OpenClaude process: a
task requiring a write-capable tool is **denied** under the default allowlist
(``Read,Grep,Glob,Bash`` — no ``Write``/``Edit``), leaving the stub project
byte-identical, while a ``Read``/``Grep``-only task against the same process
succeeds. This is the concrete end-to-end evidence that OpenClaude cannot mutate
the repository under analysis.

Per contract C9, :meth:`OpenClaudeTool.delegate` never raises: a denied command
surfaces as a non-retriable failure :class:`CodeResult`
(``metadata["error"] == "permission_denied"``) plus an emitted
:class:`OpenClaudePermissionDenied` event — not an exception.

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
from aegis_swr.openclaude.events import OpenClaudePermissionDenied
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis_swr.openclaude.tool import OpenClaudeTool
from tests.integration.openclaude.conftest import require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self) -> None:
        """Helper that provides init for the allowlist enforcement tests."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        """Helper that provides call for the allowlist enforcement tests."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Helper that provides of for the allowlist enforcement tests."""
        return [e for e in self.events if isinstance(e, event_type)]


def _build_tool(client: OpenClaudeGrpcClient, bus: EventBus) -> OpenClaudeTool:
    """Helper that provides build tool for the allowlist enforcement tests."""
    settings = OpenClaudeSettings(grpc_url="localhost:50051")  # default read-only allowlist
    return OpenClaudeTool(client, settings, bus, CallBudget(max_tokens=10_000_000))


def _live_ctx() -> CodeTaskContext:
    """Helper that provides live ctx for the allowlist enforcement tests."""
    return CodeTaskContext(run_id=uuid.uuid4(), dry_run=False)


async def test_write_task_denied_under_default_allowlist(
    live_grpc_client: OpenClaudeGrpcClient,
    stub_project: Path,
) -> None:
    """[Integration] allowlist enforcement: A task needing a write tool is denied; the stub project is left unmodified.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a task needing a write tool is denied; the stub project is left unmodified.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)
    tool = _build_tool(live_grpc_client, bus)

    target = stub_project / "app.py"
    before = target.read_bytes()

    result = await tool.delegate(
        f"Edit {target}: rename compute_checksum to compute_crc and save the file.",
        _live_ctx(),
    )

    # delegate never raises (C9): the denial is a non-retriable failure result.
    assert result.metadata["ok"] is False
    assert result.metadata["error"] == "permission_denied"
    assert result.metadata["retriable"] is False
    assert recorder.of(OpenClaudePermissionDenied), "expected an OpenClaudePermissionDenied event"
    assert target.read_bytes() == before  # stub project unmodified


async def test_read_only_task_succeeds(live_grpc_client: OpenClaudeGrpcClient) -> None:
    """[Integration] allowlist enforcement: A ``Read``/``Grep``-only navigation task succeeds under the same allowlist.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a ``Read``/``Grep``-only navigation task succeeds under the same allowlist.
    """
    tool = _build_tool(live_grpc_client, EventBus())
    result = await tool.delegate(
        "Grep for compute_checksum and report the file it is defined in.",
        _live_ctx(),
    )
    assert result.metadata["ok"] is True
    assert result.content.strip()
