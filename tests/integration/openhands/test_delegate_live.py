"""Live delegation tests for the OpenHands backend over REST/WS (Task 12.0/02).

Proves the delegation path against a real OpenHands sidecar: a live
``delegate()`` returns a well-formed :class:`~aegis_swr.code_intel.backend.CodeResult`,
at least one :class:`~aegis_swr.openhands.events.OpenHandsAction` is emitted
(proving real navigation), exactly one
:class:`~aegis_swr.openhands.events.OpenHandsCompleted` carries a positive token
figure, and — the load-bearing assertion — the delegated task executes **inside
the Docker sandbox** rather than on the test host (C8).

**Wire-shape caveat.** The REST/WS shapes this client uses (``POST
/api/conversations``, Socket.IO ``oh_event``/``oh_user_action``, and the raw
event dict projection) follow the researched V1-server names recorded in Task
07.0 but have **never been validated against a live OpenHands server**. Treat
the first successful run as a contract-discovery exercise; assertion failures
may reflect wire-shape mismatches rather than product bugs.

Skipped as a whole when ``OPENHANDS_SERVER_URL`` is unset, the Docker daemon is
unreachable, or ``python-socketio`` is not installed.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from aegis_swr.code_intel.backend import CodeResult, CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openhands.client import OpenHandsClient
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.events import OpenHandsAction, OpenHandsCompleted
from aegis_swr.openhands.tool import OpenHandsTool
from tests.integration.openhands.conftest import require_openhands

require_openhands()  # module-level: one skip line when URL unset, Docker down, or socketio absent


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber for the delegate live tests."""

    def __init__(self):
        """Initialise with an empty event list."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent):
        """Append *event* to the capture list."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Return events matching *event_type* (or any subclass).

        :param event_type: The target event class to filter on.
        :return: Matching events in emission order.
        """
        return [e for e in self.events if isinstance(e, event_type)]


def _build_tool(client: OpenHandsClient, bus: EventBus) -> OpenHandsTool:
    """Build an :class:`OpenHandsTool` pointed at the live server URL.

    :param client: REST/WS client connected to the running sidecar.
    :param bus: Event bus for ``openhands.*`` lifecycle emissions.
    :return: Configured :class:`OpenHandsTool` ready for ``delegate()``.
    """
    return OpenHandsTool(
        client,
        OpenHandsSettings(server_url=os.environ["OPENHANDS_SERVER_URL"]),
        bus,
        CallBudget(max_tokens=4096),
    )


def _ctx() -> CodeTaskContext:
    """Return a fresh live :class:`CodeTaskContext` (``dry_run=False``).

    :return: Context with a new UUID4 run id.
    """
    return CodeTaskContext(run_id=uuid.uuid4(), dry_run=False)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


async def test_delegate_returns_code_result_shape(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """[Integration] openhands delegate: A live delegate() against the running sidecar returns a real CodeResult.

    Scenario: delegate() flows through the OpenHands REST/WS client against a
    live sandboxed runtime and returns an available, non-empty result.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify OPENHANDS_SERVER_URL points to a reachable
    sidecar and the Docker runtime is healthy; also check the wire-shape caveat
    in the module docstring.
    """
    bus = EventBus()
    tool = _build_tool(live_openhands_client, bus)
    result: CodeResult = await tool.delegate(
        task=f"Find compute_checksum under {stub_project} and name its file.",
        ctx=_ctx(),
    )
    assert result.available is True
    assert result.content.strip()
    assert result.token_estimate > 0


async def test_at_least_one_action_emitted(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """[Integration] openhands delegate: At least one openhands.action proves real navigation.

    Scenario: the sandboxed runtime must navigate the stub project using its own
    tool loop; at least one OpenHandsAction event must be emitted.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify the stub project is mounted inside the
    sandbox and the navigation task targets a path the runtime can read.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)

    tool = _build_tool(live_openhands_client, bus)
    await tool.delegate(
        task=f"Grep for compute_checksum under {stub_project} and report its file.",
        ctx=_ctx(),
    )
    assert recorder.of(OpenHandsAction), "expected at least one OpenHandsAction event"


async def test_task_executes_inside_docker_sandbox(
    live_openhands_client: OpenHandsClient,
):
    """[Integration] openhands delegate: The task ran inside the Docker container, not on the host (C8).

    Scenario: /.dockerenv exists inside every Docker container but not on a
    normal host. We first assert the host lacks it (sanity), then ask the
    runtime to report whether it can see it; a DOCKERENV_PRESENT response proves
    in-container execution.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify the OpenHands runtime is truly Docker-
    sandboxed (not local/unsandboxed mode) and that the model correctly reported
    the /.dockerenv presence.
    """
    assert not Path("/.dockerenv").exists(), "test host unexpectedly looks containerised"

    bus = EventBus()
    tool = _build_tool(live_openhands_client, bus)
    result: CodeResult = await tool.delegate(
        task=(
            "Report exactly whether the file /.dockerenv exists in your working "
            "environment. Answer with the single token DOCKERENV_PRESENT if it "
            "exists, or DOCKERENV_ABSENT if it does not."
        ),
        ctx=_ctx(),
    )
    assert "DOCKERENV_PRESENT" in result.content, "task did not run inside the Docker sandbox (C8)"


async def test_completed_event_carries_token_estimate(
    live_openhands_client: OpenHandsClient,
    stub_project: Path,
):
    """[Integration] openhands delegate: Exactly one openhands.completed carries a positive token figure (C9).

    Scenario: after a live delegate() exactly one OpenHandsCompleted event is
    emitted and its token_estimate is strictly positive (server-reported usage
    when available, otherwise the boundary estimate).

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: verify the sidecar emits a terminal stream event
    and that the token accounting path in OpenHandsTool fires correctly.
    """
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)

    tool = _build_tool(live_openhands_client, bus)
    await tool.delegate(
        task=f"Locate compute_checksum under {stub_project}.",
        ctx=_ctx(),
    )
    completed = recorder.of(OpenHandsCompleted)
    assert len(completed) == 1, "expected exactly one OpenHandsCompleted event"
    assert completed[0].token_estimate > 0  # type: ignore[attr-defined]
