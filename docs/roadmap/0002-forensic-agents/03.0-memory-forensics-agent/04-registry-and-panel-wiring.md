# 04 - Registry & panel wiring

**Parent task:** 03.0 Memory Forensics Agent
**State:** ⬜ Not started
**Depends on:** 03 (agent implementation)
**Blocks:** 05

## Objective

Register `MemoryForensicsAgent` in the agent registry introduced by Task 02.0 and
wire it into the default per-fault-class panels for its three authoritative fault
classes. Implements the portion of contracts **C4** and **C5** that pertain to this
agent. The registry contract is defined in
[02.0-extensible-panel/03-registry-and-panel-factory.md](/docs/roadmap/0002-forensic-agents/02.0-extensible-panel/03-registry-and-panel-factory.md).

## Files

- **Modify** `src/aegis_swr/agents/registry.py` - add `MemoryForensicsAgent` entry.
- **Modify** `src/aegis_swr/agents/forensic/__init__.py` - confirm `MemoryForensicsAgent`
  is exported in `__all__` (may already be done by subtask 03; verify and complete if not).
- **Modify** `src/aegis_swr/config/settings.py` - add `"memory_forensics"` to the
  `per_fault_class` panel lists for the three authoritative fault classes inside
  `AgentPanelSettings` defaults (the settings model introduced by Task 02.0).
- **Modify** `config/agents.example.json` - add `"memory_forensics"` to the
  `per_fault_class` panel arrays for `memory_access_violation`,
  `null_pointer_dereference`, and `use_after_free`.

## Registry entry

Add the following entry to `AGENT_REGISTRY` in `agents/registry.py`, alongside
the existing base-agent entries:

```python
MemoryForensicsAgent.agent_key: MemoryForensicsAgent,
```

The comment block in `registry.py` marking the forensic-specialist zone (per the
Task 02.0 scaffold) must be preserved; insert the entry inside that zone.

## Panel configuration

`AgentPanelSettings.per_fault_class` maps fault-class strings to ordered agent-key
lists. Add `"memory_forensics"` to the lists for:

| fault_class                | panel (suggested order) |
|----------------------------|------------------------|
| `memory_access_violation`  | `["os_kernel", "code_analyst", "memory_forensics", "log_historian", "skeptic"]` |
| `null_pointer_dereference` | `["os_kernel", "code_analyst", "memory_forensics", "log_historian", "skeptic"]` |
| `use_after_free`           | `["os_kernel", "code_analyst", "memory_forensics", "log_historian", "skeptic"]` |

The ordering invariant from C4 applies: `skeptic` is always moved to the end by
`create_agent_panel` regardless of its position in this list, so listing it last
is the canonical form. The base agents (`os_kernel`, `code_analyst`,
`log_historian`) must remain in the panel for all three fault classes.

## Constraints

- `create_agent_panel` must not be modified in this subtask; only the registry
  dict and the panel-settings defaults are changed.
- The **default panel** (fault class `None` or unrecognized) must not be altered -
  it must remain the legacy four-agent chain to preserve the 0001 back-compat gate.
- No import cycle: `registry.py` imports `MemoryForensicsAgent` from
  `agents.forensic.memory_forensics`; the forensic subpackage must not import
  from `registry.py`.
- `Optional[T]` from `typing`; `replace_optional.py --check` clean; `ruff` clean.
- Unknown keys in config panel lists are silently dropped by `create_agent_panel`
  (already guaranteed by the C4 implementation); this subtask does not need to
  add new guard logic.

## Tests

In `tests/unit/test_agent_registry.py` (extend the file from Task 02.0):

- `test_memory_forensics_registered` - assert `"memory_forensics"` is a key in
  `AGENT_REGISTRY` and maps to `MemoryForensicsAgent`.
- `test_memory_forensics_panel_memory_access_violation` - call
  `create_agent_panel(..., fault_class=FaultClass.memory_access_violation)` with
  default settings; assert `MemoryForensicsAgent` appears in the returned panel.
- `test_memory_forensics_panel_use_after_free` - same for `use_after_free`.
- `test_memory_forensics_panel_null_pointer_dereference` - same for
  `null_pointer_dereference`.
- `test_default_panel_unchanged` - `create_agent_panel(..., fault_class=None)`
  returns exactly the four base agents in legacy order; `MemoryForensicsAgent` is
  absent.

## Success criteria

- [ ] `"memory_forensics"` key present in `AGENT_REGISTRY`, mapping to
      `MemoryForensicsAgent`.
- [ ] `MemoryForensicsAgent` exported from `agents/forensic/__init__.py`.
- [ ] `create_agent_panel` returns `MemoryForensicsAgent` for all three
      authoritative fault classes.
- [ ] Default panel (no fault class) is unchanged - four base agents only.
- [ ] `agents.example.json` panel arrays updated for the three fault classes.
- [ ] All five registry tests pass.
- [ ] `replace_optional.py --check` clean; `ruff` clean.
