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

import time

from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis_swr.openclaude.process import OpenClaudeProcess
from tests.integration.openclaude.conftest import managed_settings, require_managed_openclaude

require_managed_openclaude()  # module-level: one skip line when binary/signal absent


class _Recorder:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_recorder() -> tuple[EventBus, _Recorder]:
    bus = EventBus()
    recorder = _Recorder()
    bus.subscribe(DomainEvent, recorder)
    return bus, recorder


async def test_managed_start_connects_within_timeout() -> None:
    """Managed ``__aenter__`` exposes a ready ``grpc_url`` within ``connect_timeout_s``."""
    settings = managed_settings()
    bus, _ = _bus_with_recorder()
    start = time.monotonic()
    async with OpenClaudeProcess(settings, bus, run_id="lifecycle-1") as proc:
        assert proc.grpc_url  # resolved, concrete free port
        assert (time.monotonic() - start) <= settings.connect_timeout_s


async def test_connected_and_disconnected_emitted_exactly_once() -> None:
    """Exactly one connected on entry and exactly one disconnected on exit (C6)."""
    bus, recorder = _bus_with_recorder()
    async with OpenClaudeProcess(managed_settings(), bus, run_id="lifecycle-2"):
        assert len(recorder.of(OpenClaudeConnected)) == 1
        assert recorder.of(OpenClaudeDisconnected) == []
    assert len(recorder.of(OpenClaudeDisconnected)) == 1


async def test_no_process_survives_context() -> None:
    """The managed subprocess is terminated on exit; none survives the context."""
    bus, _ = _bus_with_recorder()
    proc = OpenClaudeProcess(managed_settings(), bus, run_id="lifecycle-3")
    async with proc:
        child = proc._process  # noqa: SLF001 - inspecting the live subprocess
        assert child is not None
        assert child.returncode is None  # running inside the block
    # After __aexit__ the child must have exited (SIGTERM, then SIGKILL on grace).
    assert child.returncode is not None
