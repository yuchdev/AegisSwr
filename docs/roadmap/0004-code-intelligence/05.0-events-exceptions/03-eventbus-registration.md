# 03 - EventBus registry update

**Parent task:** 05.0 Event Types & Exceptions
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** none

## Objective

Wire the seven `openclaude.*` events (subtask 01) into the existing `EventBus`
using the **same mechanism the Milestone 0003 `RouterEvent` types use**, and add
the `openclaude.*` rows to the event-taxonomy registry documentation that
already lists the `router.*` events, so operators and telemetry consumers can
discover the full event taxonomy in one place. The router does not use an
imperative `bus.register(...)` call: an event is "registered" by (a) being a
frozen dataclass carrying a `ClassVar[str] event_type` sentinel that the bus
distributes and consumers filter on, and (b) being re-exported from its package
`__init__.py` for discoverability. This subtask replicates both, adds nothing to
`aegis/core/events.py` (the bus itself is unchanged), and updates the taxonomy
doc.

## Mechanism (how the router does it, replicated here)

The router foundation (`docs/roadmap/0003-litellm-routing/02.0-router-foundation/`)
registers `RouterCallStarted` / `RouterCallCompleted` / `RouterCallFailed` /
`RouterFallbackUsed` by:

1. Defining them as `frozen=True` dataclasses with a `ClassVar[str] event_type`
   (subtask
   [02-events-dataclasses.md](/docs/roadmap/0003-litellm-routing/02.0-router-foundation/02-events-dataclasses.md)).
   The `EventBus` distributes them and subscribers filter by
   `event.event_type == "router.call.completed"` - no central type table is
   mutated.
2. Re-exporting them from `aegis/router/__init__.py` alongside the router's
   public API (subtask
   [04-package-init.md](/docs/roadmap/0003-litellm-routing/02.0-router-foundation/04-package-init.md)).
3. Documenting the full set in the router architecture doc's
   *"RouterEvent taxonomy"* section
   ([02-router-architecture.md](/docs/roadmap/0003-litellm-routing/07.0-documentation/02-router-architecture.md)).

This subtask does the identical three things for the `openclaude.*` events.

## File: `aegis/openclaude/__init__.py` (re-export the public API)

```python
from __future__ import annotations

# Public API - events and exceptions re-exported for discoverability.
from aegis.openclaude.events import (
    OpenClaudeConnected,
    OpenClaudeDisconnected,
    OpenClaudePermissionDenied,
    OpenClaudeStreamCompleted,
    OpenClaudeStreamError,
    OpenClaudeToolCall,
    OpenClaudeToolResult,
)
from aegis.openclaude.exceptions import (
    OpenClaudeConfigError,
    OpenClaudeUnavailableError,
    PermissionDeniedError,
)

__all__ = [
    # events (C8 taxonomy)
    "OpenClaudeConnected",
    "OpenClaudeDisconnected",
    "OpenClaudeToolCall",
    "OpenClaudeToolResult",
    "OpenClaudePermissionDenied",
    "OpenClaudeStreamCompleted",
    "OpenClaudeStreamError",
    # exceptions
    "OpenClaudeUnavailableError",
    "PermissionDeniedError",
    "OpenClaudeConfigError",
]
```

> Task 01.0 created `aegis/openclaude/__init__.py` as an empty, versioned file.
> This subtask populates it with the re-export block above. `OpenClaudeTool`,
> `OpenClaudeProcess`, and `OpenClaudeGrpcClient` are **not** re-exported here -
> importing them at package import time would pull `grpc` into the package
> namespace and violate the C3 isolation boundary. Only the payload-free,
> `grpc`-free events and exceptions are re-exported.

## Documentation update (the "registry")

Add a `openclaude.*` taxonomy table to the consolidated event-taxonomy
registry - the same document family that lists the `router.*` events - so the
full bus taxonomy is discoverable in one place. The seven rows are exactly the
C8 table:

