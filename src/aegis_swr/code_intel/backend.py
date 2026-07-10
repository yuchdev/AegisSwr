"""Backend-agnostic Code Intelligence contract.

Defines the abstract :class:`CodeIntelBackend` (a single free-text delegation
surface) and the immutable :class:`CodeResult` it returns. This module is
deliberately minimal — there is no multi-tool selection loop on the Aegis SWR
side (Milestone 0004 supersedes the bespoke tool-per-capability design).

The name is deliberately **not** ``CodeBackend``: that name already belongs to
the unrelated VCS/git-history backend in
:mod:`aegis_swr.backends.base`, which the :class:`~aegis_swr.core.orchestrator.Orchestrator`
consumes for commit-window correlation. This contract is the code-*navigation*
surface OpenClaude implements; keeping the names distinct removes the
import-confusion hazard flagged during milestone decomposition.

Isolation (C3): this module imports **neither** ``aegis_swr.openclaude``
**nor** ``grpc``. A concrete backend is injected via constructor at the
:mod:`aegis_swr.openclaude.composition` factory; the scaffolding never imports
its implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CodeTaskContext:
    """Per-invocation context threaded from the caller down to the backend.

    :ivar run_id: Investigation run identifier, propagated onto every EventBus
        emission the backend makes.
    :ivar dry_run: When ``True``, the backend must short-circuit every external
        call (no gRPC connection) and return a zero-token ``[dry-run]`` result
        (C5). The composition path still constructs and registers the backend so
        it is exercised; only the outbound call is suppressed.
    """

    run_id: UUID
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class CodeResult:
    """Immutable result of one delegated code-intelligence task.

    Kept intentionally small (C5 boundary accounting only — Aegis SWR cannot
    observe OpenClaude's internal per-step token usage).

    :ivar content: The concatenated text answer (already truncated to the
        backend's ``max_response_tokens`` cap, if applicable).
    :ivar token_estimate: Boundary token estimate for the call
        (``max(1, len(content) // 4)`` for a real call; ``0`` for a dry-run or
        an unavailable-capability result).
    :ivar available: ``False`` when no backend was registered and the capability
        is simply unavailable (no exception is raised in that case, C4).
    :ivar truncated: ``True`` when ``content`` was clipped at the response cap.
    :ivar metadata: Small free-form observability map (e.g. stream-frame counts,
        ``dry_run`` marker). Never carries raw incident payload text.
    """

    content: str
    token_estimate: int
    available: bool = True
    truncated: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)


class CodeIntelBackend(ABC):
    """Abstract single-surface code-intelligence backend.

    A backend accepts one open-ended natural-language task string and returns a
    single :class:`CodeResult`. There is exactly one concrete implementation in
    this milestone — ``aegis_swr.openclaude.tool.OpenClaudeTool`` — injected at
    the :mod:`aegis_swr.openclaude.composition` factory; this contract never
    imports it (C3).
    """

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line human-readable description of the backend's capability."""
        ...

    @abstractmethod
    async def delegate(self, task: str, ctx: CodeTaskContext) -> CodeResult:
        """Delegate *task* to the backend and return its text result.

        Implementations must not raise for expected failure modes (budget
        exhaustion, permission denial, gRPC ``UNAVAILABLE``); they return a
        ``CodeResult`` whose ``metadata`` records the failure. ``ctx.dry_run``
        must short-circuit any external call to a zero-token ``[dry-run]``
        result (C5).

        :param task: The open-ended code-navigation task string.
        :param ctx: Per-invocation :class:`CodeTaskContext`.
        :return: A :class:`CodeResult`.
        """
        ...
