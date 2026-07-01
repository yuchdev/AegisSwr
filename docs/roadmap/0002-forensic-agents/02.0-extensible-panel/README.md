# Task 02.0 - Extensible Panel (Registry / Consensus / Orchestration)

**Parent milestone:** [Milestone 0002 - Forensic Agents](/docs/roadmap/0002-forensic-agents/plan.md)
**Status:** ⬜ Not started

## Scope

Turn the hard-coded four-agent panel into a **data-driven, registry-backed
panel** so specialist agents can be added by configuration. Three subsystems
change in lock-step:

1. **`BaseAgent`** gains identity `ClassVar`s (`agent_key`, `category`,
   `display_name`) so agents can be addressed generically.
2. **Consensus** (`AgentWeightEntry` / `ConsensusEvaluator`) moves from four
   fixed float fields to a `dict[str, float]` weight map keyed by `agent_key`.
3. **Orchestrator** builds its debate sub-graph dynamically from a panel returned
   by a new `create_agent_panel()` factory, instead of wiring four fixed nodes.

The non-negotiable property of this task: **with no specialists enabled, behavior
is byte-identical to Milestone 0001** - same node chain, same consensus numbers.

See the authoritative contracts C2–C5 in the
[milestone plan](/docs/roadmap/0002-forensic-agents/plan.md#shared-contracts-authoritative).

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Generalize `BaseAgent`](01-generalize-base-agent.md) | ⬜ Not started | 03, 04 |
| 02 | [Data-driven consensus weights](02-consensus-weight-map.md) | ⬜ Not started | 04 |
| 03 | [Agent registry & panel factory](03-registry-and-panel-factory.md) | ⬜ Not started | 04 |
| 04 | [Dynamic orchestrator panel](04-orchestrator-dynamic-panel.md) | ⬜ Not started | 06 |
| 05 | [Config model & examples](05-config-model.md) | ⬜ Not started | 06 |
| 06 | [Tests](06-tests.md) | ⬜ Not started | - |

Subtasks 01, 02, 03 are largely independent and may proceed in parallel; 04
depends on all three; 05 can land alongside 03; 06 gates the task.

## Key constraints

- **Back-compat gate.** Default config ⇒ default panel ⇒ legacy chain
  (`os_kernel → code_analyst → log_historian → skeptic`) and the exact 0001
  weight matrix.
- **Skeptic stays terminal.** Whatever the panel, `skeptic` is always the last
  debate node and keeps the `_route_after_skeptic` conditional edges.
- **Synthesis agents are not voters** and are never returned by
  `create_agent_panel` (Task 07.0 wires the planner into the synthesizer path).
- `mypy --strict`, `ruff`, `Optional[T]` clean.
