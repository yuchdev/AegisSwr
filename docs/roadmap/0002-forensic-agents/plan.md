# Milestone 0002 - Forensic Agents

**Package:** `aegis-swr` | **Module root:** `src/aegis_swr/agents/`
**Depends on:** Milestone 0001 (Multi-Agent System engine, schemas, consensus, orchestrator)

This milestone grows the **Synthetic War Room** from the four generalist base
agents (`os_kernel`, `code_analyst`, `log_historian`, `skeptic`) into a richer,
**composable panel** of specialist *forensic* agents plus a *synthesis*-tier
remediation planner. It is primarily an `src/aegis_swr/agents/*.py`
implementation effort, but it begins with two infrastructure tasks because the
current code **hard-wires exactly four agents** and cannot accept new ones
without refactoring first.

> **Why the infrastructure tasks come first.** `core/consensus.py` keys on a
> fixed tuple `("os_kernel", "code_analyst", "log_historian", "skeptic")`,
> `AgentWeightEntry` has one `float` field per agent, and `core/orchestrator.py`
> registers four fixed nodes in a linear chain. Adding agents is therefore not
> "write one file" - the panel must first become *data-driven*.

## Table of contents

- [Tasks](#tasks)
- [Target agent package layout](#target-agent-package-layout)
- [Shared contracts (authoritative)](#shared-contracts-authoritative)
- [Per-task specifications](#per-task-specifications)
- [Specialist → fault-class authority matrix](#specialist--fault-class-authority-matrix)
- [Dependency graph](#dependency-graph)

---

## Tasks

| Task  | Name                                  | Category       | Output                                                                       |
|-------|---------------------------------------|----------------|------------------------------------------------------------------------------|
| 01.0  | Agent Package Restructure             | infrastructure | Move base agents into `agents/base/`; scaffold `forensic/`, `synthesis/`     |
| 02.0  | Extensible Panel (Registry/Consensus) | infrastructure | Data-driven consensus weights, agent registry, dynamic orchestrator panel    |
| 03.0  | Memory Forensics Agent                | forensic       | `agents/forensic/memory_forensics.py`; heap-corruption specialist            |
| 04.0  | Concurrency Analyst Agent             | forensic       | `agents/forensic/concurrency_analyst.py`; deadlock/race specialist           |
| 05.0  | Exploitability Analyst Agent          | forensic       | `agents/forensic/exploitability_analyst.py`; vuln/exploit-assessment agent   |
| 06.0  | Resource Exhaustion Agent             | forensic       | `agents/forensic/resource_analyst.py`; leak/OOM specialist                   |
| 07.0  | Remediation Planner Agent             | synthesis      | `agents/synthesis/remediation_planner.py`; ordered, rollback-covered plan    |
| 08.0  | Panel Integration, Docs & Hardening   | integration    | Default per-fault panels, config/examples, docs, regression, directory tree  |

Tasks 01.0 → 02.0 are sequential foundations. Tasks 03.0–06.0 (the four forensic
specialists) share an identical subtask shape and may proceed **in parallel**
once 02.0 lands. Task 07.0 depends on 02.0. Task 08.0 closes the milestone.

---

## Target agent package layout

```
src/aegis_swr/agents/
  __init__.py                      # back-compat re-exports + create_agent_panel
  registry.py                      # AGENT_REGISTRY, create_agent_panel()
  base/
    __init__.py                    # re-exports BaseAgent + the four base agents
    base.py                        # generalized BaseAgent (agent_key/category/display_name)
    os_kernel.py                   # OSKernelAgent          (moved)
    code_analyst.py                # CodeAnalystAgent       (moved)
    log_historian.py               # LogHistorianAgent      (moved)
    skeptic.py                     # SkepticAgent           (moved)
  forensic/
    __init__.py
    memory_forensics.py            # MemoryForensicsAgent       (Task 03.0)
    concurrency_analyst.py         # ConcurrencyAnalystAgent    (Task 04.0)
    exploitability_analyst.py      # ExploitabilityAnalystAgent (Task 05.0)
    resource_analyst.py            # ResourceExhaustionAgent    (Task 06.0)
  synthesis/
    __init__.py
    remediation_planner.py         # RemediationPlannerAgent    (Task 07.0)
```

---

## Shared contracts (authoritative)

These contracts are defined once here and referenced by every subtask. Changing
one means updating this section and the affected subtask specs.

### C1 - Canonical agent keys

| `agent_key`           | Class                        | Category   | Tier   |
|-----------------------|------------------------------|------------|--------|
| `os_kernel`           | `OSKernelAgent`              | base       | debate |
| `code_analyst`        | `CodeAnalystAgent`           | base       | debate |
| `log_historian`       | `LogHistorianAgent`          | base       | debate |
| `skeptic`             | `SkepticAgent`               | base       | debate (always last) |
| `memory_forensics`    | `MemoryForensicsAgent`       | forensic   | debate |
| `concurrency_analyst` | `ConcurrencyAnalystAgent`    | forensic   | debate |
| `exploitability`      | `ExploitabilityAnalystAgent` | forensic   | debate |
| `resource_exhaustion` | `ResourceExhaustionAgent`    | forensic   | debate |
| `remediation_planner` | `RemediationPlannerAgent`    | synthesis  | post-debate |

### C2 - Generalized `BaseAgent`

`agents/base/base.py` keeps the existing constructor and `run`/`system_prompt`
contract and adds three `ClassVar`s so the registry and consensus can address
agents generically:

```python
class BaseAgent(ABC):
    agent_key: ClassVar[str]        # canonical key from C1, e.g. "memory_forensics"
    category: ClassVar[str]         # "base" | "forensic" | "synthesis"
    display_name: ClassVar[str]     # human label, e.g. "Memory Forensics Agent"
```

`display_name` MUST equal the `AgentTurn.agent` string the agent already emits
(e.g. `"OS Kernel Agent"`), so existing turn-matching logic keeps working.

### C3 - Data-driven consensus weights

`AgentWeightEntry` stops being four fixed float fields and becomes a single
normalized map keyed by `agent_key`:

```python
class AgentWeightEntry(BaseSettings):
    weights: dict[str, float] = Field(default_factory=dict)
    # validator: drop unknown keys is NOT done here; missing keys read as 0.0
```

`ConsensusEvaluator.calculate(agent_scores, fault_class)` iterates the union of
keys present in the entry's `weights` (skipping `remediation_planner`, which is
not a voter - see C5). The legacy four-field constructor signature
(`AgentWeightEntry(os_kernel=…, code_analyst=…, …)`) is preserved as a
compatibility shim that folds kwargs into `weights`. **Default weights for the
existing ten fault classes reproduce 0001's matrix exactly** (back-compat gate).

### C4 - Agent registry & panel factory

`agents/registry.py`:

```python
AGENT_REGISTRY: dict[str, type[BaseAgent]]    # agent_key -> class, from C1

def create_agent_panel(
    ai_backend: AIAPIBackend,
    settings: Settings,
    fault_class: Optional[FaultClass] = None,
) -> list[BaseAgent]:
    """Return the ordered *debate* panel (synthesis agents excluded).

    Order invariant: skeptic is always last; remaining debate agents follow
    their configured order. fault_class selects the per-fault panel override
    when one is configured, else the default panel.
    """
```

Synthesis-tier agents (`remediation_planner`) are **never** returned by
`create_agent_panel`; they are instantiated separately by the orchestrator's
output-synthesizer path.

### C5 - Orchestrator integration

- The debate sub-graph is built **dynamically** from `create_agent_panel(...)`:
  one node per panel agent, chained in panel order, `skeptic_node` terminal with
  the existing `_route_after_skeptic` conditional edges. The fixed
  `os_kernel → code_analyst → log_historian → skeptic` chain is replaced by the
  panel sequence; the **default panel must reproduce that exact chain** so 0001
  behavior is unchanged when no specialists are enabled.
- `remediation_planner` runs **once** inside `output_synthesizer_node`, after
  convergence/skeptic confirmation, consuming the confirmed `RCAReport`. It is
  skipped on the HITL (low-confidence) path.

### C6 - Output schemas (`core/schemas.py`)

Each debate specialist mirrors the existing `OSKernelOutput` shape (a list of
`Hypothesis` + a `confidence_score: float`) and adds domain-specific fields:
`MemoryForensicsOutput`, `ConcurrencyAnalystOutput`, `ExploitabilityOutput`,
`ResourceExhaustionOutput`. The synthesis agent adds `RemediationStep` +
`RemediationPlan`, and `RCAReport` gains an optional `remediation_plan` field.

### C7 - Cross-cutting project invariants (inherited from 0001)

- `Optional[T]` from `typing`, never `T | None` (run `scripts/replace_optional.py --check`).
- `mypy --strict` clean; `ruff` clean.
- Mandatory `cache_control: {"type": "ephemeral"}` on every system prompt block
  (handled by `_BaseAIBackend`; agents pass the system prompt through).
- **Untrusted payload text** (stack frames, log lines, register values) flows
  into prompts only after the Data Adapter's PII scrub - agents never re-introduce
  raw payload into a shell, SQL, or unsanitised sink.
- Every new feature ships unit + mock tests; every integration ships an
  integration test with mocked externals. The Stop hook runs the unit suite.

---

## Per-task specifications

### Task 01.0 - Agent Package Restructure

**Goal:** Reorganize `agents/` into category subpackages with **zero behavior
change**. This is the enabling move the rest of the milestone builds on.

**Subtasks:** see [`01.0-agent-package-restructure/README.md`](/docs/roadmap/0002-forensic-agents/01.0-agent-package-restructure/README.md)

| # | Subtask | Summary |
|---|---------|---------|
| 01 | Move base agents into `agents/base/` | Move `base.py` + four agent modules; fix intra-package imports |
| 02 | Update consumers & back-compat shims | Repoint `orchestrator.py`, tests; `agents/__init__.py` re-exports old paths |
| 03 | Scaffold `forensic/` & `synthesis/` packages | Empty packages + `category` convention + `agents/base/__init__.py` |
| 04 | Regression gate | Full suite green; import-path tests; mypy/ruff clean |

**Success criteria:** all 478+ existing tests pass unchanged; `from
aegis_swr.agents.os_kernel import OSKernelAgent` still resolves (shim);
`from aegis_swr.agents.base import OSKernelAgent` resolves (new home).

---

### Task 02.0 - Extensible Panel (Registry / Consensus / Orchestration)

**Goal:** Make the panel data-driven so agents can be added by configuration.

**Subtasks:** see [`02.0-extensible-panel/README.md`](/docs/roadmap/0002-forensic-agents/02.0-extensible-panel/README.md)

| # | Subtask | Summary |
|---|---------|---------|
| 01 | Generalize `BaseAgent` (C2) | Add `agent_key`/`category`/`display_name` `ClassVar`s to the four base agents |
| 02 | Data-driven consensus weights (C3) | `AgentWeightEntry.weights` map + legacy-kwargs shim; iterate the panel |
| 03 | Agent registry & panel factory (C4) | `agents/registry.py`; `AgentPanelSettings`; `create_agent_panel` |
| 04 | Dynamic orchestrator panel (C5) | Build debate nodes from the panel; default panel == legacy chain |
| 05 | Config model & examples | `agents.example.json` / `config.yaml` panel + weights schema |
| 06 | Tests | Consensus with N agents; registry; orchestrator with a variable panel; back-compat |

**Success criteria:** with no specialists enabled the orchestrator and consensus
produce byte-identical results to 0001; with a specialist enabled it appears as a
debate node and contributes a weighted vote.

---

### Tasks 03.0–06.0 - Forensic specialists (shared shape)

Each forensic-specialist task has the **same five subtasks**. The per-task README
fills in the domain content (system prompt heuristics, output fields, authoritative
fault classes).

| # | Subtask | Summary |
|---|---------|---------|
| 01 | Output schema (C6) | New `*Output` model in `core/schemas.py` + schema tests |
| 02 | Consensus weight integration (C3) | Add the agent's `agent_key` weight to its authoritative fault classes; re-normalize |
| 03 | Agent implementation | `system_prompt` + `run()` with domain pre-checks and heuristics |
| 04 | Registry & panel wiring (C4/C5) | Register in `AGENT_REGISTRY`; add to default panels for authoritative fault classes |
| 05 | Tests | Unit (schema request, prompt content, deterministic pre-checks), mock pipeline, integration |

#### Task 03.0 - Memory Forensics Agent
`agents/forensic/memory_forensics.py` → `MemoryForensicsAgent` (`memory_forensics`).
Specialism: heap corruption, use-after-free, double-free, buffer over/underflow,
allocator/heap-metadata tells, guard-page hits, fill-pattern signatures
(`0xCCCC…`/`0xFEEEFEEE`/`0xBAADF00D`). Authoritative on `memory_access_violation`,
`null_pointer_dereference`, `use_after_free`. Output adds
`corruption_signatures: list[str]`, `suspected_allocation_site: Optional[str]`,
`heap_state: Optional[str]`.
See [`03.0-memory-forensics-agent/README.md`](/docs/roadmap/0002-forensic-agents/03.0-memory-forensics-agent/README.md).

#### Task 04.0 - Concurrency Analyst Agent
`agents/forensic/concurrency_analyst.py` → `ConcurrencyAnalystAgent`
(`concurrency_analyst`). Specialism: deadlocks, lock-ordering inversions, race
conditions, TOCTOU, thread wait-chains, starvation. Authoritative on `deadlock`,
`use_after_free` (race-induced), `assertion_failure`. Output adds
`wait_chain: list[str]`, `lock_order_inversions: list[str]`,
`suspected_race: Optional[str]`.
See [`04.0-concurrency-analyst-agent/README.md`](/docs/roadmap/0002-forensic-agents/04.0-concurrency-analyst-agent/README.md).

#### Task 05.0 - Exploitability Analyst Agent
`agents/forensic/exploitability_analyst.py` → `ExploitabilityAnalystAgent`
(`exploitability`). Specialism: is the crash a security vulnerability? Whether
attacker-controlled data reaches the fault, write-what-where primitives,
control-flow hijack potential, mitigation state (ASLR/DEP/stack canary).
Authoritative on `memory_access_violation`, `use_after_free`, `stack_overflow`.
Output adds `exploitable: bool`, `severity: str`, `attacker_control: Optional[str]`,
`mitigations_present: list[str]`. **Security-sensitive - Task 08 requires a
`security-auditor` pass** (this agent reasons over attacker-influenced payload).
See [`05.0-exploitability-analyst-agent/README.md`](/docs/roadmap/0002-forensic-agents/05.0-exploitability-analyst-agent/README.md).

#### Task 06.0 - Resource Exhaustion Agent
`agents/forensic/resource_analyst.py` → `ResourceExhaustionAgent`
(`resource_exhaustion`). Specialism: handle/fd/thread/memory leaks, OOM,
connection-pool and GDI/kernel-object exhaustion, unbounded growth - the "silent
logical lockup / resource leak" gap from the product roadmap §1.1. Authoritative
on `resource_exhaustion`, `stack_overflow`, `deadlock` (thread starvation).
Output adds `exhausted_resource: Optional[str]`, `leak_indicators: list[str]`,
`growth_trend: Optional[str]`.
See [`06.0-resource-exhaustion-agent/README.md`](/docs/roadmap/0002-forensic-agents/06.0-resource-exhaustion-agent/README.md).

---

### Task 07.0 - Remediation Planner Agent (synthesis tier)

**Goal:** Turn the confirmed RCA into an ordered, **idempotent, rollback-covered**
remediation playbook, compatible with the `/playbook-validate` skill.

**Subtasks:** see [`07.0-remediation-planner-agent/README.md`](/docs/roadmap/0002-forensic-agents/07.0-remediation-planner-agent/README.md)

| # | Subtask | Summary |
|---|---------|---------|
| 01 | `RemediationPlan` / `RemediationStep` schema | New models in `core/schemas.py`; `RCAReport.remediation_plan` optional field |
| 02 | Agent implementation | `system_prompt` + `run()` consuming the confirmed `RCAReport`; step ordering + rollback per step |
| 03 | Synthesis-tier wiring (C5) | Invoked in `output_synthesizer_node` post-convergence; skipped on the HITL path |
| 04 | `/playbook-validate` alignment | Output shape passes the playbook validator; HITL when synthesis confidence is low |
| 05 | Tests | Unit, mock, integration; idempotency/rollback assertions; playbook-validate run |

**Success criteria:** a converged investigation yields an `RCAReport` whose
`remediation_plan` validates under `/playbook-validate`; a HITL outcome carries
**no** remediation plan (escalate, don't auto-remediate).

---

### Task 08.0 - Panel Integration, Docs & Hardening

**Goal:** Compose the full default panels, finalize config, document the roster,
and run the milestone exit gates.

**Subtasks:** see [`08.0-panel-integration-and-docs/README.md`](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/README.md)

| # | Subtask | Summary |
|---|---------|---------|
| 01 | Default per-fault panels & weight audit | Finalize the [authority matrix](#specialist--fault-class-authority-matrix); assert weights sum sanely |
| 02 | Config & examples | `agents.example.json`, `config.yaml`, `.env.example` (if any new keys) |
| 03 | Docs | Product roster in `docs/agent/agents.md`/`docs/config/agents.md`; `docs/specs/agentic_fleet_design.md` glossary; `docs/README.md` index |
| 04 | Hardening gates | Full regression + ground-truth; `security-auditor` (Task 05 surface) + `incident-analyst` (consensus/escalation) passes |
| 05 | Milestone closeout | Write the final directory tree; flip `status.md` to ✅; update roadmap index |

---

## Specialist → fault-class authority matrix

Default debate-panel membership and **primary** weight share per fault class.
Base agents always participate; a ✓ marks a specialist that joins the panel and
carries meaningful weight for that fault class. Task 08.0 ratifies the exact
floats; the rule is *re-normalize so each fault class's debate weights sum to 1.0*.

| FaultClass                 | memory_forensics | concurrency_analyst | exploitability | resource_exhaustion |
|----------------------------|:----------------:|:-------------------:|:--------------:|:-------------------:|
| memory_access_violation    | ✓ (primary)      |                     | ✓              |                     |
| null_pointer_dereference   | ✓                |                     |                |                     |
| use_after_free             | ✓ (primary)      | ✓                   | ✓              |                     |
| stack_overflow             |                  |                     | ✓              | ✓                   |
| integer_divide_by_zero     |                  |                     |                |                     |
| deadlock                   |                  | ✓ (primary)         |                | ✓                   |
| assertion_failure          |                  | ✓                   |                |                     |
| resource_exhaustion        |                  |                     |                | ✓ (primary)         |
| unhandled_exception        |                  |                     |                |                     |
| unknown                    | (base panel only)|                     |                |                     |

`remediation_planner` is **not** in this matrix - it is a post-debate synthesis
agent, not a weighted voter.

---

## Dependency graph

```
Task 01.0 (Restructure)
   │
   └──► Task 02.0 (Extensible Panel)         ← registry/consensus/orchestrator
           │
           ├──► Task 03.0 (Memory Forensics)        ┐
           ├──► Task 04.0 (Concurrency Analyst)     │  parallel
           ├──► Task 05.0 (Exploitability)          │  (shared shape)
           ├──► Task 06.0 (Resource Exhaustion)     ┘
           │
           └──► Task 07.0 (Remediation Planner)     ← synthesis tier
                   │
   Tasks 03–07 ────┴──► Task 08.0 (Integration, Docs & Hardening)   ← milestone exit
```

**Minimum viable forensic panel:** 01.0 → 02.0 → any one specialist → 08.0.
**Full milestone:** all eight tasks.
