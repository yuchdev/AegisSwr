# 04 - Registry & panel wiring

**Parent task:** 06.0 Resource Exhaustion Agent
**State:** ⬜ Not started
**Depends on:** 03
**Blocks:** 05

## Objective

Register `ResourceExhaustionAgent` in the `AGENT_REGISTRY` introduced by Task
02.0, export it from `agents/forensic/__init__.py`, and add it to the
per-fault-class panel overrides for its three authoritative fault classes:
`resource_exhaustion` (primary), `stack_overflow`, and `deadlock`. Implements
contracts C4 and C5 from `plan.md`.

## Files

- **Modify** `src/aegis_swr/agents/registry.py`
- **Modify** `src/aegis_swr/agents/forensic/__init__.py`
- **Modify** `config/config.yaml` - add `resource_exhaustion` to the
  `per_fault_class` panel lists for the three fault classes.
- **Modify** `config/agents.example.json` - same three panel list entries.

## Registry change

In `src/aegis_swr/agents/registry.py`, add the import and the registry entry
adjacent to the other forensic specialist entries (Tasks 03.0–05.0):

```
from aegis_swr.agents.forensic.resource_analyst import ResourceExhaustionAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    # ... existing entries ...
    ResourceExhaustionAgent.agent_key: ResourceExhaustionAgent,
}
```

The dict key must use `ResourceExhaustionAgent.agent_key` (the `ClassVar`),
not a string literal, so a rename propagates automatically.

## Package export

In `src/aegis_swr/agents/forensic/__init__.py`, add:

```
from aegis_swr.agents.forensic.resource_analyst import ResourceExhaustionAgent

__all__ = [
    # ... existing forensic exports ...
    "ResourceExhaustionAgent",
]
```

This lets callers import via `from aegis_swr.agents.forensic import
ResourceExhaustionAgent` without knowing the module name.

## Per-fault-class panel configuration

In `config/config.yaml` and `config/agents.example.json`, update the
`agents.panel.per_fault_class` section to include `"resource_exhaustion"` in
the agent key list for each of the three fault classes.

### `resource_exhaustion` fault class

Panel order (debate order; `skeptic` always last):

```
["os_kernel", "log_historian", "code_analyst", "resource_exhaustion", "skeptic"]
```

Rationale: `log_historian` runs before the specialist so temporal patterns are
already in the discussion history when `resource_exhaustion` takes its turn.

### `stack_overflow` fault class

Add `"resource_exhaustion"` to the existing specialist list. If `exploitability`
(Task 05.0) is already in this list, insert `resource_exhaustion` before it:

```
["os_kernel", "code_analyst", "log_historian", "resource_exhaustion", "skeptic"]
```

Task 08.0 finalizes the exact order across all specialists.

### `deadlock` fault class

Add `"resource_exhaustion"` to the existing specialist list. If
`concurrency_analyst` (Task 04.0) is already in this list, insert
`resource_exhaustion` after it:

```
["os_kernel", "code_analyst", "log_historian", "resource_exhaustion", "skeptic"]
```

Task 08.0 finalizes the exact order across all specialists.

## Ordering invariant

`create_agent_panel` always moves `skeptic` to the end regardless of list
position (C4). The panels above reflect the intended debate order; the factory
enforces the skeptic-last invariant as a safety net.

## Constraints

- Import the class using its module path, not a string. No dynamic import at
  registry registration time.
- No circular imports: `registry.py` imports from `forensic/`; `forensic/`
  must not import from `registry.py`.
- `Optional[T]` from `typing`; never `T | None`.
- `ruff check src/ tests/` - clean after the change.
- `ruff` clean; line length 100.
- Unknown keys in panel config are silently dropped by `create_agent_panel`
  (C4 invariant); this subtask does not change that behavior.

## Success criteria

- [ ] `AGENT_REGISTRY["resource_exhaustion"]` resolves to
      `ResourceExhaustionAgent`.
- [ ] `from aegis_swr.agents.forensic import ResourceExhaustionAgent` resolves.
- [ ] `config/config.yaml` and `config/agents.example.json` list
      `"resource_exhaustion"` in the panel for `resource_exhaustion`,
      `stack_overflow`, and `deadlock` fault classes.
- [ ] `create_agent_panel(…, fault_class=FaultClass.RESOURCE_EXHAUSTION)`
      returns a panel containing a `ResourceExhaustionAgent` instance.
- [ ] `ruff check src/ tests/` - clean; no import cycles.
