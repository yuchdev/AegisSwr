"""Unit tests for the :mod:`aegis_swr.code_intel.agent` entry point.

Exercise both :class:`CodeAgent` paths with zero real processes or gRPC
channels: the no-backend unavailable branch (C4) and the delegation branch
against an async-mock :class:`CodeIntelBackend`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from aegis_swr.code_intel.agent import CodeAgent
from aegis_swr.code_intel.backend import CodeResult, CodeTaskContext


def test_agent_without_backend_is_unavailable() -> None:
    """``available`` is ``False`` when constructed with no backend."""
    agent = CodeAgent(backend=None)
    assert agent.available is False


@pytest.mark.asyncio
async def test_investigate_without_backend_returns_unavailable_result() -> None:
    """The no-backend path returns a non-raising unavailable ``CodeResult``."""
    agent = CodeAgent(backend=None)
    result = await agent.investigate(
        "find the null deref",
        uuid4(),
    )
    assert result.available is False
    assert result.token_estimate == 0
    assert result.content == "[code-intelligence unavailable]"
    assert result.metadata == {"reason": "no_backend_registered"}


def test_agent_with_backend_is_available() -> None:
    """``available`` is ``True`` when a backend is registered."""
    agent = CodeAgent(backend=AsyncMock())
    assert agent.available is True


@pytest.mark.asyncio
async def test_investigate_delegates_to_backend() -> None:
    """The backend path builds a ``CodeTaskContext`` and returns the backend result."""
    expected = CodeResult(content="stack analysed", token_estimate=4)
    backend = AsyncMock()
    backend.delegate.return_value = expected

    agent = CodeAgent(backend=backend)
    run_id = uuid4()
    result = await agent.investigate(
        "trace the fault",
        run_id,
        dry_run=True,
    )

    assert result is expected
    backend.delegate.assert_awaited_once()
    (task_arg, ctx_arg), _kwargs = backend.delegate.call_args
    assert task_arg == "trace the fault"
    assert isinstance(ctx_arg, CodeTaskContext)
    assert ctx_arg.run_id == run_id
    assert ctx_arg.dry_run is True
