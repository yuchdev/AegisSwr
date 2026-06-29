# 03 — Agent registry & panel factory

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** 01
**Blocks:** 04

## Objective

Introduce `agents/registry.py` with an `agent_key → class` registry and a
`create_agent_panel()` factory that returns the ordered debate panel for a given
fault class. Implements contract **C4**.

## Files

- **Create** `src/aegis_swr/agents/registry.py`
- **Modify** `src/aegis_swr/agents/__init__.py` (export `create_agent_panel`, `AGENT_REGISTRY`)
- **Modify** `src/aegis_swr/config/settings.py` (add `AgentPanelSettings`; see also subtask 05)

## `AGENT_REGISTRY`

```python
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    OSKernelAgent.agent_key: OSKernelAgent,
    CodeAnalystAgent.agent_key: CodeAnalystAgent,
    LogHistorianAgent.agent_key: LogHistorianAgent,
    SkepticAgent.agent_key: SkepticAgent,
    # forensic specialists registered by Tasks 03.0–06.0
    # remediation_planner registered by Task 07.0 (synthesis; not a debate agent)
}
```

> Tasks 03.0–07.0 each add their class to this dict. Forensic agents are eligible
> for the debate panel; the synthesis planner is registered but flagged
> `category == "synthesis"` so `create_agent_panel` excludes it.

## `create_agent_panel`

```python
def create_agent_panel(
    ai_backend: AIAPIBackend,
    settings: Settings,
    fault_class: Optional[FaultClass] = None,
) -> list[BaseAgent]:
    """Return the ordered debate panel (synthesis agents excluded).

    Resolution:
      1. Pick the key list: per-fault override from AgentPanelSettings if present
         for `fault_class`, else the configured default panel, else the four base
         keys (back-compat).
      2. Drop any key whose registered class has category == "synthesis".
      3. Instantiate each remaining key's class with (ai_backend, settings).
      4. Enforce ordering: skeptic is always moved to the END; the rest keep their
         configured order.
    """
```

Ordering invariants:
- `skeptic` is always last.
- The **default** panel resolves to exactly
  `["os_kernel", "code_analyst", "log_historian", "skeptic"]` (back-compat).
- Unknown keys in config are dropped with a `loguru` warning (never raise mid-run).

## `AgentPanelSettings` (sketch; finalized in subtask 05)

```python
class AgentPanelSettings(BaseSettings):
    default_panel: list[str] = Field(
        default_factory=lambda: ["os_kernel", "code_analyst", "log_historian", "skeptic"]
    )
    # optional per-fault overrides, e.g. {"deadlock": ["os_kernel", "concurrency_analyst", ...]}
    per_fault_class: dict[str, list[str]] = Field(default_factory=dict)
    enabled_synthesis: list[str] = Field(default_factory=list)  # e.g. ["remediation_planner"]
```

## Constraints

- `create_agent_panel` never returns a synthesis agent.
- It never raises on a bad config key — it warns and skips.
- No import cycle: `registry.py` imports the concrete agent classes; orchestrator
  imports `create_agent_panel` (not the classes directly, going forward).
- `Optional[T]`, mypy strict, ruff clean.

## Tests

- Add `tests/unit/test_agent_registry.py`:
  - `test_registry_has_base_agents` — the four base keys map to the right classes.
  - `test_default_panel_is_legacy_chain` — `create_agent_panel(..., fault_class=None)`
    with default settings returns the four base agents in legacy order.
  - `test_skeptic_always_last` — a config that lists skeptic first still yields it last.
  - `test_synthesis_excluded` — a synthesis key in a panel list is filtered out.
  - `test_unknown_key_warns_and_skips` — a bogus key is dropped, no raise.
  - `test_per_fault_override` — a per-fault panel override is honored for that class.

## Success criteria

- [ ] `AGENT_REGISTRY` maps the four base keys; `create_agent_panel` returns an
      ordered, instantiated panel.
- [ ] Default panel reproduces the legacy four-agent chain; skeptic always last.
- [ ] Synthesis agents and unknown keys are excluded gracefully.
- [ ] All registry tests pass; `mypy src/` clean.
