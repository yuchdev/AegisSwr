# Milestone 0002 - Forensic Agents - Status

Tracks progress against [plan.md](/docs/roadmap/0002-forensic-agents/plan.md).
Updated as each task lands.

## Current status

| Task  | Name                                  | Status         | Tests |
|-------|---------------------------------------|----------------|-------|
| 01.0  | Agent Package Restructure             | ⬜ Not started | -     |
| 02.0  | Extensible Panel (Registry/Consensus) | ✅ Superseded (see Notes) | 538 |
| 03.0  | Memory Forensics Agent                | ⬜ Not started | -     |
| 04.0  | Concurrency Analyst Agent             | ⬜ Not started | -     |
| 05.0  | Exploitability Analyst Agent          | ⬜ Not started | -     |
| 06.0  | Resource Exhaustion Agent             | ⬜ Not started | -     |
| 07.0  | Remediation Planner Agent             | ⬜ Not started | -     |
| 08.0  | Panel Integration, Docs & Hardening   | ⬜ Not started | -     |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** Task 02.0 (Extensible Panel) has been superseded and
implemented outside this milestone's original decomposition — see below. Tasks
01.0 and 03.0-08.0 remain "Not started" as originally decomposed.

## Notes & decisions

- **Task 02.0 superseded (2026-07-07):** the "Dynamic Agent Roster" redesign
  (plan: `/Users/atatat/.claude/plans/orchestrator-src-aegis-swr-core-orchestr-wondrous-harp.md`)
  implements a superset of Task 02.0's scope directly in `src/aegis_swr/` -
  `BaseAgent` ClassVars (`agent_key`/`display_name`/`category`/`role`/
  `contributes_fix`), `AGENT_REGISTRY`/`create_agent` (`agents/registry.py`),
  `resolve_panel`/`resolve_consensus_weights` (`agents/panel.py`), and
  `PanelResolver`/`ExplicitPanelStrategy`/`AgenticManagerStrategy`
  (`core/panel_strategy.py`) - plus a per-agent `priority`/`weight` model
  (`AgentSpec`) and an `AgentRole` (`INVESTIGATOR`/`ARBITER`/`SYNTHESIS`)
  invariant (exactly one `ARBITER` per panel) that Task 02.0's original spec
  did not have. `core/orchestrator.py` now builds a fresh LangGraph per run
  from the resolved panel instead of a static 4-node chain. The default
  (no-explicit-panel) behavior remains byte-identical to Milestone 0001's
  `os_kernel -> code_analyst -> log_historian -> skeptic` chain and weight
  matrix - verified by `tests/integration/test_orchestrator_dynamic_panel.py`.
  **Disposition of `02.0-extensible-panel/*.md`:** `01-generalize-base-agent.md`
  and `02-consensus-weight-map.md` were consumed near-verbatim;
  `03-registry-and-panel-factory.md`'s single `create_agent_panel(fault_class)`
  factory was superseded by the `resolve_panel(specs)` + `PanelResolver` split
  (needed for explicit-vs-auto selection); `04-orchestrator-dynamic-panel.md`'s
  "union default panel + no-op specialist nodes" workaround was superseded by
  building the graph fresh per run once the panel is known; `05-config-model.md`'s
  single `AgentPanelSettings` was superseded by an ops-static (`agents.json`:
  `weights` + `panel`) vs. runtime-explicit (`config.json`: `Settings.panel`)
  split. Tasks 03.0-08.0 (the four forensic specialists + remediation planner)
  are unaffected in scope and will register into `AGENT_REGISTRY` once
  implemented.
- **Roster (ratified 2026-06-29):** four `forensic/` specialists
  (`memory_forensics`, `concurrency_analyst`, `exploitability`,
  `resource_exhaustion`) + one `synthesis/` agent (`remediation_planner`).
- **Back-compat is a hard gate.** Tasks 01.0 and 02.0 must leave the default
  (no-specialist) panel byte-identical to 0001 - `create_agent_panel` with the
  default config reproduces `os_kernel → code_analyst → log_historian → skeptic`,
  and the default consensus weights reproduce the 0001 matrix exactly.
