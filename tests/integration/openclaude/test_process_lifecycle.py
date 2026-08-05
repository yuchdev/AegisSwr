"""Live managed-mode process-lifecycle integration tests (C6, Task 08.0).

Proves the managed lifecycle against a real OpenClaude sidecar: ``__aenter__``
brings a subprocess to a connectable free port within ``connect_timeout_s`` and
emits exactly one :class:`OpenClaudeConnected`; ``__aexit__`` terminates the
process and emits exactly one :class:`OpenClaudeDisconnected`; and no sidecar
survives the context. These tests build their **own** process (not the shared
``live_openclaude_process`` fixture) so they can observe the transitions.

Skipped as a whole when ``OPENCLAUDE_INTEGRATION`` is unset or the ``openclaude``
binary is absent.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis_swr.openclaude.process import OpenClaudeProcess
from tests.integration.openclaude.conftest import managed_settings, require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self) -> None:
        """Helper that provides init for the process lifecycle tests."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        """Helper that provides call for the process lifecycle tests."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Helper that provides of for the process lifecycle tests."""
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_recorder() -> tuple[EventBus, _Recorder]:
    """Helper that provides bus with recorder for the process lifecycle tests."""
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)
    return bus, recorder


async def test_managed_start_connects_within_timeout(stub_project: Path) -> None:
    """[Integration] process lifecycle: Managed ``__aenter__`` exposes a ready ``grpc_url`` within ``connect_timeout_s``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: managed ``__aenter__`` exposes a ready ``grpc_url`` within ``connect_timeout_s``.
    """
    _ = stub_project  # ensure the stub tree exists for this test's lifetime
    settings = managed_settings()
    bus, _ = _bus_with_recorder()
    start = time.monotonic()
    async with OpenClaudeProcess(settings, bus, run_id="lifecycle-1") as proc:
        assert proc.grpc_url  # resolved, concrete free port
        assert (time.monotonic() - start) <= settings.connect_timeout_s


async def test_connected_and_disconnected_emitted_exactly_once(stub_project: Path) -> None:
    """[Integration] process lifecycle: Exactly one connected on entry and exactly one disconnected on exit (C6).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: exactly one connected on entry and exactly one disconnected on exit (C6).
    """
    _ = stub_project  # ensure the stub tree exists for this test's lifetime
    bus, recorder = _bus_with_recorder()
    async with OpenClaudeProcess(managed_settings(), bus, run_id="lifecycle-2"):
        assert len(recorder.of(OpenClaudeConnected)) == 1
        assert recorder.of(OpenClaudeDisconnected) == []
    assert len(recorder.of(OpenClaudeDisconnected)) == 1


async def test_no_process_survives_context(stub_project: Path) -> None:
    """[Integration] process lifecycle: Managed subprocess terminates gracefully on exit; no sidecar survives the context.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: managed subprocess terminates gracefully on exit; no sidecar survives the context.
    """
    _ = stub_project  # ensure the stub tree exists for this test's lifetime
    bus, _ = _bus_with_recorder()
    proc = OpenClaudeProcess(managed_settings(), bus, run_id="lifecycle-3")
    async with proc:
        child = proc._process  # noqa: SLF001 - inspecting the live subprocess
        assert child is not None
        pid = child.pid  # capture before exit for the post-context PID probe
        assert child.returncode is None  # running inside the block

    # 1. In-process returncode: the child exited and was reaped.
    assert child.returncode is not None

    # 2. Grace-period / no-SIGKILL assertion (08.0/02 gap): a healthy process
    #    must respond to SIGTERM within _TERMINATE_GRACE_S without escalation
    #    to SIGKILL.  returncode == -9 would prove SIGKILL was required.
    assert child.returncode != -9, (
        f"sidecar PID {pid} required SIGKILL (returncode={child.returncode}); "
        "a healthy process should exit on SIGTERM within the grace period"
    )

    # 3. External PID-existence probe: os.kill(pid, 0) must raise
    #    ProcessLookupError once the child is gone (08.0/02 gap, no psutil).
    #    NOTE: PID reuse is an accepted limitation of this probe technique;
    #    the risk is negligible in the narrow window immediately after __aexit__.
    try:
        os.kill(pid, 0)
        raise AssertionError(  # pragma: no cover - only reached on test failure
            f"PID {pid} still exists after context exit; possible process leak or extremely unlikely PID reuse"
        )
    except ProcessLookupError as e:
        assert isinstance(e, ProcessLookupError)  # expected: the child process is gone
