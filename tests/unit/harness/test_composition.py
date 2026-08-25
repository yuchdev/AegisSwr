"""Unit tests for the neutral harness composition factory (Task 10.0, C4).

Exercise :func:`aegis_swr.harness.composition.build_code_agent` across the full
C2 selection matrix - no backend (capability unavailable), single-signal
auto-select (including the ``OPENCLAUDE_GRPC_URL``-only 0004 backward-compat
guarantee), explicit-selector-with-absent-signal (``HarnessUnavailableError``),
and the ``dry_run`` orthogonality axis - for all three backend families, with
zero live processes, sidecars, sockets, or Docker. Each backend's external seam
is replaced by a fake injected into the ``composition`` module so no real
resource is ever opened.

This is the relocated, generalised home of the former
``tests/unit/openclaude/test_composition.py`` (0004) factory coverage: the OpenClaude
assembly moved verbatim into ``harness/composition.py`` and its selection surface
is now the C2 truth table, exercised here.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Optional
from uuid import uuid4

import pytest

import aegis_swr.harness.composition as composition_mod
from aegis_swr.claude_code.config import ClaudeCodeSettings
from aegis_swr.claude_code.tool import ClaudeCodeTool
from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.harness.composition import build_code_agent
from aegis_swr.harness.config import HarnessBackend, HarnessSettings
from aegis_swr.harness.exceptions import HarnessUnavailableError
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected
from aegis_swr.openclaude.tool import OpenClaudeTool
from aegis_swr.openhands.config import OpenHandsSettings
from aegis_swr.openhands.tool import OpenHandsTool

_GRPC_URL = "localhost:50051"
_SERVER_URL = "http://localhost:3000"


class _FakeOpenClaudeClient:
    """Fake ``OpenClaudeGrpcClient`` recording health-check usage (no socket)."""

    instances: list[_FakeOpenClaudeClient] = []

    def __init__(self, settings: OpenClaudeSettings):
        """Record construction from ``settings``; open no gRPC channel."""
        self.settings = settings
        self.health_calls = 0
        _FakeOpenClaudeClient.instances.append(self)

    async def health_check(self) -> bool:
        """Report healthy; the process health-checks this in external mode."""
        self.health_calls += 1
        return True

    async def query(self, *args: object, **kwargs: object):  # pragma: no cover
        """Refuse queries; composition unit tests never delegate."""
        raise AssertionError("query() must not be called in composition unit tests")


class _FakeOpenHandsProcess:
    """Fake ``OpenHandsProcess`` recording enter/exit without a real sidecar."""

    instances: list[_FakeOpenHandsProcess] = []

    def __init__(self, settings: OpenHandsSettings, bus: EventBus, run_id: str, client: Any = None):
        """Record construction; start nothing and open no connection."""
        self.settings = settings
        self.run_id = run_id
        self.entered = False
        self.exited = False
        _FakeOpenHandsProcess.instances.append(self)

    async def __aenter__(self) -> _FakeOpenHandsProcess:
        """Mark the sidecar entered without a real health check."""
        self.entered = True
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any):
        """Mark the sidecar torn down (RAII on stack close)."""
        self.exited = True


class _RecordingStack(AsyncExitStack):
    """AsyncExitStack that records every async context registered on it."""

    def __init__(self):
        """Initialise the base stack and an empty registration log."""
        super().__init__()
        self.entered: list[object] = []

    async def enter_async_context(self, cm: Any) -> Any:
        """Record *cm*, then register it on the base stack (RAII preserved)."""
        self.entered.append(cm)
        return await super().enter_async_context(cm)


class _Capture:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self):
        """Start with an empty event log."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent):
        """Record one published event."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Return every captured event of *event_type*."""
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_capture() -> tuple[EventBus, _Capture]:
    """Build an :class:`EventBus` with a subscriber capturing every event."""
    bus = EventBus()
    capture = _Capture()
    bus.subscribe(DomainEvent, capture)
    return bus, capture


