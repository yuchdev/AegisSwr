# 02 — Consensus weight integration

**Parent task:** 04.0 Concurrency Analyst Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0/02 (data-driven `AgentWeightEntry.weights` map in place)
**Blocks:** 05

## Objective

Add `concurrency_analyst` weight entries to the three fault classes for which
this agent is authoritative (`deadlock`, `use_after_free`, `assertion_failure`),
re-normalizing each affected class so its debate weights sum to 1.0. Update
both `agents.example.json` and `config/config.yaml` (or `config.example.json`
if `config.yaml` does not yet exist in the repo) to reflect the new agent's
presence. These vectors are **provisional**; Task 08.0 ratifies the final
floats after all four forensic specialists land.

## Files

- **Modify** `agents.example.json`
- **Modify** `config/config.yaml` (or `config/config.example.json` — whichever
  carries the canonical weights block; add `config/config.yaml` if absent)

## Proposed weight vectors

The base-panel weights below are taken from `agents.example.json` as of Task
02.0 completion. `concurrency_analyst` is inserted and the remaining agent
weights are scaled down proportionally so the sum remains 1.0. Exact floats
are rounded to two decimal places; Task 08.0 is the final arbiter.

### `deadlock` (concurrency_analyst is primary)

`concurrency_analyst` carries the largest single share because thread
scheduling and lock-ordering are the defining forensic domain.

| Agent | Weight |
|---|---|
| `concurrency_analyst` | 0.30 |
| `os_kernel` | 0.25 |
| `code_analyst` | 0.20 |
| `log_historian` | 0.15 |
| `skeptic` | 0.10 |

Sum: 1.00

Derivation: base vector was `{os_kernel: 0.35, code_analyst: 0.30, log_historian: 0.20, skeptic: 0.15}`.
Introduce `concurrency_analyst` at 0.30; scale remaining four by factor 0.70 / 1.00 = 0.70.

### `use_after_free` (concurrency_analyst is secondary)

`use_after_free` already has `memory_forensics` as primary (Task 03.0).
`concurrency_analyst` covers the race-induced subset. Weights shown assume
`memory_forensics` is also present in the panel; Task 08.0 reconciles the
combined vector across all specialists.

| Agent | Weight |
|---|---|
| `code_analyst` | 0.28 |
| `memory_forensics` | 0.25 |
| `concurrency_analyst` | 0.15 |
| `os_kernel` | 0.17 |
| `log_historian` | 0.10 |
| `skeptic` | 0.05 |

Sum: 1.00

> Note: if `memory_forensics` is not enabled for a given panel, the
> `ConsensusEvaluator` ignores the zero-scored missing key and re-normalizes
> over present voters (contract C3 — missing keys contribute 0.0, total weight
> is the sum of present keys only).

### `assertion_failure` (concurrency_analyst is secondary)

Concurrent invariant violations are a common trigger for assertions; the agent
provides a meaningful secondary signal without displacing `code_analyst` as
primary.

| Agent | Weight |
|---|---|
| `code_analyst` | 0.38 |
| `concurrency_analyst` | 0.20 |
| `os_kernel` | 0.20 |
| `log_historian` | 0.12 |
| `skeptic` | 0.10 |

Sum: 1.00

## Changes to `agents.example.json`

Replace the three affected fault-class objects. All other fault-class objects
are untouched. The `concurrency_analyst` key must appear in the objects for
`deadlock`, `use_after_free`, and `assertion_failure` only; it must not appear
in any other fault-class object in this file (those remain base-panel only
until Task 08.0 sets the final matrix).

## Changes to config YAML/JSON

Add or update the `agents.weights` section to mirror the same three fault-class
vectors. Provide an inline comment noting these are provisional until Task 08.0.

## Constraints

- Weights for each fault class listed in this subtask must sum to exactly 1.00
  (two-decimal precision is sufficient for the config file; Task 08.0 uses
  higher precision in the assertion gate).
- Do not modify weights for fault classes not listed here (`memory_access_violation`,
  `null_pointer_dereference`, `stack_overflow`, `integer_divide_by_zero`,
  `resource_exhaustion`, `unhandled_exception`, `unknown`) — those will be
  addressed by Task 08.0 or the specialist owning them.
- `Optional[T]` convention does not apply to this subtask (config data, not Python);
  the constraint carries forward to any Python settings models touched here.
- `mypy --strict` and `ruff` must still be clean after any incidental Python
  touches (e.g. updating `AgentWeightsSettings` defaults).

## Success criteria

- [ ] `agents.example.json` contains `concurrency_analyst` weight entries in
      the `deadlock`, `use_after_free`, and `assertion_failure` objects.
- [ ] Each of those three objects sums to 1.00.
- [ ] All other fault-class objects in `agents.example.json` are unchanged.
- [ ] The config YAML/JSON weights section reflects the same three vectors.
- [ ] Existing consensus unit tests still pass (back-compat: base panel only
      with the unchanged base weights reproduces 0001 results).
