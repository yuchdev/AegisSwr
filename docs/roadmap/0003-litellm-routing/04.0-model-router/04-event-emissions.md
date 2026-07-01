# 04 - EventBus emissions

**Parent task:** 04.0 Model Router
**State:** ⬜ Not started
**Depends on:** 02, 03
**Blocks:** 06.0

## Objective

Verify the complete event emission contract across the full
retry + fallback flow and document the expected event sequence for each
scenario. This subtask is the acceptance gate for the router's observability.

## Event sequences by scenario

### Scenario A: First attempt succeeds

```
RouterCallStarted(role, model=primary, attempt=0)
RouterCallCompleted(role, model_used=primary, tokens=..., latency_ms=..., cost_usd=...)
```

### Scenario B: First attempt fails, second succeeds (retry)

```
RouterCallStarted(role, model=primary, attempt=0)
RouterCallFailed(role, model=primary, attempt=0, error=...)
RouterCallStarted(role, model=primary, attempt=1)
RouterCallCompleted(role, model_used=primary, ...)
```

### Scenario C: Primary exhausted, fallback succeeds

```
RouterCallStarted(role, model=primary, attempt=0)
RouterCallFailed(role, model=primary, attempt=0, ...)
[... repeat for retry.attempts ...]
RouterFallbackUsed(role, from_model=primary, to_model=fallback1, reason=...)
RouterCallStarted(role, model=fallback1, attempt=0)
RouterCallCompleted(role, model_used=fallback1, ...)
```

### Scenario D: All providers exhausted

```
RouterCallStarted(role, model=primary, attempt=0)
RouterCallFailed(role, model=primary, attempt=0, ...)
[... retries ...]
RouterFallbackUsed(role, from_model=primary, to_model=fallback1, ...)
RouterCallStarted(role, model=fallback1, attempt=0)
RouterCallFailed(role, model=fallback1, attempt=0, ...)
[AllProvidersExhausted raised - no final event]
```

### Scenario E: Non-retriable error (context length exceeded)

```
RouterCallStarted(role, model=primary, attempt=0)
RouterCallFailed(role, model=primary, attempt=0, error="context length exceeded")
RouterFallbackUsed(role, from_model=primary, to_model=fallback1, ...)
RouterCallStarted(role, model=fallback1, attempt=0)
RouterCallCompleted(...)  [or RouterCallFailed if fallback also fails]
```

## Constraints

- Every `RouterEvent` carries the same `run_id` that was passed to `complete()`.
- `RouterCallCompleted` is emitted **only** on success (not on the failed path).
- There is no "AllProvidersExhausted" event - the exception is the signal.
  Callers that want to observe exhaustion subscribe to `RouterCallFailed`
  patterns or catch the exception and emit their own event.

## Success criteria

- [ ] Scenarios A–E above produce the exact event sequences documented here
      (verified by `test_router.py`).
- [ ] Every emitted event carries `run_id` equal to the `run_id` passed to
      `complete()`.
- [ ] `RouterCallCompleted` appears exactly once per successful call.
- [ ] `RouterFallbackUsed.from_model` always equals the model that just
      failed, not always the primary.
