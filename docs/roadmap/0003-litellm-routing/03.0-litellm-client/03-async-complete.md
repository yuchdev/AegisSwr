# 03 — `async complete()` — call, latency, cost

**Parent task:** 03.0 LiteLLM Client
**State:** ⬜ Not started
**Depends on:** 01, 02
**Blocks:** 04.0

## Objective

Implement `LiteLLMClient.complete()` — the single async method that calls
`litellm.acompletion`, measures wall-clock latency, extracts token counts
and cost, and normalizes all errors to `RouterException`.

## Method signature & contract

```python
async def complete(self, request: CompletionRequest) -> CompletionResponse:
    """Make a single model call. Does NOT implement retry or fallback.

    :param request: Encapsulates model, messages, timeout, and extra headers.
    :return: CompletionResponse with content, tokens, latency, and cost.
    :raises RouterException: For any provider or network error, with the
        original exception set as __cause__.
    """
    ...
```

## Implementation sketch

```python
import time
import litellm
from aegis.router.exceptions import RouterException

async def complete(self, request: CompletionRequest) -> CompletionResponse:
    t0 = time.monotonic()
    try:
        response = await litellm.acompletion(
            model=request.model,
            messages=request.messages,
            timeout=request.timeout_s,
            extra_headers=request.extra_headers,
        )
    except Exception as exc:
        raise RouterException(str(exc)) from exc

    latency_ms = (time.monotonic() - t0) * 1000.0

    content = response.choices[0].message.content or ""
    usage = response.usage
    input_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    cost_usd: Optional[float] = None
    try:
        cost_usd = litellm.completion_cost(completion_response=response)
    except Exception:
        pass  # cost is best-effort; never raise for missing cost data

    return CompletionResponse(
        model_used=response.model or request.model,
        content=content,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
```

## Constraints

- `latency_ms` uses `time.monotonic()` (not `time.time()`; monotonic is
  suitable for duration measurement and unaffected by clock adjustments).
- **All exceptions** from `litellm.acompletion` are caught and re-raised
  as `RouterException` with `__cause__` set. This includes network errors,
  auth failures, rate limits, and context-length errors.
- `cost_usd` is `None` on any failure of `litellm.completion_cost()` — never
  propagated as an error.
- No retry/fallback logic here.

## Success criteria

- [ ] `latency_ms` is measured from just before the `litellm.acompletion`
      call to just after it returns.
- [ ] Any `litellm.*` exception (including `APIError`, `Timeout`,
      `RateLimitError`) is caught and re-raised as `RouterException`.
- [ ] `cost_usd` is populated via `litellm.completion_cost()` when available,
      `None` otherwise.
- [ ] `model_used` is taken from `response.model`, falling back to
      `request.model` if absent.
