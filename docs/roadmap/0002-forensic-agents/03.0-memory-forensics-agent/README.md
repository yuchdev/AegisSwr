# Task 03.0 - Memory Forensics Agent

**Parent task:** Milestone 0002 Forensic Agents ([plan.md](/docs/roadmap/0002-forensic-agents/plan.md))
**Status:** ✅ Complete

## Scope

Deliver `MemoryForensicsAgent` - the heap-corruption and memory-safety specialist
in the forensic agent panel. The agent joins the debate for fault classes where
memory-layout and allocator-state knowledge provides decisive signal:
`memory_access_violation` (primary), `null_pointer_dereference`, and
`use_after_free` (primary).

The agent follows the shared forensic-specialist shape defined in
[plan.md §Tasks 03.0–06.0](/docs/roadmap/0002-forensic-agents/plan.md#tasks-030060---forensic-specialists-shared-shape).
Its distinguishing feature is a **deterministic fill-pattern pre-check** that
scans the incident brief's stack frames and raw text for known heap-metadata
sentinel values (e.g. `0xBAADF00D`, `0xFEEEFEEE`) before - and independent of -
the LLM call, surfacing them in `corruption_signatures` immediately.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Output schema](01-output-schema.md) | ✅ Complete | 03 |
| 02 | [Consensus weight integration](02-consensus-weights.md) | ✅ Complete (adapted) | 05 |
| 03 | [Agent implementation](03-agent-implementation.md) | ✅ Complete | 04, 05 |
| 04 | [Registry & panel wiring](04-registry-and-panel-wiring.md) | ✅ Complete (adapted) | 05 |
| 05 | [Tests](05-tests.md) | ✅ Complete | - |

> **Architecture reconciliation (2026-07-10):** subtasks 02 & 04 were written
> against the roadmap's per-fault-class weight matrix + `AgentPanelSettings`,
> which the ratified Task 02.0 superset replaced. As implemented: subtask 02's
> weight integration became the agent's intrinsic `default_weight = 0.25`
> ClassVar (self-normalized by the live panel; no per-fault matrix, no
> `config/agents.example.json`); subtask 04's panel wiring became fault-aware
> auto-selection via `AgenticManagerStrategy` + the new
> `authoritative_fault_classes` ClassVar. See
> [status.md](/docs/roadmap/0002-forensic-agents/status.md) Task 03.0.

Subtasks 01 and 02 are independent of each other and may proceed in parallel.
Subtask 03 depends on 01; subtask 04 depends on 03; subtask 05 depends on all
of 01, 02, 03, and 04.

## Key constraints

- `Optional[T]` from `typing`; never `T | None` (enforced by `scripts/replace_optional.py --check`).
- `ruff` must be clean after every subtask.
- The fill-pattern pre-check must never pass raw stack text to a shell, SQL,
  or unsanitised sink - regex scanning only, results stored in `corruption_signatures`.
- `display_name = "Memory Forensics Agent"` must equal the `AgentTurn.agent`
  string emitted so existing turn-matching logic is not disturbed.
- Subtask 02 weight vectors are **provisional**; Task 08.0 ratifies the final
  floats and asserts each fault class's weights sum to 1.0.
- The Stop hook runs the unit suite; a red suite blocks ending the session.
