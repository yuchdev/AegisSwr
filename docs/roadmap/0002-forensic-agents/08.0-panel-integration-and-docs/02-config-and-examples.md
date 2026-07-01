# 02 - Config & Examples

**Parent task:** Task 08.0 - Panel Integration, Docs & Hardening
**Status:** ⬜ Not started
**Depends on:** [01-default-panels-and-weight-audit.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/01-default-panels-and-weight-audit.md)
**Blocks:** [04-hardening-gates.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/04-hardening-gates.md)

---

## Objective

Write the definitive configuration artifacts that ship with the product,
reflecting the ratified weight table and panel assignments from subtask 01.
Check `.env.example` for any new environment variable keys introduced by
Milestone 0002. Verify a loader round-trip: settings loaded from the example
files produce a `Settings` object whose `agent_weights` and panel config match
the ratified values.

---

## Files to produce or update

### `agents.example.json`

The canonical example for `~/.aegis-swr/agents.json`. This file is read by
`AegisJsonSettingsSource` and mounted under the `agent_weights` key of
`Settings`. It must express the full nine-voter weight map using the data-driven
`weights` dict format from plan.md C3 (not the legacy four-field flat format).

Structure (abbreviated - implement all ten fault classes from subtask 01):

```json
{
  "memory_access_violation": {
    "weights": {
      "os_kernel": 0.20,
      "code_analyst": 0.20,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "memory_forensics": 0.25,
      "exploitability": 0.15
    }
  },
  "null_pointer_dereference": {
    "weights": {
      "os_kernel": 0.25,
      "code_analyst": 0.25,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "memory_forensics": 0.30
    }
  },
  "use_after_free": {
    "weights": {
      "os_kernel": 0.15,
      "code_analyst": 0.15,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "memory_forensics": 0.25,
      "concurrency_analyst": 0.15,
      "exploitability": 0.10
    }
  },
  "stack_overflow": {
    "weights": {
      "os_kernel": 0.25,
      "code_analyst": 0.20,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "exploitability": 0.20,
      "resource_exhaustion": 0.15
    }
  },
  "integer_divide_by_zero": {
    "weights": {
      "os_kernel": 0.35,
      "code_analyst": 0.40,
      "log_historian": 0.10,
      "skeptic": 0.15
    }
  },
  "deadlock": {
    "weights": {
      "os_kernel": 0.15,
      "code_analyst": 0.15,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "concurrency_analyst": 0.35,
      "resource_exhaustion": 0.15
    }
  },
  "assertion_failure": {
    "weights": {
      "os_kernel": 0.20,
      "code_analyst": 0.30,
      "log_historian": 0.10,
      "skeptic": 0.10,
      "concurrency_analyst": 0.30
    }
  },
  "resource_exhaustion": {
    "weights": {
      "os_kernel": 0.20,
      "code_analyst": 0.20,
      "log_historian": 0.15,
      "skeptic": 0.10,
      "resource_exhaustion": 0.35
    }
  },
  "unhandled_exception": {
    "weights": {
      "os_kernel": 0.30,
      "code_analyst": 0.35,
      "log_historian": 0.20,
      "skeptic": 0.15
    }
  },
  "unknown": {
    "weights": {
      "os_kernel": 0.30,
      "code_analyst": 0.35,
      "log_historian": 0.20,
      "skeptic": 0.15
    }
  }
}
```

The file location is `agents.example.json` at the repository root (alongside
`.env.example`). The docs reference `~/.aegis-swr/agents.json` as the runtime
location; the example ships as a copy-in template.

### `config.yaml` - `agents` block

The `config.yaml` YAML source (read by `AegisJsonSettingsSource`) gains two new
top-level keys under an `agents:` section:

```yaml
agents:
  panel:
    default_panel:
      - os_kernel
      - code_analyst
      - log_historian
      - skeptic
    per_fault_class:
      memory_access_violation:
        - os_kernel
        - code_analyst
        - log_historian
        - memory_forensics
        - exploitability
        - skeptic
      null_pointer_dereference:
        - os_kernel
        - code_analyst
        - log_historian
        - memory_forensics
        - skeptic
      use_after_free:
        - os_kernel
        - code_analyst
        - log_historian
        - memory_forensics
        - concurrency_analyst
        - exploitability
        - skeptic
      stack_overflow:
        - os_kernel
        - code_analyst
        - log_historian
        - exploitability
        - resource_exhaustion
        - skeptic
      integer_divide_by_zero:
        - os_kernel
        - code_analyst
        - log_historian
        - skeptic
      deadlock:
        - os_kernel
        - code_analyst
        - log_historian
        - concurrency_analyst
        - resource_exhaustion
        - skeptic
      assertion_failure:
        - os_kernel
        - code_analyst
        - log_historian
        - concurrency_analyst
        - skeptic
      resource_exhaustion:
        - os_kernel
        - code_analyst
        - log_historian
        - resource_exhaustion
        - skeptic
      unhandled_exception:
        - os_kernel
        - code_analyst
        - log_historian
        - skeptic
      unknown:
        - os_kernel
        - code_analyst
        - log_historian
        - skeptic
```

The `agents.weights` block in `config.yaml` mirrors `agents.example.json` with
the same structure; the YAML source is the canonical one for new deployments
while `agents.json` is the user-editable override.

### `.env.example`

Milestone 0002 introduces no new environment variable keys. Confirm by grepping
all `src/aegis_swr/agents/forensic/` and `src/aegis_swr/agents/synthesis/`
modules for `os.environ` / `getenv` / `AEGIS__` references. If none are found,
add a comment to `.env.example` noting that the agent panel is configured via
`agents.json` / `config.yaml`, not environment variables.

---

## Loader round-trip test

File: `tests/unit/test_agents_config_roundtrip.py`

### Test: `test_agents_example_json_loads_cleanly`

Read `agents.example.json` from the repository root, pass it to
`AgentWeightsSettings.model_validate(data)`, and assert that no `ValidationError`
is raised. Assert that all ten fault-class keys are present and that each returns
a non-empty `weights` dict from `for_fault_class`.

### Test: `test_agents_example_json_weights_sum_to_one`

For every fault-class entry in `agents.example.json`, sum all float values in
`weights` and assert the result equals 1.0 within tolerance 1e-6.

### Test: `test_config_yaml_panel_block_parses`

Load `config.yaml` (the YAML settings source path), extract the
`agents.panel.per_fault_class` mapping, and assert all ten `FaultClass` string
keys are present and each maps to a non-empty list ending with `"skeptic"`.

### Test: `test_round_trip_settings_default_panel`

Construct `Settings()` with no file overrides. Assert
`settings.agent_weights.for_fault_class("unknown").weights` matches the 0001
back-compat values (os_kernel=0.30, code_analyst=0.35, log_historian=0.20,
skeptic=0.15).

---

## Success criteria

- [ ] `agents.example.json` exists at the repository root with all ten fault
      classes expressed in the data-driven `weights` dict format.
- [ ] Every `weights` dict in `agents.example.json` sums to 1.0 (verified by
      `test_agents_example_json_weights_sum_to_one`).
- [ ] `config.yaml` contains an `agents.panel` block with `default_panel` and
      `per_fault_class` for all ten classes.
- [ ] `.env.example` is checked; a note is added if no new env keys are required.
- [ ] All four round-trip tests pass.
- [ ] `mypy --strict` and `ruff check` pass on `test_agents_config_roundtrip.py`.
- [ ] No existing test is weakened or deleted to achieve a green run.
