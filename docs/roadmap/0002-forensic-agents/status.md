# Milestone 0002 - Forensic Agents - Status

Tracks progress against [plan.md](/docs/roadmap/0002-forensic-agents/plan.md).
Updated as each task lands.

## Current status

| Task | Name                                  | Status                   | Tests |
|------|---------------------------------------|--------------------------|-------|
| 01.0 | Agent Package Restructure             | ✅ Complete               | 975   |
| 02.0 | Extensible Panel (Registry/Consensus) | ✅ Complete (superset)    | 975   |
| 03.0 | Memory Forensics Agent                | ✅ Complete               | 975   |
| 04.0 | Concurrency Analyst Agent             | ✅ Complete               | 975   |
| 05.0 | Exploitability Analyst Agent          | ✅ Complete               | 975   |
| 06.0 | Resource Exhaustion Agent             | ✅ Complete               | 975   |
| 07.0 | Remediation Planner Agent             | ✅ Complete               | 975   |
| 08.0 | Panel Integration, Docs & Hardening   | ✅ Complete               | 975   |

**Legend:** ✅ Complete · 🔶 In progress / partial · ⬜ Not started

**Current gate status:** All eight tasks complete. **0002 milestone closed
2026-07-10.** Full regression: 975 unit + 38 integration passing (7 skipped),
`ruff` clean. Security threat model:
`docs/security/2026-07-10-forensic-agents.md` (verdict: **PASS**, no findings).
Incident-analyst lifecycle gate: **PASS** (HITL always reachable; remediation
planner skipped on HITL; planner fails open). Ground-truth (Gate 3): not
executed — no crash dump available in this environment.

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

### Task 01.0 - Agent Package Restructure (✅ 2026-07-10)

**Delivered:**
- Moved the five base modules (`base.py`, `os_kernel.py`, `code_analyst.py`,
  `log_historian.py`, `skeptic.py`) into `src/aegis_swr/agents/base/` via
  `git mv` — pure renames, zero logic diff (`git diff -M --stat` confirms).
- Added `agents/base/__init__.py` re-exporting `BaseAgent`, `AgentSpec`,
  `AgentCategory`, and the four agent classes, with the category-convention
  table in its docstring.
- Rewrote the top-level `agents/__init__.py` to re-export the same seven names
  so `from aegis_swr.agents import OSKernelAgent` (etc.) still resolves
  (Approach A — no submodule shims needed; all in-repo consumers repointed).
- Scaffolded empty, importable `agents/forensic/` and `agents/synthesis/`
  category packages (`__all__ = []` + category docstrings).
- Repointed consumers: `agents/registry.py`, `core/orchestrator.py`, and the
  affected unit tests (`test_orchestrator.py`, `test_agents.py`,
  `test_agent_registry.py`) now import the four agents from
  `aegis_swr.agents.base`. No remaining references to the old submodule paths.

**Tests / gate:**
- New `tests/unit/test_agents_package.py` (5 tests): base-path import,
  shared-primitive re-export, top-level re-export, `forensic`/`synthesis`
  importable.
- Full unit suite green: **833 passed** (was 828 pre-task), 89.27% coverage.
  Integration suite: 27 passed, 7 skipped (unchanged).
- `ruff check` / `ruff format --check` clean.

### Task 02.0 - Extensible Panel (✅ 2026-07-10, superset)

Implemented earlier as the ratified "Dynamic Agent Roster" superset (see Notes
above). This session **verified** it against milestone contracts C2-C5 with a
code-review agent: all hold and the default-panel back-compat gate is intact.

**Established by:** `BaseAgent` identity ClassVars + `AgentSpec`
(`agents/base/base.py`); agent-count-agnostic `ConsensusEvaluator.calculate`
(`core/consensus.py`); `AGENT_REGISTRY`/`create_agent` (`agents/registry.py`);
`resolve_panel`/`resolve_consensus_weights` with exactly-one-arbiter enforcement
and unknown-key warn-and-skip (`agents/panel.py`); `PanelResolver` +
strategies (`core/panel_strategy.py`); per-run fresh-graph orchestrator
(`core/orchestrator.py`). Tests: `test_agent_registry.py`, `test_panel_strategy.py`,
`test_consensus.py`, `test_orchestrator.py`, `test_orchestrator_dynamic_panel.py`.