| Class                        | `event_type`                   | Carries (beyond `run_id` + `timestamp`) |
|------------------------------|--------------------------------|------------------------------------------|
| `OpenClaudeConnected`        | `openclaude.connected`         | `grpc_url`, `mode`                       |
| `OpenClaudeDisconnected`     | `openclaude.disconnected`      | `reason`                                 |
| `OpenClaudeToolCall`         | `openclaude.tool_call`         | `tool`, `arg_count`                      |
| `OpenClaudeToolResult`       | `openclaude.tool_result`       | `tool`, `ok`, `result_size`              |
| `OpenClaudePermissionDenied` | `openclaude.permission_denied` | `tool`, `denied_binary`                  |
| `OpenClaudeStreamCompleted`  | `openclaude.stream_completed`  | `token_estimate`, `frame_count`, `truncated` |
| `OpenClaudeStreamError`      | `openclaude.stream_error`      | `error_type`, `code`, `frame_count`      |

**Home for this table.** The milestone's own documentation task (Task 09.0)
owns the OpenClaude docs surface; the natural home is a consolidated event
reference maintained there (or an addition to the router architecture doc's
taxonomy section if that becomes the single event registry). This subtask
specifies the table content and requires it land next to the `router.*`
taxonomy; the actual doc edit is executed by `docs-updater` under Task 09.0 so
the milestone's documentation stays single-sourced. Do not fork a second
taxonomy table inside `aegis/openclaude/`.

## Design rationale

- **No change to `aegis/core/events.py`.** The bus distributes events and
  subscribers filter by `event_type`; there is no central registry object to
  mutate, exactly as with the router events. Keeping the bus untouched avoids a
  cross-cutting edit to core for a module-local concern.
- **Re-export, don't relocate.** The events keep living in
  `aegis/openclaude/events.py`; `__init__.py` only re-exports, so
  `from aegis.openclaude import OpenClaudeStreamCompleted` resolves without a
  full module path - matching `from aegis.router import RouterCallCompleted`.
- **`grpc`-free package import.** Re-exporting only events and exceptions keeps
  `import aegis.openclaude` free of any `grpc` import (C3); the `grpc`-touching
  classes stay behind their submodules and are constructed at the `app.py`
  composition root.
- **Single taxonomy home.** Consolidating the `openclaude.*` rows next to
  `router.*` gives operators one place to discover every bus `event_type`.

## Constraints

- `from __future__ import annotations` at the top of `__init__.py`.
- No `grpc`, `litellm`, `pydantic`, or `OpenClaudeTool`/`OpenClaudeProcess`/
  `OpenClaudeGrpcClient` import in `__init__.py` (C3).
- The re-export list and `__all__` contain all seven events and all three
  exceptions, and nothing `grpc`-bound.
- `ruff` (`F401` re-export handled via `__all__`)
  and `ruff check src/ tests/` - clean.
- The taxonomy doc edit adds only the seven C8 rows; it does not alter the
  `router.*` rows.

## Success criteria

- [ ] `from aegis.openclaude import OpenClaudeStreamCompleted` (and each of the
      other six events) resolves.
- [ ] `from aegis.openclaude import OpenClaudeUnavailableError,
      PermissionDeniedError, OpenClaudeConfigError` resolves.
- [ ] `import aegis.openclaude` pulls in **no** `grpc` module (asserted by a
      unit test checking `sys.modules`).
- [ ] `OpenClaudeTool`, `OpenClaudeProcess`, and `OpenClaudeGrpcClient` are
      **not** importable from the top-level `aegis.openclaude` namespace.
- [ ] All seven events round-trip through a real `EventBus`
      publish/subscribe cycle and are distinguishable by `event.event_type`.
- [ ] The event-taxonomy registry documentation lists all seven `openclaude.*`
      rows alongside the `router.*` rows, matching the C8 table.
- [ ] `ruff check src/ tests/` - clean.
