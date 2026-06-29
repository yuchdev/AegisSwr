# Task 06.0 — Resource Exhaustion Agent

**Parent task:** Milestone 0002 Forensic Agents ([plan.md](/docs/roadmap/0002-forensic-agents/plan.md))
**Status:** ⬜ Not started

## Scope

Deliver `ResourceExhaustionAgent` — the handle/fd/thread/memory-leak and OOM
specialist in the forensic agent panel. The agent addresses the product-roadmap
§1.1 gap: "silent logical lockups, resource leaks" that the Windows prototype
misses because they leave no explicit crash exception code. These incidents
manifest as progressive degradation — handle counts climbing, thread pools
exhausted, connection pools drained — rather than a hard fault, and require
temporal/log evidence to diagnose.

The agent joins the debate for three fault classes:

- `resource_exhaustion` — primary authority; the agent's home terrain.
- `stack_overflow` — stack space is itself an exhausted resource (unbounded
  recursion or per-thread stack-limit misconfiguration).
- `deadlock` — thread-pool starvation is a resource exhaustion variant where
  the resource is available worker threads.

The agent follows the shared forensic-specialist shape defined in
[plan.md §Tasks 03.0–06.0](/docs/roadmap/0002-forensic-agents/plan.md#tasks-030060--forensic-specialists-shared-shape).
Its distinguishing feature is a **deterministic leak-indicator pre-check** that
scans `brief.log_summary` and `brief.raw_text_excerpt` for resource-pressure
signals (e.g. `"too many open files"`, `"ERROR_NO_SYSTEM_RESOURCES"`,
`"OutOfMemoryError"`, handle-count growth phrases, thread-count thresholds)
before — and independent of — the LLM call, pre-populating `leak_indicators`.
Because temporal patterns in logs are the primary evidence channel, `log_summary`
is included in the agent context alongside the standard `incident_brief`,
mirroring the approach used by `LogHistorianAgent`.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Output schema](01-output-schema.md) | ⬜ Not started | 03 |
| 02 | [Consensus weight integration](02-consensus-weights.md) | ⬜ Not started | 05 |
| 03 | [Agent implementation](03-agent-implementation.md) | ⬜ Not started | 04, 05 |
| 04 | [Registry & panel wiring](04-registry-and-panel-wiring.md) | ⬜ Not started | 05 |
| 05 | [Tests](05-tests.md) | ⬜ Not started | — |

Subtasks 01 and 02 are independent of each other and may proceed in parallel.
Subtask 03 depends on 01; subtask 04 depends on 03; subtask 05 depends on all
of 01, 02, 03, and 04.

## Key constraints

- `Optional[T]` from `typing`; never `T | None` (enforced by
  `scripts/replace_optional.py --check`).
- `mypy --strict` and `ruff` must be clean after every subtask.
- The leak-indicator pre-check must never pass raw log or stack text to a
  shell, SQL, or unsanitised sink — regex scanning only; results stored in
  `leak_indicators`.
- `display_name = "Resource Exhaustion Agent"` must equal the `AgentTurn.agent`
  string emitted so existing turn-matching logic is not disturbed.
- Subtask 02 weight vectors are **provisional**; Task 08.0 ratifies the final
  floats and asserts each fault class's weights sum to 1.0.
- The Stop hook runs the unit suite; a red suite blocks ending the session.