def _harness(
    *,
    backend: Optional[HarnessBackend] = None,
    openclaude: Optional[OpenClaudeSettings] = None,
    claude_code: Optional[ClaudeCodeSettings] = None,
    openhands: Optional[OpenHandsSettings] = None,
) -> HarnessSettings:
    """Compose a :class:`HarnessSettings` from explicit per-family sub-settings."""
    return HarnessSettings(
        backend=backend,
        openclaude=openclaude if openclaude is not None else OpenClaudeSettings(grpc_url=None, auto_start=False),
        claude_code=claude_code if claude_code is not None else ClaudeCodeSettings(enabled=False),
        openhands=openhands if openhands is not None else OpenHandsSettings(server_url=None),
    )


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    """Clear every presence signal / selector and reset fake instance registries."""
    for var in ("AEGIS_CODE_INTEL_BACKEND", "OPENCLAUDE_GRPC_URL", "CLAUDE_CODE_ENABLED", "OPENHANDS_SERVER_URL"):
        monkeypatch.delenv(var, raising=False)
    _FakeOpenClaudeClient.instances.clear()
    _FakeOpenHandsProcess.instances.clear()


@pytest.fixture
def _fake_openclaude(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOpenClaudeClient]:
    """Swap the real gRPC client for the fake inside the ``composition`` module."""
    monkeypatch.setattr(composition_mod, "OpenClaudeGrpcClient", _FakeOpenClaudeClient)
    return _FakeOpenClaudeClient


@pytest.fixture
def _fake_openhands(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOpenHandsProcess]:
    """Swap the real sidecar process for the fake inside the ``composition`` module."""
    monkeypatch.setattr(composition_mod, "OpenHandsProcess", _FakeOpenHandsProcess)
    return _FakeOpenHandsProcess


# --------------------------------------------------------------------------- #
# C2 row 1: no selector + zero signals -> capability unavailable (no raise)
# --------------------------------------------------------------------------- #
async def test_no_backend_returns_backendless_agent(_fake_openclaude: type[_FakeOpenClaudeClient]):
    """[Unit] harness composition: zero signals yield a backend-less CodeAgent, no raise (C2 row 1).

    Scenario: a harness with no selector and no presence signals is composed.

    Boundaries: scoped to the composition factory's ``None`` branch.

    On failure, first check: zero signals yield a backend-less CodeAgent with no raise.
    """
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_harness(), bus, stack, run_id="r")
    assert isinstance(agent, CodeAgent)
    assert agent.available is False
    assert _FakeOpenClaudeClient.instances == []
    assert capture.of(OpenClaudeConnected) == []


async def test_no_backend_investigate_reports_unavailable():
    """[Unit] harness composition: the backend-less agent returns a non-raising unavailable result.

    Scenario: a backend-less agent is asked to investigate a task.

    Boundaries: scoped to :class:`CodeAgent` unavailable behaviour.

    On failure, first check: the result is unavailable with a zero token estimate and no raise.
    """
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_harness(), bus, stack, run_id="r")
        result = await agent.investigate("find the fault", uuid4())
    assert result.available is False
    assert result.token_estimate == 0


# --------------------------------------------------------------------------- #
# C2 auto-select: exactly one presence signal -> that family
# --------------------------------------------------------------------------- #
async def test_openclaude_grpc_url_only_auto_selects(_fake_openclaude: type[_FakeOpenClaudeClient]):
    """[Unit] harness composition: OPENCLAUDE_GRPC_URL-only env auto-selects OpenClaude (0004 guarantee).

    Scenario: only ``OPENCLAUDE_GRPC_URL`` is set and ``HarnessSettings()`` resolves from env.

    Boundaries: exercises the C2 single-signal auto-select and env sourcing.

    On failure, first check: ``active_backend`` is ``openclaude`` and the backend registers.
    """
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    try:
        harness = HarnessSettings()
    finally:
        monkeypatch.undo()
    assert harness.active_backend == "openclaude"
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=True)
    assert agent.available is True
    assert isinstance(_backend_of(agent), OpenClaudeTool)


async def test_claude_code_enabled_only_auto_selects(tmp_path: Any):
    """[Unit] harness composition: an enabled Claude Code backend auto-selects and registers (C2).

    Scenario: only Claude Code's ``enabled`` presence signal is set.

    Boundaries: scoped to the ``claude_code`` composition branch.

    On failure, first check: the agent is available and wired to a ClaudeCodeTool.
    """
    harness = _harness(claude_code=ClaudeCodeSettings(enabled=True, scratch_cwd=tmp_path))
    assert harness.active_backend == "claude_code"
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=True)
    assert agent.available is True
    assert isinstance(_backend_of(agent), ClaudeCodeTool)


