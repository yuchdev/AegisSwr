"""Shared fixtures for the OpenClaude unit test suite (Task 07.0/01).

Provides the injection seams that let every unit test run with
``OPENCLAUDE_GRPC_URL`` unset and no OpenClaude binary on ``PATH``:
no real gRPC channel, no Node.js subprocess, and no protobuf message
is ever constructed here.

This file covers the following fixtures (spec 07.0/01):

- ``mock_grpc_client`` — factory: sequence of frames → ``AsyncMock``
  ``OpenClaudeGrpcClient`` with an async-generator ``query()``.
- ``mock_event_bus`` — real :class:`EventBus` with a ``captured``
  list that collects every published :class:`DomainEvent`.
- ``settings_no_grpc`` / ``settings_with_grpc`` — preset
  :class:`OpenClaudeSettings` for the unavailable / available cases.
- ``ample_budget`` — a :class:`CallBudget` that never exhausts.
- ``dry_run_ctx`` / ``live_ctx`` — :class:`CodeTaskContext` for the
  dry-run short-circuit and the normal execution path.

Constraints (C3):
  This file does **not** write ``import grpc`` or import any
  ``openclaude_pb2*`` module.  It may import :class:`OpenClaudeGrpcClient`
  (which uses gRPC internally) because gRPC is a project dependency and
  the mock never invokes a real channel.
"""

from __future__ import annotations

from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from aegis_swr.code_intel.backend import CodeTaskContext
from aegis_swr.code_intel.budget import CallBudget
from aegis_swr.core.events import DomainEvent, EventBus
from aegis_swr.openclaude.config import OpenClaudeSettings
from aegis_swr.openclaude.grpc.client import OpenClaudeGrpcClient

# --------------------------------------------------------------------------- #
# gRPC client seam
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_grpc_client() -> Callable[..., OpenClaudeGrpcClient]:
    """Return a factory that builds an ``AsyncMock`` ``OpenClaudeGrpcClient``.

    The factory accepts a list of frame objects (typically
    :class:`~aegis_swr.openclaude.grpc.client.AgentFrame` instances) and
    configures ``client.query()`` to return an async generator that yields
    them in order.  ``health_check`` and ``close`` are plain
    :class:`~unittest.mock.AsyncMock` instances that callers can further
    configure.  No protobuf message is ever constructed.

    Optional keyword arguments let a test script side-effects:

    - ``query_raises`` — an exception ``query()`` raises instead of
      yielding (used for the ``UNAVAILABLE``/``DEADLINE_EXCEEDED`` paths).
    - ``health_result`` — the bool ``health_check()`` returns (default
      ``True``).

    :return: A callable ``(frames, *, query_raises, health_result)
        → OpenClaudeGrpcClient``.
    """

    def _build(
        frames: list[Any],
        *,
        query_raises: Optional[BaseException] = None,
        health_result: bool = True,
    ) -> OpenClaudeGrpcClient:
        """Build and return the configured mock client.

        :param frames: Sequence of frame objects the async generator yields.
        :param query_raises: When not ``None``, ``query()`` raises this
            exception on the first iteration rather than yielding frames.
        :param health_result: Return value for ``health_check()``; defaults
            to ``True`` (healthy sidecar).
        :return: Configured mock implementing the
            :class:`OpenClaudeGrpcClient` interface.
        """
        client = AsyncMock(spec=OpenClaudeGrpcClient)

        async def _agen(*_args: Any, **_kwargs: Any) -> Any:
            """Async generator yielding scripted frames or raising on first call."""
            if query_raises is not None:
                raise query_raises
            for frame in frames:
                yield frame

        # ``query()`` is a sync method returning an async iterator in the
        # real client; model that exactly so ``async for frame in
        # client.query(...)`` works as the tool expects.
        client.query = MagicMock(side_effect=lambda *a, **k: _agen(*a, **k))
        client.health_check = AsyncMock(return_value=health_result)
        client.close = AsyncMock()
        return client  # type: ignore[return-value]

    return _build


# --------------------------------------------------------------------------- #
# EventBus seam
# --------------------------------------------------------------------------- #


@pytest.fixture
def mock_event_bus() -> EventBus:
    """Return a real :class:`EventBus` with a list-collecting subscriber.

    Emitted events are captured on ``bus.captured`` (a plain :class:`list`)
    so tests can assert on type, ordering, count, and payload fields without
    mocking the bus itself.  Mirrors the Milestone 0003 ``capturing_bus``
    convention.

    :return: A real :class:`EventBus` whose ``captured`` attribute holds every
        event published since fixture creation, in emission order.
    """
    bus = EventBus()
    captured: list[DomainEvent] = []
    bus.subscribe(DomainEvent, captured.append)
    bus.captured = captured  # type: ignore[attr-defined]
    return bus


# --------------------------------------------------------------------------- #
# Settings seams
# --------------------------------------------------------------------------- #


@pytest.fixture
def settings_no_grpc() -> OpenClaudeSettings:
    """Return :class:`OpenClaudeSettings` with ``grpc_url=None``.

    Models the deployment where the OpenClaude backend is not registered:
    ``grpc_url`` is ``None`` and the capability is reported as unavailable
    (C4).

    :return: Settings with no gRPC endpoint configured.
    """
    return OpenClaudeSettings(grpc_url=None)


@pytest.fixture
def settings_with_grpc() -> OpenClaudeSettings:
    """Return :class:`OpenClaudeSettings` with a valid ``host:port``.

    Models the deployment where the OpenClaude sidecar is registered:
    ``grpc_url`` is set and the capability is available.  Does not start
    any real process.

    :return: Settings pointing at a loopback endpoint.
    """
    return OpenClaudeSettings(grpc_url="localhost:50051")


# --------------------------------------------------------------------------- #
# Budget seam
# --------------------------------------------------------------------------- #


@pytest.fixture
def ample_budget() -> CallBudget:
    """Return a :class:`CallBudget` large enough to never exhaust in a unit test.

    Used by the happy-path and truncation tests where the pre-check must
    pass.  Budget-exhaustion tests construct their own near-zero
    :class:`CallBudget` inline.

    :return: A budget with ``max_tokens=10_000_000``.
    """
    return CallBudget(max_tokens=10_000_000)


# --------------------------------------------------------------------------- #
# Tool context seams
# --------------------------------------------------------------------------- #


@pytest.fixture
def dry_run_ctx() -> CodeTaskContext:
    """Return a :class:`CodeTaskContext` with ``dry_run=True``.

    Used for the dry-run short-circuit branch: ``delegate()`` must return
    ``[dry-run]`` with zero tokens and make no gRPC calls (C5/C9).

    :return: A context with ``dry_run=True`` and a fresh ``UUID`` run id.
    """
    return CodeTaskContext(run_id=uuid4(), dry_run=True)


@pytest.fixture
def live_ctx() -> CodeTaskContext:
    """Return a :class:`CodeTaskContext` with ``dry_run=False``.

    Used for all normal-execution branches where a real gRPC call is
    expected.

    :return: A context with ``dry_run=False`` and a fresh ``UUID`` run id.
    """
    return CodeTaskContext(run_id=uuid4(), dry_run=False)
