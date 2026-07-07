# Task 04.0 - Concurrency Analyst Agent

**Parent task:** Milestone 0002 Forensic Agents ([plan.md](/docs/roadmap/0002-forensic-agents/plan.md))
**Status:** ⬜ Not started

## Scope

Deliver `ConcurrencyAnalystAgent` - the deadlock and race-condition specialist
in the forensic agent panel. The agent joins the debate for fault classes where
thread-scheduling and lock-ordering knowledge provides decisive signal:
`deadlock` (primary), `use_after_free` (race-induced, secondary), and
`assertion_failure` (concurrent invariant violation, secondary).

The agent follows the shared forensic-specialist shape defined in
[plan.md §Tasks 03.0–06.0](/docs/roadmap/0002-forensic-agents/plan.md#tasks-030060--forensic-specialists-shared-shape).
Its distinguishing feature is a **deterministic wait-chain pre-check** that
scans the incident brief's raw text excerpt and thread summary for blocking
primitives (e.g. `WaitForMultipleObjects`, `EnterCriticalSection`,
`pthread_mutex_lock`) before - and independent of - the LLM call, pre-populating
`wait_chain` candidates when multiple threads are detected in a blocked state.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Output schema](01-output-schema.md) | ⬜ Not started | 03 |
| 02 | [Consensus weight integration](02-consensus-weights.md) | ⬜ Not started | 05 |
| 03 | [Agent implementation](03-agent-implementation.md) | ⬜ Not started | 04, 05 |
| 04 | [Registry & panel wiring](04-registry-and-panel-wiring.md) | ⬜ Not started | 05 |
| 05 | [Tests](05-tests.md) | ⬜ Not started | - |

Subtasks 01 and 02 are independent of each other and may proceed in parallel.
Subtask 03 depends on 01; subtask 04 depends on 03; subtask 05 depends on all
of 01, 02, 03, and 04.

## Key constraints

- `Optional[T]` from `typing`; never `T | None` (enforced by `scripts/replace_optional.py --check`).
- `ruff` must be clean after every subtask.
- The wait-chain pre-check must never pass raw thread-dump or log text to a
  shell, SQL, or unsanitised sink - regex/keyword scanning only, results stored
  in `wait_chain`.
- `display_name = "Concurrency Analyst Agent"` must equal the `AgentTurn.agent`
  string emitted so existing turn-matching logic is not disturbed.
- Subtask 02 weight vectors are **provisional**; Task 08.0 ratifies the final
  floats and asserts each fault class's weights sum to 1.0.
- The Stop hook runs the unit suite; a red suite blocks ending the session.