async def test_openhands_server_url_only_auto_selects(_fake_openhands: type[_FakeOpenHandsProcess]):
    """[Unit] harness composition: an OpenHands server_url auto-selects and registers (C2).

    Scenario: only OpenHands' ``server_url`` presence signal is set.

    Boundaries: scoped to the ``openhands`` composition branch.

    On failure, first check: the agent is available and wired to an OpenHandsTool.
    """
    harness = _harness(openhands=OpenHandsSettings(server_url=_SERVER_URL))
    assert harness.active_backend == "openhands"
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=True)
    assert agent.available is True
    assert isinstance(_backend_of(agent), OpenHandsTool)


# --------------------------------------------------------------------------- #
# dry_run orthogonality: registered, but no sidecar entered / no outbound call
# --------------------------------------------------------------------------- #
async def test_openclaude_dry_run_registers_without_connecting(_fake_openclaude: type[_FakeOpenClaudeClient]):
    """[Unit] harness composition: OpenClaude dry-run builds the graph and never connects (C4/C13).

    Scenario: OpenClaude is active and composed under ``dry_run=True``.

    Boundaries: scoped to the OpenClaude dry-run assembly path.

    On failure, first check: a client is built but never health-checked and no process is entered.
    """
    harness = _harness(openclaude=OpenClaudeSettings(grpc_url=_GRPC_URL, auto_start=False))
    bus, capture = _bus_with_capture()
    async with _RecordingStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=True)
        assert agent.available is True
        assert len(_FakeOpenClaudeClient.instances) == 1
        assert _FakeOpenClaudeClient.instances[0].health_calls == 0
        assert stack.entered == []
    assert capture.of(OpenClaudeConnected) == []
    assert capture.of(OpenClaudeDisconnected) == []


async def test_openclaude_normal_run_enters_and_health_checks(_fake_openclaude: type[_FakeOpenClaudeClient]):
    """[Unit] harness composition: a non-dry-run OpenClaude entry health-checks and tears down (C6).

    Scenario: OpenClaude is active and composed under ``dry_run=False``.

    Boundaries: scoped to the OpenClaude sidecar lifecycle via the injected fake client.

    On failure, first check: the process is registered, health-checked, and disconnected on exit.
    """
    harness = _harness(openclaude=OpenClaudeSettings(grpc_url=_GRPC_URL, auto_start=False))
    bus, capture = _bus_with_capture()
    async with _RecordingStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=False)
        assert agent.available is True
        assert _FakeOpenClaudeClient.instances[0].health_calls == 1
        assert len(stack.entered) == 1
        assert capture.of(OpenClaudeConnected) != []
    assert capture.of(OpenClaudeDisconnected) != []


async def test_openhands_dry_run_registers_without_entering(_fake_openhands: type[_FakeOpenHandsProcess]):
    """[Unit] harness composition: OpenHands dry-run registers the tool but enters no sidecar (C4/C13).

    Scenario: OpenHands is active and composed under ``dry_run=True``.

    Boundaries: scoped to the OpenHands dry-run assembly path.

    On failure, first check: the process is constructed but never entered and nothing is on the stack.
    """
    harness = _harness(openhands=OpenHandsSettings(server_url=_SERVER_URL))
    bus, _ = _bus_with_capture()
    async with _RecordingStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=True)
        assert agent.available is True
        assert len(_FakeOpenHandsProcess.instances) == 1
        assert _FakeOpenHandsProcess.instances[0].entered is False
        assert stack.entered == []


