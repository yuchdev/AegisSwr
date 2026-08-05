"""Unit tests for the :mod:`aegis_swr.code_intel.backend` contract.

Cover the immutable :class:`CodeResult`/:class:`CodeTaskContext` value objects
(fields, defaults, frozen + slots invariants), the abstract nature of
:class:`CodeIntelBackend`, and the C3 isolation guarantee that importing the
``code_intel`` package pulls in neither ``grpc`` nor ``aegis_swr.openclaude``.
"""

from __future__ import annotations

import dataclasses
import sys
from uuid import UUID, uuid4

import pytest

from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext


def test_code_task_context_fields_and_default() -> None:
    """[Unit] backend: Constructs with a run_id and defaults ``dry_run`` to ``False``.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: constructs with a run_id and defaults ``dry_run`` to ``False``.
    """
    run_id = uuid4()
    ctx = CodeTaskContext(run_id=run_id)
    assert ctx.run_id == run_id
    assert isinstance(ctx.run_id, UUID)
    assert ctx.dry_run is False

    ctx_dry = CodeTaskContext(run_id=run_id, dry_run=True)
    assert ctx_dry.dry_run is True


def test_code_task_context_is_frozen_and_slotted() -> None:
    """[Unit] backend: ``CodeTaskContext`` rejects mutation and carries no ``__dict__`` (slots).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``CodeTaskContext`` rejects mutation and carries no ``__dict__`` (slots).
    """
    ctx = CodeTaskContext(run_id=uuid4())
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.dry_run = True  # type: ignore[misc]
    assert not hasattr(ctx, "__dict__")


def test_code_result_fields_and_defaults() -> None:
    """[Unit] backend: Constructs with content/token_estimate and documented defaults.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: constructs with content/token_estimate and documented defaults.
    """
    result = CodeResult(content="answer", token_estimate=7)
    assert result.content == "answer"
    assert result.token_estimate == 7
    assert result.available is True
    assert result.truncated is False
    assert result.metadata == {}


def test_code_result_metadata_default_is_independent() -> None:
    """[Unit] backend: The ``metadata`` default_factory yields distinct mappings per instance.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: the ``metadata`` default_factory yields distinct mappings per instance.
    """
    first = CodeResult(content="a", token_estimate=1)
    second = CodeResult(content="b", token_estimate=1)
    assert first.metadata == {}
    assert second.metadata == {}
    assert first.metadata is not second.metadata


def test_code_result_accepts_explicit_fields() -> None:
    """[Unit] backend: All fields, including ``metadata``, may be supplied explicitly.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: all fields, including ``metadata``, may be supplied explicitly.
    """
    result = CodeResult(
        content="[dry-run]",
        token_estimate=0,
        available=False,
        truncated=True,
        metadata={"reason": "no_backend_registered"},
    )
    assert result.available is False
    assert result.truncated is True
    assert result.metadata == {"reason": "no_backend_registered"}


def test_code_result_is_frozen_and_slotted() -> None:
    """[Unit] backend: ``CodeResult`` rejects mutation and carries no ``__dict__`` (slots).

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``CodeResult`` rejects mutation and carries no ``__dict__`` (slots).
    """
    result = CodeResult(content="x", token_estimate=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.content = "y"  # type: ignore[misc]
    assert not hasattr(result, "__dict__")


def test_code_backend_cannot_be_instantiated() -> None:
    """[Unit] backend: ``CodeIntelBackend`` is abstract and cannot be constructed directly.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: ``CodeIntelBackend`` is abstract and cannot be constructed directly.
    """
    with pytest.raises(TypeError):
        CodeIntelBackend()  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_concrete_backend_subclass_works() -> None:
    """[Unit] backend: A trivial concrete subclass implementing the contract is usable.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: a trivial concrete subclass implementing the contract is usable.
    """

    class _StubBackend(CodeIntelBackend):
        """Support type for the backend tests (StubBackend)."""
        @property
        def description(self) -> str:
            """Helper that provides description for the backend tests."""
            return "stub backend"

        async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
            """Helper that provides delegate for the backend tests."""
            return CodeResult(content=f"handled: {task}", token_estimate=1)

    backend = _StubBackend()
    assert backend.description == "stub backend"
    ctx = CodeTaskContext(run_id=uuid4())
    result = await backend.delegate("find symbol", ctx)
    assert result.content == "handled: find symbol"
    assert result.token_estimate == 1


def test_code_intel_import_pulls_no_grpc_or_openclaude() -> None:
    """[Unit] backend: C3 isolation: importing ``code_intel`` loads no gRPC / OpenClaude modules.

    Scenario: the behavior described in the summary is exercised.

    Boundaries: scoped to this test case and its direct collaborators.

    On failure, first check: c3 isolation: importing ``code_intel`` loads no gRPC / OpenClaude modules.
    """
    snapshot = dict(sys.modules)
    try:
        for name in list(sys.modules):
            if name == "grpc" or name.startswith(("grpc.", "aegis_swr.openclaude")):
                del sys.modules[name]

        import importlib

        import aegis_swr.code_intel as pkg

        importlib.reload(pkg)

        offending = [
            name for name in sys.modules if name == "grpc" or name.startswith(("grpc.", "aegis_swr.openclaude"))
        ]
        assert offending == []
    finally:
        sys.modules.clear()
        sys.modules.update(snapshot)
