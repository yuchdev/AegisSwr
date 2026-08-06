"""Unit tests for the OpenClaude composition factory.

Exercise :func:`aegis_swr.openclaude.composition.build_code_agent` across the
three composition paths — no ``grpc_url`` (capability unavailable, C4),
``grpc_url`` set with ``dry_run`` (backend registered, process **not** entered,
no gRPC connection), and ``grpc_url`` set without dry-run (process entered,
health check runs, connected/disconnected emitted) — with zero live processes
or real gRPC channels. The OpenClaude gRPC client is replaced by a fake injected
into the ``composition`` module so ``build_code_agent`` never opens a socket.

This is the relocated home of the former ``tests/unit/test_app.py`` factory
coverage; the composition factory moved out of the orphan ``aegis_swr.app``
module into :mod:`aegis_swr.openclaude.composition`, and its operator-facing
smoke test is now the ``aegis code-intel check`` CLI command (see
``tests/unit/test_cli_code_intel.py``).
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Optional
from uuid import uuid4

import pytest

import aegis_swr.openclaude.composition as composition_mod
from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.composition import build_code_agent
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected

_GRPC_URL = "localhost:50051"


class _FakeClient:
    """Fake :class:`OpenClaudeGrpcClient` recording health/query usage.

    Constructed from ``settings`` exactly like the real client so it can be
    swapped in via ``monkeypatch.setattr(composition_mod, "OpenClaudeGrpcClient",
    ...)``. ``health_check`` is the only external seam the process touches in
    external mode; ``query`` must never be called by these tests.
    """

    instances: list[_FakeClient] = []

    def __init__(self, settings: OpenClaudeSettings):
        """Helper that provides init for the composition tests."""
        self.settings = settings
        self.health_calls = 0
        self.query_calls = 0
        _FakeClient.instances.append(self)

    async def health_check(self) -> bool:
        """Helper that provides health check for the composition tests."""
        self.health_calls += 1
        return True

    async def query(self, *args: object, **kwargs: object):  # pragma: no cover
        """Helper that provides query for the composition tests."""
        self.query_calls += 1
        raise AssertionError("query() must not be called in these unit tests")


class _Capture:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self):
        """Helper that provides init for the composition tests."""
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent):
        """Helper that provides call for the composition tests."""
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        """Helper that provides of for the composition tests."""
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_capture() -> tuple[EventBus, _Capture]:
    """Helper that provides bus with capture for the composition tests."""
    bus = EventBus()
    capture = _Capture()
    bus.subscribe(DomainEvent, capture)
    return bus, capture


@pytest.fixture(autouse=True)
def _reset_fake_instances():
    """Helper that provides reset fake instances for the composition tests."""
    _FakeClient.instances.clear()


@pytest.fixture
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Swap the real gRPC client for the fake inside the ``composition`` module."""
    monkeypatch.setattr(composition_mod, "OpenClaudeGrpcClient", _FakeClient)
    return _FakeClient


def _settings(*, grpc_url: Optional[str]) -> OpenClaudeSettings:
    """Helper that provides settings for the composition tests."""
    return OpenClaudeSettings(grpc_url=grpc_url, auto_start=False)


# --------------------------------------------------------------------------- #
# build_code_agent - no grpc_url (capability unavailable, C4)
# --------------------------------------------------------------------------- #
async def test_no_grpc_url_returns_backendless_agent(_fake_client: type[_FakeClient]):
    """[Unit] composition: With ``grpc_url`` unset, no backend is registered (C4).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: with ``grpc_url`` unset, no backend is registered (C4).
    """
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=None), bus, stack, run_id="r")
    assert isinstance(agent, CodeAgent)
    assert agent.available is False
    assert _FakeClient.instances == []
    assert capture.of(OpenClaudeConnected) == []


async def test_no_grpc_url_investigate_reports_unavailable(_fake_client: type[_FakeClient]):
    """[Unit] composition: The backend-less agent returns a non-raising unavailable result.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the backend-less agent returns a non-raising unavailable result.
    """
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=None), bus, stack, run_id="r")
        result = await agent.investigate("find the fault", uuid4())
    assert result.available is False
    assert result.token_estimate == 0


# --------------------------------------------------------------------------- #
# build_code_agent - grpc_url set + dry_run (registered, not entered)
# --------------------------------------------------------------------------- #
async def test_dry_run_registers_backend_without_connecting(_fake_client: type[_FakeClient]):
    """[Unit] composition: Dry-run builds the graph, registers the backend, and never connects.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: dry-run builds the graph, registers the backend, and never connects.
    """
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=True)
        assert agent.available is True
        # A client was constructed, but never health-checked (no process entry).
        assert len(_FakeClient.instances) == 1
        assert _FakeClient.instances[0].health_calls == 0
        assert _FakeClient.instances[0].query_calls == 0
    # No lifecycle events fire when __aenter__ is skipped (C6: zero entries).
    assert capture.of(OpenClaudeConnected) == []
    assert capture.of(OpenClaudeDisconnected) == []


async def test_dry_run_delegate_short_circuits(_fake_client: type[_FakeClient]):
    """[Unit] composition: A delegated task under dry-run returns ``[dry-run]`` with zero tokens.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a delegated task under dry-run returns ``[dry-run]`` with zero tokens.
    """
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=True)
        result = await agent.investigate("trace the segfault", uuid4(), dry_run=True)
    assert result.content.startswith("[dry-run]")
    assert result.token_estimate == 0
    assert _FakeClient.instances[0].query_calls == 0


# --------------------------------------------------------------------------- #
# build_code_agent - grpc_url set, normal run (process entered)
# --------------------------------------------------------------------------- #
async def test_normal_run_enters_process_and_health_checks(_fake_client: type[_FakeClient]):
    """[Unit] composition: A non-dry-run entry health-checks the sidecar and emits connected/disconnected.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a non-dry-run entry health-checks the sidecar and emits connected/disconnected.
    """
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=False)
        assert agent.available is True
        assert _FakeClient.instances[0].health_calls == 1
        assert capture.of(OpenClaudeConnected) != []
    # Leaving the stack triggers the process __aexit__ -> disconnected (C6/RAII).
    assert capture.of(OpenClaudeDisconnected) != []
