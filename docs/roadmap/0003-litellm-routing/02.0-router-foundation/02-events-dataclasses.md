# 02 — events.py — RouterEvent dataclasses

**Parent task:** 02.0 Router Foundation Types
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 04.0

## Objective

Implement `aegis/router/events.py` — the four `RouterEvent` frozen dataclasses
that `ModelRouter` emits on the `EventBus`. These extend the existing event
taxonomy in `aegis/events.py` without importing from it (they are a separate
concern; the bus is untyped enough to accept any dataclass).

## File: `aegis/router/events.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import ClassVar, Optional


@dataclass(frozen=True)
class RouterCallStarted:
    """Emitted before each model call attempt."""
    event_type: ClassVar[str] = "router.call.started"
    run_id: str
    role: str
    model: str
    attempt: int


@dataclass(frozen=True)
class RouterCallCompleted:
    """Emitted on successful model response. Only event with token/cost data."""
    event_type: ClassVar[str] = "router.call.completed"
    run_id: str
    role: str
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: Optional[float]


@dataclass(frozen=True)
class RouterCallFailed:
    """Emitted on each individual attempt failure."""
    event_type: ClassVar[str] = "router.call.failed"
    run_id: str
    role: str
    model: str
    attempt: int
    error: str


@dataclass(frozen=True)
class RouterFallbackUsed:
    """Emitted when moving to the next model in the fallback chain."""
    event_type: ClassVar[str] = "router.fallback.used"
    run_id: str
    role: str
    from_model: str
    to_model: str
    reason: str
```

## Design rationale

- `ClassVar[str] event_type` allows `EventBus` subscribers to filter by type
  using `event.event_type == "router.call.completed"` without `isinstance`
  checks — consistent with the existing event pattern.
- `RouterCallCompleted` is the **only** event that carries token counts and
  cost. Duplicating these across events would complicate telemetry aggregation.
- `cost_usd: Optional[float]` (not `float`) because LiteLLM cannot determine
  cost for all providers/models.

## Constraints

- All four dataclasses `frozen=True`.
- `ClassVar[str] event_type` on every class.
- `Optional[float]` not `float | None` (C5).
- No `litellm` import.

## Success criteria

- [ ] All four event classes implemented with the fields above.
- [ ] All are `frozen=True`.
- [ ] All have `ClassVar[str] event_type` with the `router.*` string.
- [ ] `RouterCallCompleted` is the only class with `input_tokens`,
      `output_tokens`, and `cost_usd`.