**Reconciliation note:** the roadmap's per-fault-class weight matrix
(`AgentWeightEntry.weights`) and `AgentPanelSettings.per_fault_class` were
superseded by intrinsic per-agent `default_weight` (self-normalized) + fault-aware
auto-selection (completed in Task 03.0). Subtasks `03/04/05`'s config-file design
does not apply; there is no `config/agents.example.json` / `config.yaml`.

### Task 03.0 - Memory Forensics Agent (✅ 2026-07-10)

**Delivered:**
- `MemoryForensicsOutput` schema (`core/schemas.py`): `hypotheses`,
  range-validated `confidence_score`, `corruption_signatures`,
  `suspected_allocation_site`, `heap_state`.
- `MemoryForensicsAgent` (`agents/forensic/memory_forensics.py`): ClassVars
  (`agent_key="memory_forensics"`, `category="forensic"`,
  `display_name="Memory Forensics Agent"`, `default_weight=0.25`, role
  INVESTIGATOR), a module-level `_SYSTEM_PROMPT`, and a **deterministic
  fill-pattern pre-check** - a module-compiled regex over `raw_text_excerpt` +
  JSON-serialized `stack_frames` for the known sentinels (`0xBAADF00D`,
  `0xFEEEFEEE`, `0xCCCCCCCC`, ...), string-only (no shell/SQL/eval sink), merged
  with (never overriding) the LLM's `corruption_signatures`.
- **Fault-aware panel selection** (`core/panel_strategy.py`): `AgenticManagerStrategy`
  now reads `brief.fault_class` and selects base agents always, forensic
  specialists only for their `authoritative_fault_classes`
  (new `BaseAgent` ClassVar), synthesis agents never. This completes the
  per-fault selection Task 02.0 deferred, and preserves 0001 back-compat (a
  None/non-memory fault ⇒ exactly the four base agents).
- Registered `memory_forensics` in `AGENT_REGISTRY`; exported from
  `agents/forensic/__init__.py`. Authoritative for `MEMORY_ACCESS_VIOLATION`,
  `NULL_POINTER_DEREFERENCE`, `USE_AFTER_FREE`.

**Tests / gate:**
- New `tests/unit/test_memory_forensics_agent.py` (20 tests: prompt content,
  ClassVars, pre-check detection/merge/clean, run() shape, token accounting,
  arbiter-correction propagation, mock pipeline).
- New `tests/integration/test_memory_forensics_integration.py` (2 tests: present
  in debate for a memory_access_violation incident; absent for a deadlock one).
- 4 new `MemoryForensicsOutput` schema tests; updated `test_panel_strategy.py`
  (fault-aware roster), `test_agent_registry.py`, `test_consensus.py` /
  `test_settings.py` (default-weight invariant scoped to base agents).
- Full unit suite **857 passed** (was 833), 89.25% coverage. Integration: 29
  passed, 7 skipped. `ruff check` clean; all created/edited files
  `ruff format`-clean; no `T | None` introduced.
- **Weights are provisional** (Task 08.0 ratifies the final authority matrix).

### Task 04.0 - Concurrency Analyst Agent (✅ 2026-07-10)

**Delivered:**
- `ConcurrencyAnalystOutput` schema (`core/schemas.py`): `wait_chain`,
  `lock_order_inversions`, `suspected_race` + range-validated `confidence_score`.
- `ConcurrencyAnalystAgent` (`agents/forensic/concurrency_analyst.py`): ClassVars
  (`concurrency_analyst`/forensic/"Concurrency Analyst Agent", `default_weight=0.30`),
  authoritative for `DEADLOCK`, `USE_AFTER_FREE`, `ASSERTION_FAILURE`, and a pure
  module-level `_extract_wait_chain_candidates(text)` **wait-chain pre-check**
  (regex/keyword only over blocking primitives: WaitForMultipleObjects,
  EnterCriticalSection, pthread_mutex, ...). Candidates fill an empty
  `wait_chain` (never overwrite a populated one) and are surfaced in the turn.
- Registered `concurrency_analyst`; exported from `agents/forensic/__init__.py`.

