# 05 - Config model & examples

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** 03
**Blocks:** 06

## Objective

Expose the panel and weight model through configuration: an `AgentPanelSettings`
block wired into `Settings`, plus the matching keys in `config.yaml` and
`agents.example.json`. Defaults must reproduce the legacy panel and weights.

## Files

- **Modify** `src/aegis_swr/config/settings.py` (finalize `AgentPanelSettings`, wire into `Settings`)
- **Modify** `config.yaml` (root default config)
- **Modify** `config/agents.example.json` (or the project's canonical example; confirm path)

## `AgentPanelSettings` (final)

```python
class AgentPanelSettings(BaseSettings):
    default_panel: list[str] = Field(
        default_factory=lambda: ["os_kernel", "code_analyst", "log_historian", "skeptic"]
    )
    per_fault_class: dict[str, list[str]] = Field(default_factory=dict)
    enabled_synthesis: list[str] = Field(default_factory=list)
```

Wire as `Settings.agents_panel` (or under an existing `agents` grouping - match
the placement of `AgentWeightsSettings`). Env overrides follow the `AEGIS__`
prefix + `__` delimiter automatically.

## `config.yaml` block (defaults = legacy behavior)

```yaml
agents:
  panel:
    default_panel: [os_kernel, code_analyst, log_historian, skeptic]
    per_fault_class: {}          # populated in Task 08.0 with specialist panels
    enabled_synthesis: []        # ["remediation_planner"] added in Task 07.0/08.0
  weights:
    # unchanged 0001 per-fault-class matrix, now expressed as key→weight maps
    memory_access_violation: {os_kernel: 0.40, code_analyst: 0.35, log_historian: 0.15, skeptic: 0.10}
    # ... the remaining nine fault classes, identical numbers to 0001 ...
```

> The weight block expresses the existing 0001 numbers in the new map form. Task
> 08.0 adds specialist keys per the
> [authority matrix](/docs/roadmap/0002-forensic-agents/plan.md#specialist--fault-class-authority-matrix)
> and re-normalizes.

## `agents.example.json`

Mirror the same structure in the example JSON the `/playbook-validate` and config
loaders read, so users have a copy-paste starting point including a commented
specialist panel example.

## Constraints

- Defaults reproduce the legacy panel + weights (back-compat gate).
- Out-of-range / unknown keys are tolerated by `create_agent_panel` (warn+skip);
  the config schema itself accepts free-form key lists.
- `Optional[T]`, full annotations, ruff clean.

## Tests

- Extend `tests/unit/test_settings.py`:
  - `test_agent_panel_defaults` - `default_panel` is the four base keys;
    `per_fault_class` and `enabled_synthesis` empty.
  - `test_agent_panel_env_override` - `AEGIS__agents__panel__default_panel`
    overrides the panel.
  - `test_weights_loaded_from_yaml` - the ten fault-class weight maps load with the
    expected base-key values.

## Success criteria

- [ ] `AgentPanelSettings` exists and is reachable from `Settings`.
- [ ] `config.yaml` and `agents.example.json` carry the panel + weight blocks with
      legacy defaults.
- [ ] Settings tests pass; `python scripts/replace_optional.py --check` clean.
