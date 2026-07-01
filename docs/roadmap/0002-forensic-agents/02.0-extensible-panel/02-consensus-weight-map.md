# 02 - Data-driven consensus weights

**Parent task:** 02.0 Extensible Panel
**State:** ⬜ Not started
**Depends on:** Task 01.0
**Blocks:** 04

## Objective

Replace `AgentWeightEntry`'s four fixed float fields with a single
`weights: dict[str, float]` map keyed by `agent_key`, and make
`ConsensusEvaluator.calculate` iterate that map instead of a hard-coded
four-key tuple. Implements contract **C3**. Default weights must reproduce the
0001 matrix exactly.

## Files

- **Modify** `src/aegis_swr/config/settings.py` (`AgentWeightEntry`, `AgentWeightsSettings`)
- **Modify** `src/aegis_swr/core/consensus.py` (`ConsensusEvaluator`)

## Changes to `AgentWeightEntry`

1. New shape:

   ```python
   class AgentWeightEntry(BaseSettings):
       weights: dict[str, float] = Field(default_factory=dict)

       def __init__(self, **data: object):
           # Back-compat shim: fold legacy per-agent kwargs into `weights`.
           # AgentWeightEntry(os_kernel=0.4, code_analyst=0.35, ...) still works.
           legacy = {k: float(v) for k, v in data.items()
                     if k != "weights" and isinstance(v, (int, float))}
           if legacy:
               merged = dict(data.get("weights") or {})
               merged.update(legacy)
               data = {"weights": merged}
           super().__init__(**data)

       def weight_for(self, agent_key: str) -> float:
           return self.weights.get(agent_key, 0.0)
   ```

   > Keep the implementation faithful to Pydantic v2 settings semantics; the
   > snippet shows intent. A `model_validator(mode="before")` is an acceptable
   > alternative to the custom `__init__` if it is cleaner under mypy strict.

2. `AgentWeightsSettings` keeps its ten per-fault-class fields, but each
   `default_factory` now passes the same legacy kwargs (which the shim folds into
   `weights`) - **no numeric change** to any default. `for_fault_class` is
   unchanged.

## Changes to `ConsensusEvaluator`

1. Drop the module-level `_AGENT_KEYS = ("os_kernel", ...)` tuple.
2. `calculate(agent_scores, fault_class)` now iterates the **union of keys** in
   the fault class's `weights` map, excluding any synthesis agent
   (`remediation_planner` is never weighted):

   ```python
   def calculate(self, agent_scores, fault_class):
       entry = self._weights.for_fault_class(fault_class.value)
       weight_map = {k: w for k, w in entry.weights.items()
                     if k != "remediation_planner"}
       total_weight = sum(weight_map.values())
       if total_weight == 0.0:
           return 0.0
       weighted_sum = sum(w * agent_scores.get(k, 0.0)
                          for k, w in weight_map.items())
       return weighted_sum / total_weight
   ```

3. `is_converged` / `is_deadlocked` are unchanged.

## Constraints

- **Numeric back-compat:** for every existing fault class, `calculate` with the
  default config and the same `agent_scores` returns the identical float it did
  in 0001 (the four base keys, same weights, same normalization).
- Missing agent keys contribute 0.0 (partial rounds still score).
- `remediation_planner` weight, if ever present, is ignored by `calculate`.
- `Optional[T]`, mypy strict, ruff clean.

## Tests

- Extend `tests/unit/test_consensus.py`:
  - `test_legacy_weights_unchanged` - for each of the ten fault classes, the
    default entry's `weights` equals the 0001 four-key values.
  - `test_calculate_matches_0001_for_base_panel` - a fixed `agent_scores` over the
    four base keys yields the same number as the pre-task implementation
    (hard-code the expected floats).
  - `test_calculate_includes_new_agent_key` - an entry with an extra key (e.g.
    `memory_forensics=0.3`) folds it into the weighted sum and re-normalizes.
  - `test_remediation_planner_weight_ignored` - a `remediation_planner` weight in
    the map does not affect `calculate`.
  - `test_legacy_kwargs_shim` - `AgentWeightEntry(os_kernel=0.5, code_analyst=0.5)`
    produces `weights == {"os_kernel": 0.5, "code_analyst": 0.5}`.

## Success criteria

- [ ] `AgentWeightEntry` exposes `weights: dict[str, float]` + `weight_for`, and
      still accepts the legacy per-agent kwargs.
- [ ] `ConsensusEvaluator.calculate` iterates the weight map and excludes
      `remediation_planner`.
- [ ] All five new tests pass; existing consensus tests pass unchanged.
- [ ] `mypy src/` clean.
