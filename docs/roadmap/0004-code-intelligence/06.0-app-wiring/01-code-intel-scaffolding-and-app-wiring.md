# 01 - code_intel scaffolding + app.py composition root

**Parent task:** 06.0 App Wiring & agents.yaml
**State:** ⬜ Not started
**Depends on:** none (foundation subtask; consumes Tasks 01.0-05.0 outputs at wiring time)
**Blocks:** 02, 03, 04; downstream Task 07.0 (unit tests target `code_intel/` + `app.py`)

## Objective

Stand up the minimal, backend-agnostic Code Intelligence scaffolding that
Milestone 0004 would otherwise have supplied, then wire OpenClaude into it as
the sole backend at the `app.py` composition root. This subtask creates
`aegis/code_intel/{__init__.py,backend.py,agent.py,budget.py}` — a `CodeBackend`
contract plus `CodeResult`, a `CodeAgent` entry point, and a `CallBudget`
boundary accountant — and updates `app.py` so that **only** when
`settings.openclaude.grpc_url is not None` (contract C4) the OpenClaude stack
(`OpenClaudeGrpcClient` → `OpenClaudeProcess` → `OpenClaudeTool`) is constructed
and injected as the `CodeBackend` into `CodeAgent`. When `grpc_url` is `None`,
`CodeAgent` is constructed with no backend and reports the capability as
unavailable. The scaffolding is deliberately small: no multi-tool selection
loop, no tool registry, no index backends.

## File: `aegis/code_intel/backend.py`

```python
"""Backend-agnostic Code Intelligence contract.

Defines the abstract :class:`CodeBackend` (a single free-text delegation
surface) and the immutable :class:`CodeResult` it returns. This module is
deliberately minimal — there is no multi-tool selection loop on the Aegis SWR
side (Milestone 0004 supersedes the bespoke tool-per-capability design).

Isolation (C3): this module imports **neither** ``aegis.openclaude`` **nor**
``grpc``. A concrete backend is injected via constructor at the ``app.py``
composition root; the scaffolding never imports its implementation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CodeTaskContext:
    """Per-invocation context threaded from the caller down to the backend.

    :ivar run_id: Investigation run identifier, propagated onto every EventBus
        emission the backend makes.
    :ivar dry_run: When ``True``, the backend must short-circuit every external
        call (no gRPC connection) and return a zero-token ``[dry-run]`` result
        (C5). The ``app.py`` composition path still constructs and registers the
        backend so it is exercised; only the outbound call is suppressed.
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


class CodeBackend(ABC):
    """Abstract single-surface code-intelligence backend.

    A backend accepts one open-ended natural-language task string and returns a
    single :class:`CodeResult`. There is exactly one concrete implementation in
    this milestone — ``aegis.openclaude.tool.OpenClaudeTool`` — injected at
    ``app.py``; this contract never imports it (C3).
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
```

## File: `aegis/code_intel/agent.py`

```python
"""Code Intelligence entry point.

:class:`CodeAgent` is the single object the rest of Aegis SWR calls to delegate
a code-navigation task. It holds an *optional* :class:`CodeBackend`: when no
backend is registered (``OPENCLAUDE_GRPC_URL`` unset), the capability is
reported as unavailable without raising (C4).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from loguru import logger

from aegis.code_intel.backend import CodeBackend, CodeResult, CodeTaskContext
from aegis.code_intel.budget import CallBudget


class CodeAgent:
    """Delegates a code task to the registered backend, if any.

    :ivar _backend: The sole registered :class:`CodeBackend`, or ``None`` when
        code intelligence is unavailable in this deployment.
    """

    def __init__(self, backend: Optional[CodeBackend] = None) -> None:
        """Construct the agent.

        :param backend: The code backend to delegate to, or ``None`` to run in
            capability-unavailable mode.
        """
        self._backend = backend

    @property
    def available(self) -> bool:
        """Whether a code-intelligence backend is registered."""
        return self._backend is not None

    async def investigate(
        self,
        task: str,
        run_id: UUID,
        *,
        budget: CallBudget,
        dry_run: bool = False,
    ) -> CodeResult:
        """Delegate *task*, or report unavailability when no backend is set.

        When ``self._backend is None`` this returns a non-raising
        ``CodeResult(available=False, token_estimate=0)`` — there are no sibling
        backends to fall back to (C4).

        :param task: The open-ended code-navigation task string.
        :param run_id: Investigation run identifier.
        :param budget: Boundary :class:`CallBudget` for this single call.
        :param dry_run: Threaded into :class:`CodeTaskContext`; suppresses the
            external call.
        :return: A :class:`CodeResult`.
        """
        if self._backend is None:
            logger.debug("Code intelligence requested but no backend registered")
            return CodeResult(
                content="[code-intelligence unavailable]",
                token_estimate=0,
                available=False,
                metadata={"reason": "no_backend_registered"},
            )
        ctx = CodeTaskContext(run_id=run_id, dry_run=dry_run)
        ...  # delegate via self._backend; budget pre-check/charge lives in the backend (C5)
```

