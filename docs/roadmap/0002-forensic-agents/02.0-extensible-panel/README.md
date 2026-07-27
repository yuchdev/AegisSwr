# Task 02.0 - Extensible Panel (Registry / Consensus / Orchestration)

**Parent milestone:** [Milestone 0002 - Forensic Agents](/docs/roadmap/0002-forensic-agents/plan.md)
**Status:** ✅ Complete (implemented as ratified superset — see
[status.md](/docs/roadmap/0002-forensic-agents/status.md))

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
| 01 | [Generalize `BaseAgent`](01-generalize-base-agent.md) | ✅ Complete | 03, 04 |
| 02 | [Data-driven consensus weights](02-consensus-weight-map.md) | ✅ Complete (superset) | 04 |
| 03 | [Agent registry & panel factory](03-registry-and-panel-factory.md) | ✅ Complete (superset) | 04 |
| 04 | [Dynamic orchestrator panel](04-orchestrator-dynamic-panel.md) | ✅ Complete (superset) | 06 |
| 05 | [Config model & examples](05-config-model.md) | ✅ Complete (superset) | 06 |
| 06 | [Tests](06-tests.md) | ✅ Complete | - |

> **Implemented as a ratified superset** (the "Dynamic Agent Roster" redesign),
> not the literal decomposition above: `create_agent_panel(fault_class)` +
> `AgentWeightEntry.weights` + `AgentPanelSettings` were superseded by
> `resolve_panel`/`resolve_consensus_weights`, intrinsic per-agent
> `default_weight`, `PanelResolver`/strategies, and a per-run fresh graph.
> Verified against contracts C2-C5 by a code-review agent. See
> [status.md](/docs/roadmap/0002-forensic-agents/status.md).

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
- `ruff`, `replace_optional.py --check`, `Optional[T]` clean.
