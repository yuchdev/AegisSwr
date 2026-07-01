# 02 - Retry logic with async backoff

**Parent task:** 04.0 Model Router
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 03

## Objective

Implement the primary-model retry loop inside `ModelRouter.complete()`. On
each failed attempt, emit `RouterCallFailed` and sleep with linear backoff
before the next try. On success, emit `RouterCallCompleted` and return.

## Retry loop (primary model only)

```python
import asyncio
from aegis.router.exceptions import RouterException

# Inside ModelRouter.complete(), primary-model section:
agent_cfg: AgentConfig = self._config.agent_for_role(role)
primary_request = CompletionRequest(
    model=agent_cfg.model,
    messages=messages,
    timeout_s=agent_cfg.timeout_s,
)
errors: list[str] = []

for attempt in range(agent_cfg.retry.attempts):
    self._bus.publish(RouterCallStarted(
        run_id=run_id,
        role=role,
        model=agent_cfg.model,
        attempt=attempt,
    ))
    try:
        response = await self._client.complete(primary_request)
        self._bus.publish(RouterCallCompleted(
            run_id=run_id,
            role=role,
            model_used=response.model_used,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            cost_usd=response.cost_usd,
        ))
        return response
    except RouterException as exc:
        error_msg = str(exc)
        errors.append(f"{agent_cfg.model}[attempt={attempt}]: {error_msg}")
        self._bus.publish(RouterCallFailed(
            run_id=run_id,
            role=role,
            model=agent_cfg.model,
            attempt=attempt,
            error=error_msg,
        ))
        if _is_non_retriable(exc):
            break   # skip remaining retries; go straight to fallback
        if attempt < agent_cfg.retry.attempts - 1:
            await asyncio.sleep(agent_cfg.retry.backoff_s * (attempt + 1))

# primary exhausted → fallback chain (subtask 03)
```

## Non-retriable errors

Context-length-exceeded errors skip retries because retrying the same model
with the same messages will always fail. Detection heuristic (adjust at
implementation time):

```python
def _is_non_retriable(exc: RouterException) -> bool:
    msg = str(exc).lower()
    return "context" in msg and ("length" in msg or "exceeded" in msg)
```

## Constraints

- `asyncio.sleep`, never `time.sleep` (never blocks the event loop).
- Backoff formula: `backoff_s * (attempt + 1)` - linear, not exponential.
  Attempt 0 = no sleep (first try); attempt 1 = 1× backoff; attempt 2 = 2× etc.
- No sleep after the **last** attempt (the `attempt < max - 1` guard).
- `RouterCallStarted` emitted **before** the call; `RouterCallCompleted` /
  `RouterCallFailed` emitted **after**.

## Success criteria

- [ ] `RouterCallStarted` emitted before each attempt.
- [ ] `RouterCallCompleted` emitted on success; function returns.
- [ ] `RouterCallFailed` emitted on each failure.
- [ ] `asyncio.sleep` called with `backoff_s * (attempt + 1)` between retries.
- [ ] Non-retriable errors break the retry loop immediately.
- [ ] On exhaustion of all attempts, code continues to subtask 03 (fallback).