## File: `aegis/code_intel/budget.py`

```python
"""Boundary-level token/cost accounting for a single delegated call (C5).

Aegis SWR cannot see OpenClaude's internal per-step token usage, so accounting
is a two-step boundary estimate: a *pre-check* before the call and a *charge*
after the stream completes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CallBudget:
    """A single-call token budget.

    :ivar max_tokens: Hard ceiling for the call's boundary token estimate.
    :ivar spent: Tokens charged so far (``0`` until :meth:`charge`).
    """

    max_tokens: int
    spent: int = 0

    @property
    def remaining(self) -> int:
        """Tokens still available before the ceiling is reached."""
        return max(0, self.max_tokens - self.spent)

    def can_afford(self, estimate: int) -> bool:
        """Pre-check step (C5.1): whether *estimate* fits under the ceiling.

        Called with ``max_response_tokens // 4`` before opening a connection.

        :param estimate: Conservative pre-call token estimate.
        :return: ``True`` if the estimate fits within :attr:`remaining`.
        """
        ...

    def charge(self, tokens: int) -> None:
        """Post-charge step (C5.2): record *tokens* actually estimated.

        Called after stream completion with ``max(1, len(content) // 4)``.
        Charging is idempotent per call and never raises on overshoot (the cap
        is enforced by the pre-check and by response truncation, not here).

        :param tokens: Boundary token estimate to add to :attr:`spent`.
        """
        ...
```

## File: `aegis/code_intel/__init__.py`

```python
"""Minimal, backend-agnostic Code Intelligence scaffolding.

Exports the public contract only. Contains **zero** imports of
``aegis.openclaude`` or ``grpc`` (C3).
"""
from __future__ import annotations

from aegis.code_intel.agent import CodeAgent
from aegis.code_intel.backend import CodeBackend, CodeResult, CodeTaskContext
from aegis.code_intel.budget import CallBudget

__all__ = [
    "CallBudget",
    "CodeAgent",
    "CodeBackend",
    "CodeResult",
    "CodeTaskContext",
]
```

## File: `aegis/app.py` (composition-root section — updated)

```python
from aegis.code_intel.agent import CodeAgent
from aegis.code_intel.backend import CodeBackend
# OpenClaude imports are confined to app.py (C3/C4) — no other module imports them.
from aegis.openclaude.grpc.client import OpenClaudeGrpcClient
from aegis.openclaude.process import OpenClaudeProcess
from aegis.openclaude.tool import OpenClaudeTool


async def build_code_agent(
    settings: OpenClaudeSettings,
    bus: EventBus,
    stack: AsyncExitStack,
) -> CodeAgent:
    """Construct the :class:`CodeAgent`, wiring OpenClaude when configured.

    The ``grpc_url is not None`` branch lives **only here** (C4). When it is
    ``None`` the agent is built with no backend and the capability is
    unavailable. The started :class:`OpenClaudeProcess` is registered on *stack*
    so its shutdown is tied to application lifetime (RAII).

    :param settings: The composed ``settings.openclaude`` sub-settings.
    :param bus: Shared EventBus for the run.
    :param stack: Application-lifetime ``AsyncExitStack``.
    :return: A configured :class:`CodeAgent`.
    """
    if settings.grpc_url is None:
        return CodeAgent(backend=None)

    process = OpenClaudeProcess(settings, bus)
    await stack.enter_async_context(process)          # health-check / start (C6)
    client = OpenClaudeGrpcClient(process.grpc_url, settings)
    backend: CodeBackend = OpenClaudeTool(client, settings, bus)
    return CodeAgent(backend=backend)
```

