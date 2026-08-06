# 02 - docs/router-architecture.md

**Parent task:** 07.0 Documentation & CI
**State:** ⬜ Not started
**Depends on:** 04.0 (router complete)
**Blocks:** -

## Objective

Author `docs/router-architecture.md` - the architectural reference for the
`aegis/router/` module. Primary audience: developers adding agents, adding
providers, or debugging routing failures.

## Required sections

### 1. Architecture diagram (ASCII)

```
agents.yaml
    │ RouterConfig.from_yaml()
    ▼
aegis/router/config.py     RouterConfig, AgentConfig, ProviderConfig, RetryPolicy
    │
    ▼
aegis/router/router.py     ModelRouter  ─────────────────────────┐
    │  role → AgentConfig                                         │
    │  retry + fallback loop                                      │ EventBus
    ▼                                                             │
aegis/router/client.py     LiteLLMClient  ◄── (only litellm import) │
    │                                                             │
    ▼                                                   RouterEvent emissions
  LiteLLM ──► Anthropic / DeepSeek / vLLM
```

### 2. RouterEvent taxonomy

Full table: event class name, `event_type` string, when emitted, which fields it carries. Reference contract C3 from `plan.md`.

### 3. Boundary contract

- What `aegis/core/` **may** import from `aegis/router/`: `ModelRouter`,
  `RouterConfig`, event classes, exception classes.
- What `aegis/core/` **must not** import: `litellm`, `LiteLLMClient`,
  `anthropic`, `openai`, `deepseek`.
- Enforcement: CI `grep` lint step + `test_litellm_is_only_imported_in_client`.

### 4. Fallback and retry semantics

- Linear backoff formula with example table:

  | Attempt | Sleep (backoff_s=1.0) |
  |---------|-----------------------|
  | 0       | none (first try)      |
  | 1       | 1.0 s                 |
  | 2       | 2.0 s                 |

- When retries are skipped (non-retriable errors)
- Fallback: one attempt per model, no per-fallback retry

### 5. Adding an event subscriber for routing telemetry

```python
from aegis.event_bus import EventBus
from aegis.router.events import RouterCallCompleted

bus = EventBus()

def on_completed(event):
    if event.event_type == "router.call.completed":
        print(f"{event.role}: {event.latency_ms:.0f}ms, cost=${event.cost_usd}")

bus.subscribe(on_completed)
```

## Success criteria

- [ ] `docs/router-architecture.md` created with all 5 sections above.
- [ ] ASCII diagram matches the actual file structure (verify file names).
- [ ] RouterEvent taxonomy table is complete (all 4 event types).
- [ ] `docs/README.md` index links to this new file.
