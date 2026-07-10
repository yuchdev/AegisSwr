"""Unit tests for the :mod:`aegis_swr.app` composition root.

Exercise :func:`aegis_swr.app.build_code_agent` and the runnable ``main`` entry
point across the three composition paths — no ``grpc_url`` (capability
unavailable), ``grpc_url`` set with ``--dry-run`` (backend registered, process
**not** entered, no gRPC connection), and ``grpc_url`` set without dry-run
(process entered, health check runs) — with zero live processes or real gRPC
channels. The OpenClaude gRPC client is replaced by a fake injected into the
``app`` module so ``build_code_agent`` never opens a socket.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Optional
from uuid import uuid4

import pytest

import aegis_swr.app as app_mod
from aegis_swr.app import build_code_agent, main
from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.events import OpenClaudeConnected, OpenClaudeDisconnected

_GRPC_URL = "localhost:50051"


class _FakeClient:
    """Fake :class:`OpenClaudeGrpcClient` recording health/query usage.

    Constructed from ``settings`` exactly like the real client so it can be
    swapped in via ``monkeypatch.setattr(app_mod, "OpenClaudeGrpcClient", ...)``.
    ``health_check`` is the only external seam the process touches in external
    mode; ``query`` must never be called by these tests.
    """

    instances: list[_FakeClient] = []

    def __init__(self, settings: OpenClaudeSettings) -> None:
        self.settings = settings
        self.health_calls = 0
        self.query_calls = 0
        _FakeClient.instances.append(self)

    async def health_check(self) -> bool:
        self.health_calls += 1
        return True

    async def query(self, *args: object, **kwargs: object) -> None:  # pragma: no cover
        self.query_calls += 1
        raise AssertionError("query() must not be called in these unit tests")


class _Capture:
    """Capturing :class:`DomainEvent` subscriber."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)

    def of(self, event_type: type) -> list[DomainEvent]:
        return [e for e in self.events if isinstance(e, event_type)]


def _bus_with_capture() -> tuple[EventBus, _Capture]:
    bus = EventBus()
    capture = _Capture()
    bus.subscribe(DomainEvent, capture)
    return bus, capture


@pytest.fixture(autouse=True)
def _reset_fake_instances() -> None:
    _FakeClient.instances.clear()


@pytest.fixture
def _fake_client(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    """Swap the real gRPC client for the fake inside the ``app`` module."""
    monkeypatch.setattr(app_mod, "OpenClaudeGrpcClient", _FakeClient)
    return _FakeClient


def _settings(*, grpc_url: Optional[str]) -> OpenClaudeSettings:
    return OpenClaudeSettings(grpc_url=grpc_url, auto_start=False)


# --------------------------------------------------------------------------- #
# build_code_agent - no grpc_url (capability unavailable, C4)
# --------------------------------------------------------------------------- #
async def test_no_grpc_url_returns_backendless_agent(_fake_client: type[_FakeClient]) -> None:
    """With ``grpc_url`` unset, no backend is registered (C4)."""
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=None), bus, stack, run_id="r")
    assert isinstance(agent, CodeAgent)
    assert agent.available is False
    assert _FakeClient.instances == []
    assert capture.of(OpenClaudeConnected) == []


async def test_no_grpc_url_investigate_reports_unavailable(_fake_client: type[_FakeClient]) -> None:
    """The backend-less agent returns a non-raising unavailable result."""
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(_settings(grpc_url=None), bus, stack, run_id="r")
        result = await agent.investigate("find the fault", uuid4())
    assert result.available is False
    assert result.token_estimate == 0


# --------------------------------------------------------------------------- #
# build_code_agent - grpc_url set + dry_run (registered, not entered)
# --------------------------------------------------------------------------- #
async def test_dry_run_registers_backend_without_connecting(_fake_client: type[_FakeClient]) -> None:
    """Dry-run builds the graph, registers the backend, and never connects."""
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(
            _settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=True
        )
        assert agent.available is True
        # A client was constructed, but never health-checked (no process entry).
        assert len(_FakeClient.instances) == 1
        assert _FakeClient.instances[0].health_calls == 0
        assert _FakeClient.instances[0].query_calls == 0
    # No lifecycle events fire when __aenter__ is skipped (C6: zero entries).
    assert capture.of(OpenClaudeConnected) == []
    assert capture.of(OpenClaudeDisconnected) == []


async def test_dry_run_delegate_short_circuits(_fake_client: type[_FakeClient]) -> None:
    """A delegated task under dry-run returns ``[dry-run]`` with zero tokens."""
    bus, _ = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(
            _settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=True
        )
        result = await agent.investigate("trace the segfault", uuid4(), dry_run=True)
    assert result.content.startswith("[dry-run]")
    assert result.token_estimate == 0
    assert _FakeClient.instances[0].query_calls == 0


# --------------------------------------------------------------------------- #
# build_code_agent - grpc_url set, normal run (process entered)
# --------------------------------------------------------------------------- #
async def test_normal_run_enters_process_and_health_checks(_fake_client: type[_FakeClient]) -> None:
    """A non-dry-run entry health-checks the sidecar and emits connected/disconnected."""
    bus, capture = _bus_with_capture()
    async with AsyncExitStack() as stack:
        agent = await build_code_agent(
            _settings(grpc_url=_GRPC_URL), bus, stack, run_id="r", dry_run=False
        )
        assert agent.available is True
        assert _FakeClient.instances[0].health_calls == 1
        assert capture.of(OpenClaudeConnected) != []
    # Leaving the stack triggers the process __aexit__ -> disconnected (C6/RAII).
    assert capture.of(OpenClaudeDisconnected) != []


# --------------------------------------------------------------------------- #
# main / _parse_args
# --------------------------------------------------------------------------- #
def test_parse_args_dry_run_flag() -> None:
    """``--dry-run`` sets the dry_run flag; absence defaults to False."""
    assert app_mod._parse_args(["--dry-run"]).dry_run is True
    assert app_mod._parse_args([]).dry_run is False


def test_main_without_grpc_url_exits_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main`` completes with exit 0 when no ``OPENCLAUDE_GRPC_URL`` is set."""
    monkeypatch.delenv("OPENCLAUDE_GRPC_URL", raising=False)
    assert main([]) == 0
    assert main(["--dry-run"]) == 0


def test_main_dry_run_with_grpc_url_does_not_connect(
    monkeypatch: pytest.MonkeyPatch, _fake_client: type[_FakeClient]
) -> None:
    """``main --dry-run`` with the var set registers the backend but never connects."""
    monkeypatch.setenv("OPENCLAUDE_GRPC_URL", _GRPC_URL)
    assert main(["--dry-run"]) == 0
    # A client was built by the composition path, but no RPC/health check ran.
    assert len(_FakeClient.instances) == 1
    assert _FakeClient.instances[0].health_calls == 0
    assert _FakeClient.instances[0].query_calls == 0