## Implementation notes

- Use an **ABC**, not a `Protocol`, for `CodeBackend` — every backend family in
  the codebase (`AIAPIBackend`, `DebugBackend`, `RelationalStore`, `LogBackend`,
  the existing VCS `CodeBackend`) is an `abc.ABC` in `backends/base.py`. Stay
  consistent.
- `CodeResult` is a `frozen=True, slots=True` dataclass — matches the frozen
  dataclass convention used for the OpenClaude event taxonomy (C8).
- The `delegate(task, ctx)` method name follows the authoritative Architecture
  diagram in `plan.md` (`CodeBackend contract: delegate(task) → CodeResult`).
  `OpenClaudeTool` (Task 04.0) implements this method. See the flagged
  discrepancy in the reporting note about Task 04.0's `run()` phrasing.
- `CallBudget` two-step accounting is invoked **inside the backend**
  (`OpenClaudeTool`, Task 04.0 subtask 04): pre-check with
  `max_response_tokens // 4`, charge with `max(1, len(content) // 4)` after
  `DONE`. `CodeAgent` merely owns and passes the budget; it never charges.
- `OpenClaudeProcess` is entered via `AsyncExitStack.enter_async_context` so
  `__aexit__` (which emits `OpenClaudeDisconnected`, C6) always runs on
  application shutdown, including on startup failure after the port opened.
- `OpenClaudeGrpcClient` reads `process.grpc_url` (resolved after entry, incl.
  the `localhost:0` free-port case, Task 03.0 subtask 03), never
  `settings.grpc_url` directly.

## Constraints

- The `settings.grpc_url is not None` branch appears in **exactly one place** —
  this `build_code_agent` helper in `app.py` (C4). No other module branches on
  OpenClaude presence.
- `aegis/code_intel/` imports **neither** `aegis.openclaude` **nor** `grpc`
  (C3); the backend is injected via constructor.
- No import of `aegis.openclaude` appears in `aegis/core/` or `aegis/ui/` (C3).
- `Optional[T]` from `typing`, never `T | None`, including in subscripts and
  `Annotated[...]` (C9); `from __future__ import annotations` in every file.
- `ruff` and `replace_optional.py --check` stay clean (C9).
- Every new public class/method carries an RST-style docstring (C9).
- No raw incident payload text or unredacted response text is placed into
  `CodeResult.metadata` or any log line (C9).
- Scaffolding stays minimal: no tool registry, no ReAct loop, no index backends.

## Success criteria

- [ ] `aegis/code_intel/{__init__.py,backend.py,agent.py,budget.py}` exist and
      export `CodeBackend`, `CodeResult`, `CodeTaskContext`, `CodeAgent`,
      `CallBudget`.
- [ ] `grep -R "aegis.openclaude\|import grpc" aegis/code_intel/` returns
      nothing (C3).
- [ ] `CodeAgent(backend=None).investigate(...)` returns a non-raising
      `CodeResult(available=False, token_estimate=0)`.
- [ ] `CodeAgent` is constructible with an all-mock backend in a unit test with
      zero real processes or gRPC channels.
- [ ] `app.py` constructs `OpenClaudeGrpcClient`/`OpenClaudeProcess`/
      `OpenClaudeTool` **only** when `settings.openclaude.grpc_url is not None`.
- [ ] The `grpc_url is not None` branch exists in exactly one file (`app.py`),
      verifiable by grep.
- [ ] `ruff`, `replace_optional.py --check` clean on all new
      files and on `app.py`.