**Tests / gate:** new `test_concurrency_analyst.py` (19) + `test_concurrency_analyst_pipeline.py`
(2), 4 schema tests, updated panel/registry tests. Unit **897 passed**; integration
34 passed, 7 skipped. `ruff` clean; no `T | None`. Code-review agent: no issues.

### Task 05.0 - Exploitability Analyst Agent (✅ 2026-07-10, security-sensitive)

**Delivered:**
- `ExploitabilityOutput` schema (`core/schemas.py`): `exploitable: bool`,
  `severity: str`, `attacker_control: Optional[str]` (analyst prose - not raw
  payload), `mitigations_present`, range-validated `confidence_score`.
- `ExploitabilityAnalystAgent` (`agents/forensic/exploitability_analyst.py`):
  ClassVars (`exploitability`/forensic/"Exploitability Analyst Agent",
  `default_weight=0.20`), authoritative for `MEMORY_ACCESS_VIOLATION`,
  `USE_AFTER_FREE`, `STACK_OVERFLOW`, and a deterministic **access pre-check**
  (`_classify_access` read/write/unknown + `_classify_address`
  near_null/attacker_pattern/unknown_wild).
- **C7 compliance:** the pre-check logs only the *derived classification*
  (`access_type`/`address_class`) via `loguru.debug` - never the raw exception
  address. Verdict is an analyst assessment, not auto-remediation authorization.
- Registered `exploitability`; exported from `agents/forensic/__init__.py`.

**Tests / gate:** new `test_exploitability_analyst.py` (14, incl. the **mandatory
`test_no_raw_payload_in_logs`**) + `test_exploitability_pipeline.py` (3, incl.
`test_exploitable_true_does_not_trigger_auto_remediation`), 4 schema tests. Unit
**897 passed**; integration 34 passed, 7 skipped. `ruff` clean; no `T | None`.
Security-focused code-review agent: C7 upheld, no issues.

> **Reconciliation (04.0 & 05.0):** as with 03.0, the roadmap's per-fault-class
> weight matrix + `AgentPanelSettings.per_fault_class` + `config/agents.example.json`
> do not exist in the superset. Subtasks 02 & 04 were realized as the agent's
> intrinsic `default_weight` + `authoritative_fault_classes` fault-aware
> auto-selection. `USE_AFTER_FREE` is now co-authoritative for `memory_forensics`,
> `concurrency_analyst`, and `exploitability` (all self-normalized by the live panel).

### Task 06.0 - Resource Exhaustion Agent (✅ 2026-07-10)

**Delivered:**
- `ResourceExhaustionOutput` schema (`exhausted_resource`, `leak_indicators`,
  `growth_trend`).
- `ResourceExhaustionAgent` (`agents/forensic/resource_analyst.py`):
  `default_weight=0.30`; authoritative for `RESOURCE_EXHAUSTION`,
  `STACK_OVERFLOW`, `DEADLOCK`. Static, never-raising `_extract_leak_indicators`
  regex pre-check (OOM, too-many-open-files, `ERROR_NO_SYSTEM_RESOURCES`, handle
  counts, thread/connection-pool exhaustion, GDI/USER objects), trimmed to 200
  chars; `run()` always includes `log_summary` in context and merges pre-check
  indicators without dropping them.
- Registered `resource_exhaustion`; exported from `agents/forensic/__init__.py`.

**Tests / gate:** `test_resource_exhaustion_agent.py` (17) +
`test_resource_exhaustion_pipeline.py` + 4 schema tests. Code-review agent: no issues.

### Task 07.0 - Remediation Planner Agent (✅ 2026-07-10, synthesis tier)

**Delivered:**
- `RemediationStep` / `RemediationPlan` schemas with `model_validator`s
  (empty-rollback rejection, read-only-sentinel-vs-idempotent guard, non-empty
  contiguous 1-based ordering, low-confidence → `requires_human_approval`), and
  `RCAReport.remediation_plan: Optional[RemediationPlan]`.
- `RemediationPlannerAgent` (`agents/synthesis/remediation_planner.py`):
  `category="synthesis"`, `role=SYNTHESIS`, `default_weight=0.0`; `run()` raises
  `NotImplementedError`; `run_synthesis(report)` sends only safe RCA fields (no
  raw payload) and returns `(AgentTurn, RemediationPlan)`. Pure
  `remediation_plan_to_playbook_dict` adapter for `/playbook-validate`.
