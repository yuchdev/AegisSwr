# 03 — Fallback chain iteration

**Parent task:** 04.0 Model Router
**State:** ⬜ Not started
**Depends on:** 02
**Blocks:** 04

## Objective

Implement the fallback chain section of `ModelRouter.complete()`. After the
primary model exhausts all retry attempts, iterate through
`AgentConfig.fallback` in order, attempting each once. Emit
`RouterFallbackUsed` when transitioning to a new model. If all fallbacks fail,
raise `AllProvidersExhausted`.

## Fallback loop

```python
# Continuing from retry loop (subtask 02)
# `errors` accumulates across all attempts and fallbacks

for fallback_model in agent_cfg.fallback:
    self._bus.publish(RouterFallbackUsed(
        run_id=run_id,
        role=role,
        from_model=agent_cfg.model if not errors_from_fallbacks else prev_model,
        to_model=fallback_model,
        reason=f"Primary model exhausted ({agent_cfg.retry.attempts} attempts)",
    ))
    fallback_request = CompletionRequest(
        model=fallback_model,
        messages=messages,
        timeout_s=agent_cfg.timeout_s,
    )
    self._bus.publish(RouterCallStarted(
        run_id=run_id,
        role=role,
        model=fallback_model,
        attempt=0,
    ))
    try:
        response = await self._client.complete(fallback_request)
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
        errors.append(f"{fallback_model}: {exc}")
        self._bus.publish(RouterCallFailed(
            run_id=run_id,
            role=role,
            model=fallback_model,
            attempt=0,
            error=str(exc),
        ))

raise AllProvidersExhausted(
    role=role,
    tried=[agent_cfg.model] + list(agent_cfg.fallback),
    errors=errors,
)
```

## Constraints

- Fallbacks get exactly **one** attempt each (no per-fallback retry).
- `RouterFallbackUsed.from_model` is the model that just failed (primary or
  the previous fallback), not always the primary.
- `AllProvidersExhausted.tried` contains **all** models attempted (primary +
  every fallback), in order. This allows callers to reconstruct the full chain.
- If `AgentConfig.fallback` is empty and the primary fails, `AllProvidersExhausted`
  is raised immediately with `tried=[primary_model]`.

## Success criteria

- [ ] `RouterFallbackUsed` emitted before each fallback attempt.
- [ ] Each fallback model gets exactly one attempt.
- [ ] Successful fallback emits `RouterCallCompleted` and returns.
- [ ] Failed fallback emits `RouterCallFailed` and continues to the next.
- [ ] When all fail, `AllProvidersExhausted` raised with the full `tried` list.
- [ ] Empty `fallback` list raises immediately after primary exhaustion.
