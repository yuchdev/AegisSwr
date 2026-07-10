"""Code Intelligence entry point.

:class:`CodeAgent` is the single object the rest of Aegis SWR calls to delegate
a code-navigation task. It holds an *optional* :class:`CodeIntelBackend`: when
no backend is registered (``OPENCLAUDE_GRPC_URL`` unset), the capability is
reported as unavailable without raising (C4).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from loguru import logger

from aegis_swr.code_intel.backend import CodeIntelBackend, CodeResult, CodeTaskContext


class CodeAgent:
    """Delegates a code task to the registered backend, if any.

    :ivar _backend: The sole registered :class:`CodeIntelBackend`, or ``None``
        when code intelligence is unavailable in this deployment.
    """

    def __init__(self, backend: Optional[CodeIntelBackend] = None) -> None:
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
        dry_run: bool = False,
    ) -> CodeResult:
        """Delegate *task*, or report unavailability when no backend is set.

        When ``self._backend is None`` this returns a non-raising
        ``CodeResult(available=False, token_estimate=0)`` — there are no sibling
        backends to fall back to (C4).

        The per-call token budget is *not* a parameter here: it is a
        construction-time collaborator of the backend itself
        (``OpenClaudeTool(..., budget=...)``), which owns the pre-check and
        post-completion charge. Per-investigation budget scoping - constructing
        the backend with an appropriately-scoped
        :class:`~aegis_swr.code_intel.budget.CallBudget` - is finalized in Task
        06.0 app wiring.

        :param task: The open-ended code-navigation task string.
        :param run_id: Investigation run identifier.
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
        return await self._backend.delegate(task, ctx)
