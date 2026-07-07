# 02 - Consensus weight integration

**Parent task:** 03.0 Memory Forensics Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0, subtask 02 (data-driven `AgentWeightEntry.weights` map)
**Blocks:** 05

## Objective

Add `"memory_forensics"` as a weighted voter in the three fault classes for which
`MemoryForensicsAgent` is authoritative. Re-normalize each affected fault class so
its debate weights still sum to 1.0. Update both `config/agents.example.json` and
`config/config.yaml` (or whichever weight-config files Task 02.0 establishes as
canonical).

These weight vectors are **provisional**. Task 08.0 performs the final authority
matrix audit and may adjust individual floats; however, each fault class must
already sum to 1.0 at the end of this subtask.

## Files

- **Modify** `src/aegis_swr/config/settings.py` - update the three `AgentWeightEntry`
  defaults for the affected fault classes to include `"memory_forensics"` in the
  `weights` map (C3 format).
- **Modify** `config/agents.example.json` - add `"memory_forensics"` key to the
  `memory_access_violation`, `null_pointer_dereference`, and `use_after_free` blocks.
- **Modify** `config/config.yaml` (if present as the canonical weight source after
  Task 02.0) - same additions.

## Weight vectors

The existing 0001 base weights for these fault classes (from `AgentWeightsSettings`
defaults) are re-normalized to accommodate the new specialist. The numbers below
are the suggested starting point; Task 08.0 ratifies them.

### `memory_access_violation` (memory_forensics: primary)

Pre-existing base-agent sum was 1.0. Adding `memory_forensics` (primary, ~0.25)
and `exploitability` (also authoritative per the authority matrix, not yet
registered) means a provisional two-specialist split.

| agent_key          | weight |
|--------------------|--------|
| `os_kernel`        | 0.30   |
| `code_analyst`     | 0.25   |
| `memory_forensics` | 0.25   |
| `log_historian`    | 0.10   |
| `skeptic`          | 0.10   |

Sum: 1.00. (Exploitability's share will be carved out in Task 05.0 and the whole
row re-normalized in Task 08.0.)

### `null_pointer_dereference` (memory_forensics: non-primary)

| agent_key          | weight |
|--------------------|--------|
| `os_kernel`        | 0.35   |
| `code_analyst`     | 0.30   |
| `memory_forensics` | 0.20   |
| `log_historian`    | 0.10   |
| `skeptic`          | 0.05   |

Sum: 1.00.

### `use_after_free` (memory_forensics: primary)

Concurrency and exploitability are also authoritative here; provisional split
between this task's specialist only.

| agent_key          | weight |
|--------------------|--------|
| `os_kernel`        | 0.25   |
| `code_analyst`     | 0.25   |
| `memory_forensics` | 0.30   |
| `log_historian`    | 0.10   |
| `skeptic`          | 0.10   |

Sum: 1.00.

## Constraints

- After this subtask, every affected fault class's `weights` values must sum to
  exactly 1.0 (assert in a unit test).
- The three **unaffected** fault classes (`stack_overflow`, `integer_divide_by_zero`,
  `deadlock`, `assertion_failure`, `resource_exhaustion`, `unhandled_exception`,
  `unknown`) must not be altered.
- `Optional[T]` from `typing`; `replace_optional.py --check` clean; `ruff` clean.
- The `AgentWeightEntry` at this point uses the `weights: dict[str, float]` map
  introduced by Task 02.0/subtask 02. Do not revert to the four fixed-field form.

## Tests

In `tests/unit/test_consensus_weights.py` (create if absent):

- `test_memory_access_violation_weights_sum_to_one` - assert sum of
  `memory_access_violation` weights == 1.0 within float tolerance (`math.isclose`).
- `test_null_pointer_dereference_weights_sum_to_one` - same for
  `null_pointer_dereference`.
- `test_use_after_free_weights_sum_to_one` - same for `use_after_free`.
- `test_memory_forensics_key_present_in_authoritative_classes` - assert
  `"memory_forensics"` appears in the `weights` map of all three fault classes.
- `test_unaffected_fault_classes_unchanged` - load `AgentWeightsSettings` with
  defaults and assert `"memory_forensics"` is absent from
  `integer_divide_by_zero`, `deadlock`, `unhandled_exception`.

## Success criteria

- [ ] `"memory_forensics"` weight key added to `memory_access_violation`,
      `null_pointer_dereference`, and `use_after_free` entries.
- [ ] Each of the three affected fault classes sums to 1.0.
- [ ] Unaffected fault classes are not modified.
- [ ] `agents.example.json` reflects the same vectors.
- [ ] All five unit tests pass.
- [ ] `replace_optional.py --check` clean; `ruff` clean.