- **Orchestrator wiring:** `Orchestrator._synthesize_remediation` runs once from
  the convergence node when `panel.enabled_synthesis` contains
  `"remediation_planner"` (new `PanelRuntimeSettings.enabled_synthesis`, default
  `["remediation_planner"]`), attaches the plan via `model_copy`, emits an
  `AgentSpoke`, and **soft-fails** (plan stays `None`) on any error. The HITL path
  never calls it. Registered in `AGENT_REGISTRY` (filtered out of debate panels
  by category).

**Tests / gate:** `test_remediation_planner.py` (17: schema/agent/adapter/wiring)
+ `test_remediation_planner_integration.py` (3: converged→plan, HITL→no plan,
  playbook-compatible) + 8 schema tests. Code-review agent: HITL exclusion,
  soft-fail, and no-raw-payload confirmed.

> **Reconciliation (07.0):** the roadmap's `AgentPanelSettings.enabled_synthesis`
> became `Settings.panel.enabled_synthesis` (`PanelRuntimeSettings`); the
> synthesizer node is a closure, so the logic lives in the testable
> `Orchestrator._synthesize_remediation` method.

### Task 08.0 - Panel Integration, Docs & Hardening (✅ 2026-07-10, milestone exit)

**Delivered:**
- **Weight/panel audit** (`tests/unit/test_weight_audit.py`, 34 tests): every
  `FaultClass` auto-resolves to its ratified panel composition and order
  (authority matrix fully realized by `authoritative_fault_classes`), `skeptic`
  always last, default/base-only classes reproduce the legacy four, and resolved
  weights normalize to 1.0. The plan's authority matrix matches the code exactly.
- **Docs:** `docs/agent/agents.md` (nine-agent product roster table),
  `docs/config/agents.md` (forensic-specialist + synthesis weights and
  fault-aware selection), `docs/specs/agentic_fleet_design.md` §1 (Consensus +
  new Agent-panel glossary), `docs/README.md`/`docs/roadmap/README.md` (0002 →
  `status.md`).
- **Hardening gates:** Gate 1 regression **975 unit + 38 integration** passing;
  Gate 2 `ruff check`/`format` clean, no `T | None`; Gate 4 `security-auditor`
  **PASS** (`docs/security/2026-07-10-forensic-agents.md`, no findings); Gate 5
  incident-analyst lifecycle **PASS**; Gate 3 ground-truth not executed (no dump).

> **Reconciliation (08.0):** subtask 02's `agents.example.json` / `config.yaml`
> weight/panel files were **not** created — the superset removed
> `AgentWeightsSettings` / `AgentPanelSettings` entirely (weights intrinsic,
> panels code-driven; see ADR 0002). The weight audit asserts the authority
> matrix against the live code instead of a config file, which is the faithful
> equivalent for this architecture.

## As-built roster

| `agent_key`           | Class                        | Category  | Tier          | Module |
|-----------------------|------------------------------|-----------|---------------|--------|
| `os_kernel`           | `OSKernelAgent`              | base      | debate        | `agents/base/os_kernel.py` |
| `code_analyst`        | `CodeAnalystAgent`           | base      | debate        | `agents/base/code_analyst.py` |
| `log_historian`       | `LogHistorianAgent`          | base      | debate        | `agents/base/log_historian.py` |
| `skeptic`             | `SkepticAgent`               | base      | debate (last) | `agents/base/skeptic.py` |
| `memory_forensics`    | `MemoryForensicsAgent`       | forensic  | debate        | `agents/forensic/memory_forensics.py` |
| `concurrency_analyst` | `ConcurrencyAnalystAgent`    | forensic  | debate        | `agents/forensic/concurrency_analyst.py` |
| `exploitability`      | `ExploitabilityAnalystAgent` | forensic  | debate        | `agents/forensic/exploitability_analyst.py` |
| `resource_exhaustion` | `ResourceExhaustionAgent`    | forensic  | debate        | `agents/forensic/resource_analyst.py` |
| `remediation_planner` | `RemediationPlannerAgent`    | synthesis | post-debate   | `agents/synthesis/remediation_planner.py` |
