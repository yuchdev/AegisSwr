# 01 - CompletionRequest / CompletionResponse types

**Parent task:** 03.0 LiteLLM Client
**State:** ⬜ Not started
**Depends on:** 02.0/03 (exceptions)
**Blocks:** 02, 03

## Objective

Define the two dataclasses that form the `LiteLLMClient`'s API boundary:
`CompletionRequest` (in) and `CompletionResponse` (out). These types are
the only things `ModelRouter` passes to / receives from the client; the
router never sees LiteLLM types directly.

## Types

```python
# aegis/router/client.py (excerpt - types section)

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CompletionRequest:
    """Input to LiteLLMClient.complete().

    :param model: LiteLLM model string, e.g. "anthropic/claude-sonnet-4-6".
    :param messages: OpenAI-format message list (role + content dicts).
    :param timeout_s: Per-call timeout in seconds.
    :param extra_headers: Optional additional HTTP headers for the provider.
    """
    model: str
    messages: list[dict]
    timeout_s: float
    extra_headers: dict = field(default_factory=dict)


@dataclass
class CompletionResponse:
    """Output from LiteLLMClient.complete().

    :param model_used: Actual model that responded (matches request.model).
    :param content: Text content of the response.
    :param input_tokens: Prompt token count from provider usage metadata.
    :param output_tokens: Completion token count.
    :param latency_ms: Wall-clock time from call entry to response receipt.
    :param cost_usd: Estimated cost in USD, or None if unavailable.
    """
    model_used: str
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: Optional[float]
```

## Design notes

- `CompletionRequest` is **not** frozen because `ModelRouter` swaps the
  `model` field when iterating the fallback chain (creating a new request
  is cleaner; but mutable avoids unnecessary allocation).
- `CompletionResponse.model_used` may differ from `request.model` in future
  if LiteLLM selects a sub-model - keeping it explicit avoids silent drift.
- `messages: list[dict]` uses the OpenAI format because LiteLLM normalizes
  all providers to this format internally.

## Constraints

- `Optional[float]` for `cost_usd`, not `float | None`.
- No `litellm` import in this section's types (they are plain dataclasses).

## Success criteria

- [ ] Both dataclasses defined with all fields listed above.
- [ ] `cost_usd` is `Optional[float]` (imported from `typing`).
- [ ] `extra_headers` defaults to an empty dict via `field(default_factory=dict)`.
