# 02 - Consensus weight integration

**Parent task:** 06.0 Resource Exhaustion Agent
**State:** ⬜ Not started
**Depends on:** Task 02.0 subtask 02
**Blocks:** 05

## Objective

Register `resource_exhaustion` as a weighted voter in the three fault classes
where this agent holds authority. Add the agent's key to the relevant
`AgentWeightEntry.weights` maps in `config/config.yaml` and
`config/agents.example.json`, and ensure each touched fault class's weights
remain normalized to 1.0 after insertion.

These weight vectors are **provisional**. Task 08.0 ratifies the final floats
after the full panel is assembled and ground-truth incidents have been evaluated.
The numbers below are the design-intent starting point.

## Files

- **Modify** `config/config.yaml` - update the weight maps for
  `resource_exhaustion`, `stack_overflow`, and `deadlock` fault classes.
- **Modify** `config/agents.example.json` - same three fault-class entries.

## Weight vectors

### `resource_exhaustion` fault class (primary authority)

The agent is the dominant voter; `log_historian` is secondary because temporal
log evidence is the main diagnostic channel for leak detection.

| Agent key | Weight |
|---|---|
| `resource_exhaustion` | 0.30 |
| `log_historian` | 0.25 |
| `os_kernel` | 0.20 |
| `code_analyst` | 0.15 |
| `skeptic` | 0.10 |

Sum: 1.00.

### `stack_overflow` fault class

Stack overflow already has `exploitability` as a specialist (Task 05.0).
`resource_exhaustion` is added as a second specialist with slightly lower share;
re-normalization is required after both tasks 05.0 and 06.0 land. The
**provisional** post-06.0 vector (before 05.0 is considered):

| Agent key | Weight |
|---|---|
| `os_kernel` | 0.30 |
| `resource_exhaustion` | 0.25 |
| `code_analyst` | 0.20 |
| `log_historian` | 0.15 |
| `skeptic` | 0.10 |

Sum: 1.00.

Note: Task 08.0 re-normalizes once `exploitability` is also inserted into this
fault class. Do not pre-insert `exploitability` here; that is Task 05.0's
responsibility.

### `deadlock` fault class

Deadlock already has `concurrency_analyst` as the primary specialist (Task
04.0). `resource_exhaustion` joins for the thread-pool-starvation variant. The
**provisional** post-06.0 vector (before 04.0 is considered):

| Agent key | Weight |
|---|---|
| `os_kernel` | 0.30 |
| `resource_exhaustion` | 0.25 |
| `code_analyst` | 0.20 |
| `log_historian` | 0.15 |
| `skeptic` | 0.10 |

Sum: 1.00.

Note: Task 08.0 re-normalizes once `concurrency_analyst` is also inserted into
this fault class.

## Normalization rule

After editing, verify each modified fault class entry independently:
`sum(weights.values()) == 1.0` within floating-point tolerance (assert to
4 decimal places). The data-driven `ConsensusEvaluator` introduced by Task 02.0
relies on this invariant; a un-normalized map will silently produce biased scores.

## Constraints

- `Optional[T]` is not directly relevant here (YAML/JSON only), but any
  Python helper that reads these maps must follow `Optional[T]`.
- Do not modify fault classes outside the three listed above.
- Keep the YAML/JSON key order consistent with the existing file structure.
- Provisional weights only; mark each block with a comment
  `# provisional - ratified by Task 08.0`.

## Success criteria

- [ ] `config/config.yaml` and `config/agents.example.json` both contain
      `resource_exhaustion` weight entries under `resource_exhaustion`,
      `stack_overflow`, and `deadlock` fault classes.
- [ ] Each of the three touched fault classes sums to 1.0 (verified by
      `tests/unit/test_consensus_weights.py`).
- [ ] No fault class outside the three is modified.
- [ ] `mypy --strict` and `ruff` clean (no Python changes in this subtask,
      but any helper touched must remain clean).
