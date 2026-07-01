# 01 — ModelRouter public interface

**Parent task:** 04.0 Model Router
**State:** ⬜ Not started
**Depends on:** 02.0/01 (RouterConfig), 02.0/02 (events), 02.0/03 (exceptions), 03.0/03 (client)
**Blocks:** 02, 03, 04

## Objective

Define and implement the `ModelRouter` class skeleton in
`aegis/router/router.py`: the constructor, the `from_config()` factory, and the
`complete()` method signature. The retry and fallback logic (subtasks 02–03)
fills in `complete()`'s body.

## Class definition

```python
# aegis/router/router.py
from __future__ import annotations
from typing import Optional

from aegis.router.config import RouterConfig, AgentConfig
from aegis.router.client import LiteLLMClient, CompletionRequest, CompletionResponse
from aegis.router.events import (
    RouterCallStarted,
    RouterCallCompleted,
    RouterCallFailed,
    RouterFallbackUsed,
)
from aegis.router.exceptions import AllProvidersExhausted
from aegis.event_bus import EventBus


class ModelRouter:
    """Public interface for all model calls within Aegis SWR.

    All agents call ``router.complete(role, messages, run_id=...)``.
    The router resolves the role to a model, executes with retry/fallback,
    emits RouterEvents on the bus, and raises AllProvidersExhausted if every
    provider fails.

    Usage::

        router = ModelRouter.from_config(config, bus)
        response = await router.complete(
            role="primary_reasoning",
            messages=[{"role": "user", "content": "..."}],
            run_id="abc123",
        )

    :param config: Validated RouterConfig loaded from agents.yaml.
    :param client: LiteLLMClient for single-shot completions.
    :param bus: EventBus for emitting RouterEvents.
    """

    def __init__(
        self,
        config: RouterConfig,
        client: LiteLLMClient,
        bus: EventBus,
    ) -> None:
        self._config = config
        self._client = client
        self._bus = bus

    @classmethod
    def from_config(cls, config: RouterConfig, bus: EventBus) -> ModelRouter:
        """Construct a ModelRouter with a LiteLLMClient configured from RouterConfig.

        :param config: Loaded RouterConfig.
        :param bus: EventBus to emit events onto.
        :return: Ready-to-use ModelRouter.
        """
        client = LiteLLMClient(config.providers)
        return cls(config=config, client=client, bus=bus)

    async def complete(
        self,
        role: str,
        messages: list[dict],
        *,
        run_id: str,
    ) -> CompletionResponse:
        """Resolve role → AgentConfig, execute with retry + fallback.

        :param role: Agent role name (must exist in RouterConfig).
        :param messages: OpenAI-format message list.
        :param run_id: Correlation ID propagated to every RouterEvent.
        :return: CompletionResponse from the first successful model.
        :raises KeyError: if the role is not configured (from RouterConfig).
        :raises AllProvidersExhausted: if all models in the primary + fallback
            chain fail.
        """
        agent_cfg = self._config.agent_for_role(role)
        # body implemented in subtasks 02 and 03
        ...
```

## Constraints

- `ModelRouter` has no knowledge of LiteLLM internals; it only calls
  `LiteLLMClient.complete()`.
- `run_id` is a keyword-only argument (enforced by the `*` separator).
- No fallback or retry logic in this subtask — only the class skeleton.

## Success criteria

- [ ] `ModelRouter.__init__` stores `config`, `client`, and `bus`.
- [ ] `from_config()` creates a `LiteLLMClient` from `config.providers`.
- [ ] `complete()` signature is exactly as shown (role, messages, *, run_id).
- [ ] `from aegis.router import ModelRouter` resolves cleanly.
