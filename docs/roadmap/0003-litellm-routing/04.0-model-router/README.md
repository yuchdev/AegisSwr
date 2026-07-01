# Task 04.0 — Model Router

**Parent milestone:** [Milestone 0003 — LiteLLM Model Router](/docs/roadmap/0003-litellm-routing/plan.md)
**Status:** ⬜ Not started

## Scope

Implement `aegis/router/router.py` — the orchestration layer. `ModelRouter`
resolves an agent role to a model, executes the call via `LiteLLMClient` with
retry and fallback logic, and emits `RouterEvent`s on the `EventBus`. This is
the only class that agents and `app.py` interact with; it has no knowledge of
LiteLLM internals.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [ModelRouter public interface](01-router-interface.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [retry logic with async backoff](02-retry-logic.md) | ⬜ Not started | 03 |
| 03 | [fallback chain iteration](03-fallback-chain.md) | ⬜ Not started | 04 |
| 04 | [EventBus emissions](04-event-emissions.md) | ⬜ Not started | 06.0 |

## Key constraints

- `ModelRouter` has no knowledge of LiteLLM internals; it only calls
  `LiteLLMClient.complete()`.
- Backoff uses `asyncio.sleep`, never `time.sleep` (never blocks the event loop).
- `run_id` is attached to every emitted `RouterEvent`.
- `AllProvidersExhausted` includes the full list of models tried and their
  individual error messages.
- `ModelRouter` is constructed once at startup and shared across all agents —
  one instance, not one per agent (enforced by the `app.py` composition root in
  Task 06.0).

## Retry / fallback flow (C4 from plan.md)

```
for attempt in range(retry.attempts):
    try:
        response = await client.complete(request)
        emit RouterCallCompleted; return response
    except RouterException as exc:
        if non_retriable(exc): break       # skip to fallback immediately
        emit RouterCallFailed(attempt=attempt)
        if attempt < max_attempts - 1:
            await asyncio.sleep(backoff_s * (attempt + 1))

# primary exhausted → iterate fallbacks
for fallback_model in agent_config.fallback:
    emit RouterFallbackUsed(from_model=..., to_model=fallback_model)
    try:
        response = await client.complete(fallback_request)
        emit RouterCallCompleted; return response
    except RouterException:
        emit RouterCallFailed(...)

raise AllProvidersExhausted(role=role, tried=[primary] + fallbacks, errors=[...])
```