async def test_openhands_normal_run_registers_and_tears_down(_fake_openhands: type[_FakeOpenHandsProcess]):
    """[Unit] harness composition: a non-dry-run OpenHands entry registers the sidecar and tears it down (C8).

    Scenario: OpenHands is active and composed under ``dry_run=False``.

    Boundaries: scoped to the OpenHands sidecar registration on the AsyncExitStack.

    On failure, first check: the process is entered, registered on the stack, and exited on stack close.
    """
    harness = _harness(openhands=OpenHandsSettings(server_url=_SERVER_URL))
    bus, _ = _bus_with_capture()
    async with _RecordingStack() as stack:
        agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=False)
        assert agent.available is True
        process = _FakeOpenHandsProcess.instances[0]
        assert process.entered is True
        assert stack.entered == [process]
        assert process.exited is False
    assert process.exited is True


async def test_claude_code_registers_no_sidecar(tmp_path: Any):
    """[Unit] harness composition: Claude Code registers nothing on the AsyncExitStack (C6).

    Scenario: an enabled Claude Code backend is composed under both dry-run settings.

    Boundaries: scoped to the ``claude_code`` no-sidecar assembly path.

    On failure, first check: no async context is ever registered on the stack.
    """
    harness = _harness(claude_code=ClaudeCodeSettings(enabled=True, scratch_cwd=tmp_path))
    bus, _ = _bus_with_capture()
    for dry_run in (True, False):
        async with _RecordingStack() as stack:
            agent = await build_code_agent(harness, bus, stack, run_id="r", dry_run=dry_run)
            assert agent.available is True
            assert stack.entered == []


# --------------------------------------------------------------------------- #
# C2 last row: explicit selector + absent signal -> HarnessUnavailableError
# --------------------------------------------------------------------------- #
async def test_explicit_openclaude_without_signal_raises():
    """[Unit] harness composition: selecting OpenClaude with no grpc_url raises unavailable (C2 last row).

    Scenario: ``backend=openclaude`` is explicit but the grpc_url signal is absent.

    Boundaries: scoped to the OpenClaude presence-signal guard.

    On failure, first check: composition raises HarnessUnavailableError for the selected backend.
    """
    harness = _harness(backend=HarnessBackend.OPENCLAUDE)
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        with pytest.raises(HarnessUnavailableError) as excinfo:
            await build_code_agent(harness, bus, stack, run_id="r")
    assert excinfo.value.backend == "openclaude"


async def test_explicit_claude_code_without_signal_raises():
    """[Unit] harness composition: selecting Claude Code while disabled raises unavailable (C2 last row).

    Scenario: ``backend=claude_code`` is explicit but ``enabled`` is False.

    Boundaries: scoped to the Claude Code presence-signal guard.

    On failure, first check: composition raises HarnessUnavailableError for the selected backend.
    """
    harness = _harness(backend=HarnessBackend.CLAUDE_CODE)
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        with pytest.raises(HarnessUnavailableError) as excinfo:
            await build_code_agent(harness, bus, stack, run_id="r")
    assert excinfo.value.backend == "claude_code"


async def test_explicit_openhands_without_signal_raises():
    """[Unit] harness composition: selecting OpenHands with no server_url raises unavailable (C2 last row).

    Scenario: ``backend=openhands`` is explicit but ``server_url`` is absent.

    Boundaries: scoped to the OpenHands presence-signal guard.

    On failure, first check: composition raises HarnessUnavailableError for the selected backend.
    """
    harness = _harness(backend=HarnessBackend.OPENHANDS)
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        with pytest.raises(HarnessUnavailableError) as excinfo:
            await build_code_agent(harness, bus, stack, run_id="r")
    assert excinfo.value.backend == "openhands"


class _UnknownHarness:
    """Duck-typed harness whose resolved backend name is outside the closed set."""

    active_backend = "bogus"
    presence_signals = frozenset()


async def test_unknown_backend_name_raises_unavailable():
    """[Unit] harness composition: an unresolvable backend name fails loud, not silently (defensive).

    Scenario: a harness reports an ``active_backend`` outside the closed family set.

    Boundaries: scoped to the composition factory's defensive fall-through.

    On failure, first check: composition raises HarnessUnavailableError rather than returning agent.
    """
    harness: Any = _UnknownHarness()
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        with pytest.raises(HarnessUnavailableError) as excinfo:
            await build_code_agent(harness, bus, stack, run_id="r")
    assert excinfo.value.backend == "bogus"


def _backend_of(agent: CodeAgent) -> Any:
    """Return the private backend an agent was wired with (test-only introspection)."""
    return agent._backend