- **Security/lifecycle gates (Task 08.0):** the Exploitability agent reasons over
  attacker-influenced payload → requires a `security-auditor` pass; the consensus
  and panel changes touch escalation → require an `incident-analyst` pass.

## Decomposition tree (as built)

The milestone is decomposed into **8 tasks / 40 subtasks** (50 Markdown files
total, including `plan.md` and this `status.md`). Link-check: 0 problems.

```
docs/roadmap/0002-forensic-agents/
├── plan.md                                   ← milestone spec (## Tasks, contracts C1–C7)
├── status.md                                 ← this tracker
├── 01.0-agent-package-restructure/           ← infrastructure
│   ├── README.md
│   ├── 01-move-base-agents.md
│   ├── 02-consumers-and-shims.md
│   ├── 03-scaffold-categories.md
│   └── 04-regression-gate.md
├── 02.0-extensible-panel/                     ← infrastructure (registry/consensus/orchestration)
│   ├── README.md
│   ├── 01-generalize-base-agent.md
│   ├── 02-consensus-weight-map.md
│   ├── 03-registry-and-panel-factory.md
│   ├── 04-orchestrator-dynamic-panel.md
│   ├── 05-config-model.md
│   └── 06-tests.md
├── 03.0-memory-forensics-agent/              ← forensic specialist
│   ├── README.md · 01-output-schema · 02-consensus-weights
│   ├── 03-agent-implementation · 04-registry-and-panel-wiring · 05-tests
├── 04.0-concurrency-analyst-agent/           ← forensic specialist
│   ├── README.md · 01-output-schema · 02-consensus-weights
│   ├── 03-agent-implementation · 04-registry-and-panel-wiring · 05-tests
├── 05.0-exploitability-analyst-agent/        ← forensic specialist (security-sensitive)
│   ├── README.md · 01-output-schema · 02-consensus-weights
│   ├── 03-agent-implementation · 04-registry-and-panel-wiring · 05-tests
├── 06.0-resource-exhaustion-agent/           ← forensic specialist
│   ├── README.md · 01-output-schema · 02-consensus-weights
│   ├── 03-agent-implementation · 04-registry-and-panel-wiring · 05-tests
├── 07.0-remediation-planner-agent/           ← synthesis tier
│   ├── README.md · 01-remediation-schema · 02-agent-implementation
│   ├── 03-synthesis-wiring · 04-playbook-validate-alignment · 05-tests
└── 08.0-panel-integration-and-docs/          ← integration & milestone closeout
    ├── README.md · 01-default-panels-and-weight-audit · 02-config-and-examples
    ├── 03-docs · 04-hardening-gates · 05-milestone-closeout
```

### Target `src/aegis_swr/agents/` layout (built by the tasks above)

```
src/aegis_swr/agents/
├── __init__.py                 # back-compat re-exports + create_agent_panel        (01.0/02.0)
├── registry.py                 # AGENT_REGISTRY, create_agent_panel()               (02.0)
├── base/                       # moved from agents/*.py                             (01.0)
│   ├── __init__.py
│   ├── base.py                 # generalized BaseAgent (agent_key/category/display)  (02.0)
│   ├── os_kernel.py · code_analyst.py · log_historian.py · skeptic.py
├── forensic/                                                                          (03.0–06.0)
│   ├── __init__.py
│   ├── memory_forensics.py        # MemoryForensicsAgent       (03.0)
│   ├── concurrency_analyst.py     # ConcurrencyAnalystAgent    (04.0)
│   ├── exploitability_analyst.py  # ExploitabilityAnalystAgent (05.0)
│   └── resource_analyst.py        # ResourceExhaustionAgent    (06.0)
└── synthesis/                                                                         (07.0)
    ├── __init__.py
    └── remediation_planner.py     # RemediationPlannerAgent    (07.0)
```

## Per-task detail

_Filled in as tasks complete (mirror the 0001 status.md format: Delivered list +
test coverage summary per task)._
