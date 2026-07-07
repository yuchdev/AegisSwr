# 01 — BaseAgent.reason() using ModelRouter

**Parent task:** 06.0 Agent Wiring
**State:** ⬜ Not started
**Depends on:** 04.0 (ModelRouter complete)
**Blocks:** 02

## Objective

Update `aegis/core/agents/base_agent.py` to call `ModelRouter.complete()`
instead of any direct provider SDK. Remove all `import anthropic`, `import openai`,
`import deepseek` from this file. Add `PipelineError` event emission when
`AllProvidersExhausted` is raised.

## Target implementation

```python
# aegis/core/agents/base_agent.py — AFTER

from __future__ import annotations
from typing import Optional
from abc import ABC, abstractmethod

from aegis.router.router import ModelRouter
from aegis.router.exceptions import AllProvidersExhausted
from aegis.event_bus import EventBus
from aegis.core.schemas import AgentTurn, InvestigationState
from aegis.core.events import PipelineError   # existing event type


class BaseAgent(ABC):
    """Abstract base for all debate-tier agents.

    :param router: Shared ModelRouter instance (injected by app.py).
    :param bus: EventBus for emitting events.
    """

    def __init__(self, router: ModelRouter, bus: EventBus) -> None:
        self._router = router
        self._bus = bus

    @property
    @abstractmethod
    def role(self) -> str:
        """LiteLLM role name matching an agents.yaml entry."""
        ...

    async def reason(
        self,
        messages: list[dict],
        run_id: str,
    ) -> AgentTurn:
        """Call the router for this agent's role and parse the response.

        :param messages: OpenAI-format message list.
        :param run_id: Correlation ID for event bus emissions.
        :return: Parsed AgentTurn.
        :raises AllProvidersExhausted: after emitting PipelineError on the bus.
        """
        try:
            response = await self._router.complete(
                role=self.role,
                messages=messages,
                run_id=run_id,
            )
        except AllProvidersExhausted as exc:
            self._bus.publish(PipelineError(
                run_id=run_id,
                stage=self.role,
                error=str(exc),
            ))
            raise
        return self._parse_response(response)

    @abstractmethod
    def _parse_response(self, response) -> AgentTurn:
        ...
```

## Constraints

- No `import anthropic`, `import openai`, or `import deepseek` in this file
  after the change.
- `ModelRouter` is received via constructor injection — no module-level
  singleton or global state.
- `PipelineError` must be emitted **before** re-raising `AllProvidersExhausted`
  so the UI can react to the failure before the exception unwinds.

## Success criteria

- [ ] `BaseAgent.__init__` accepts `router: ModelRouter` and `bus: EventBus`.
- [ ] `reason()` calls `self._router.complete(role=self.role, ...)`.
- [ ] `AllProvidersExhausted` triggers `PipelineError` event then re-raise.
- [ ] No direct provider SDK imports remain in this file.
- [ ] `replace_optional.py --check` passes on the updated file.
