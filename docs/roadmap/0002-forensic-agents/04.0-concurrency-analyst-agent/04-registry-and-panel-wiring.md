# 04 - Registry & panel wiring

**Parent task:** 04.0 Concurrency Analyst Agent
**State:** ⬜ Not started
**Depends on:** 03 (agent implementation)
**Blocks:** 05

## Objective

Register `ConcurrencyAnalystAgent` in `AGENT_REGISTRY` and add it to the
per-fault panel overrides for its three authoritative fault classes (`deadlock`,
`use_after_free`, `assertion_failure`). Implements contracts **C4** and **C5**
for this specialist.

## Files

- **Modify** `src/aegis_swr/agents/registry.py`
  (add `ConcurrencyAnalystAgent` to `AGENT_REGISTRY`)
- **Modify** `src/aegis_swr/agents/forensic/__init__.py`
  (confirm `ConcurrencyAnalystAgent` is exported at the package level)
- **Modify** `src/aegis_swr/config/settings.py`
  (add `concurrency_analyst` to the `per_fault_class` default panel lists for
  the three authoritative fault classes in `AgentPanelSettings`)

## `AGENT_REGISTRY` change

Add one entry to the registry dict in `agents/registry.py`:

```
ConcurrencyAnalystAgent.agent_key: ConcurrencyAnalystAgent,
```

This line must appear in the "forensic specialists" comment block introduced
by Task 02.0/03, immediately after the `memory_forensics` entry (or first in
that block if `memory_forensics` has not landed yet). The insertion point
comment in the registry reads:
`# forensic specialists registered by Tasks 03.0–06.0`.

## Per-fault panel overrides

`AgentPanelSettings.per_fault_class` gains default panel lists for the three
fault classes. The lists follow the ordering rule from C4: `skeptic` last,
other agents in their configured order.

### `deadlock`

```
["os_kernel", "code_analyst", "log_historian", "concurrency_analyst", "skeptic"]
```

`concurrency_analyst` is placed immediately before `skeptic` so its output is
available as the freshest non-skeptic voice when the skeptic evaluates.

### `use_after_free`

```
["os_kernel", "code_analyst", "log_historian", "memory_forensics", "concurrency_analyst", "skeptic"]
```

`memory_forensics` precedes `concurrency_analyst` because UAF's primary axis
is memory-layout; the concurrency angle is secondary. If `memory_forensics` is
not registered (Task 03.0 not yet merged), `create_agent_panel` drops it with
a warning and the panel degrades gracefully per C4.

### `assertion_failure`

```
["os_kernel", "code_analyst", "log_historian", "concurrency_analyst", "skeptic"]
```

## `forensic/__init__.py`

Ensure the package-level `__init__.py` exports `ConcurrencyAnalystAgent`
directly, so callers can use:

```python
from aegis_swr.agents.forensic import ConcurrencyAnalystAgent
```

## Constraints

- The registry import of `ConcurrencyAnalystAgent` must not create a circular
  import. The import chain is: `registry.py` imports from
  `agents.forensic.concurrency_analyst`; the agent module imports from
  `core.schemas` and `agents.base` only.
- `create_agent_panel` must degrade gracefully (warning, not raise) if a key
  in a per-fault panel list is absent from `AGENT_REGISTRY`.
- `Optional[T]`, `replace_optional.py --check`, `ruff` clean throughout all touched files.
- No change to `AGENT_REGISTRY` ordering for existing base agents.

## Tests

These tests belong to subtask 05. They are listed here for traceability:

- `test_concurrency_analyst_in_registry` - `AGENT_REGISTRY["concurrency_analyst"]
  is ConcurrencyAnalystAgent`.
- `test_deadlock_panel_includes_concurrency_analyst` - `create_agent_panel(...,
  fault_class=FaultClass.deadlock)` returns an agent with
  `agent_key == "concurrency_analyst"`.
- `test_concurrency_analyst_before_skeptic` - in the `deadlock` panel, the
  `ConcurrencyAnalystAgent` instance appears before the `SkepticAgent` instance.
- `test_use_after_free_panel_degrades_without_memory_forensics` - if
  `memory_forensics` is absent from the registry, the UAF panel still returns
  `concurrency_analyst` (and does not raise).

## Success criteria

- [ ] `AGENT_REGISTRY["concurrency_analyst"]` resolves to `ConcurrencyAnalystAgent`.
- [ ] `from aegis_swr.agents.forensic import ConcurrencyAnalystAgent` resolves.
- [ ] `create_agent_panel(fault_class=FaultClass.deadlock)` includes
      `ConcurrencyAnalystAgent` before `SkepticAgent`.
- [ ] `create_agent_panel(fault_class=FaultClass.use_after_free)` includes
      `ConcurrencyAnalystAgent` and degrades gracefully if `memory_forensics`
      is unregistered.
- [ ] `create_agent_panel(fault_class=FaultClass.assertion_failure)` includes
      `ConcurrencyAnalystAgent`.
- [ ] Default panel (no fault-class override) is unchanged from the legacy
      four-agent chain.
- [ ] `replace_optional.py --check` clean; `ruff` clean.
