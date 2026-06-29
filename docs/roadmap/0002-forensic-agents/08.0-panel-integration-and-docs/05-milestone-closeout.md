# 05 — Milestone Closeout

**Parent task:** Task 08.0 — Panel Integration, Docs & Hardening
**Status:** ⬜ Not started
**Depends on:** 01-default-panels-and-weight-audit.md, 02-config-and-examples.md,
               03-docs.md, 04-hardening-gates.md
**Blocks:** nothing (milestone exit)

---

## Objective

Record the as-built state of Milestone 0002 and close the milestone by editing
the two tracker documents listed below. This subtask is **purely editorial** —
no `src/` files are modified.

The implementer (`docs-updater`) performs the edits described here once all
four preceding subtasks and all hardening gates are green.

---

## As-built roster

The full nine-agent roster delivered by this milestone:

| `agent_key`           | Class                          | Category  | Tier         | Module path |
|-----------------------|--------------------------------|-----------|--------------|-------------|
| `os_kernel`           | `OSKernelAgent`                | base      | debate       | `agents/base/os_kernel.py` |
| `code_analyst`        | `CodeAnalystAgent`             | base      | debate       | `agents/base/code_analyst.py` |
| `log_historian`       | `LogHistorianAgent`            | base      | debate       | `agents/base/log_historian.py` |
| `skeptic`             | `SkepticAgent`                 | base      | debate (last)| `agents/base/skeptic.py` |
| `memory_forensics`    | `MemoryForensicsAgent`         | forensic  | debate       | `agents/forensic/memory_forensics.py` |
| `concurrency_analyst` | `ConcurrencyAnalystAgent`      | forensic  | debate       | `agents/forensic/concurrency_analyst.py` |
| `exploitability`      | `ExploitabilityAnalystAgent`   | forensic  | debate       | `agents/forensic/exploitability_analyst.py` |
| `resource_exhaustion` | `ResourceExhaustionAgent`      | forensic  | debate       | `agents/forensic/resource_analyst.py` |
| `remediation_planner` | `RemediationPlannerAgent`      | synthesis | post-debate  | `agents/synthesis/remediation_planner.py` |

---

## As-built package layout

The final directory tree to record in `status.md`:

```
src/aegis_swr/agents/
  __init__.py                        # back-compat re-exports + create_agent_panel
  registry.py                        # AGENT_REGISTRY, create_agent_panel()
  base/
    __init__.py                      # re-exports BaseAgent + four base agents
    base.py                          # BaseAgent ABC (agent_key/category/display_name)
    os_kernel.py                     # OSKernelAgent          (moved from agents/)
    code_analyst.py                  # CodeAnalystAgent       (moved from agents/)
    log_historian.py                 # LogHistorianAgent      (moved from agents/)
    skeptic.py                       # SkepticAgent           (moved from agents/)
  forensic/
    __init__.py
    memory_forensics.py              # MemoryForensicsAgent       (Task 03.0)
    concurrency_analyst.py           # ConcurrencyAnalystAgent    (Task 04.0)
    exploitability_analyst.py        # ExploitabilityAnalystAgent (Task 05.0)
    resource_analyst.py              # ResourceExhaustionAgent    (Task 06.0)
  synthesis/
    __init__.py
    remediation_planner.py           # RemediationPlannerAgent    (Task 07.0)
```

---

## As-built weight matrix

Copy the final ratified weight table from subtask 01 here for permanent record.
If the ground-truth run (Gate 3 of subtask 04) produced a different consensus
score than expected, note any per-fault-class weight adjustments made after that
run. If no adjustments were made, write "Weight matrix unchanged from subtask 01
ratification."

---

## Edits to perform

### Edit 1 — `docs/roadmap/0002-forensic-agents/status.md`

The implementer must:

1. Flip every task row in the `## Current status` table from `⬜ Not started`
   to `✅ Complete`.
2. Update the `Tests` column for each task with the canonical test file names
   (draw from the per-task subtask specs).
3. Update the `**Current gate status:**` paragraph to read:
   "All eight tasks complete. 0002 milestone closed YYYY-MM-DD. Security threat
   model: `docs/security/YYYY-MM-DD-forensic-agents.md` (verdict: PASS or
   PASS_WITH_FOLLOWUP). Incident-analyst lifecycle gate: PASS."
4. Populate the `## Per-task detail` section with one block per task following
   the 0001 `status.md` format: a "Delivered:" bullet list and a test coverage
   line. Source the content from each task's README.md and subtask files.

The completed `## Current status` table should read:

| Task  | Name                                  | Status       | Tests |
|-------|---------------------------------------|--------------|-------|
| 01.0  | Agent Package Restructure             | ✅ Complete  | `test_agents.py` (import paths), `test_orchestrator.py` (shim) |
| 02.0  | Extensible Panel (Registry/Consensus) | ✅ Complete  | `test_consensus.py`, `test_registry.py`, `test_orchestrator.py` |
| 03.0  | Memory Forensics Agent                | ✅ Complete  | `test_memory_forensics.py`, `integration/test_forensic_pipeline.py` |
| 04.0  | Concurrency Analyst Agent             | ✅ Complete  | `test_concurrency_analyst.py`, `integration/test_forensic_pipeline.py` |
| 05.0  | Exploitability Analyst Agent          | ✅ Complete  | `test_exploitability_analyst.py`, `integration/test_forensic_pipeline.py` |
| 06.0  | Resource Exhaustion Agent             | ✅ Complete  | `test_resource_analyst.py`, `integration/test_forensic_pipeline.py` |
| 07.0  | Remediation Planner Agent             | ✅ Complete  | `test_remediation_planner.py`, `integration/test_synthesis_pipeline.py` |
| 08.0  | Panel Integration, Docs & Hardening   | ✅ Complete  | `test_weight_audit.py`, `test_agents_config_roundtrip.py` |

### Edit 2 — `docs/roadmap/README.md`

The implementer must update the Milestones table row for 0002 from:

```
| 0002 | Forensic agents (agentic execution brief) | plan.md | — |
```

to:

```
| 0002 | Forensic agents | plan.md | status.md |
```

where `plan.md` links to `/docs/roadmap/0002-forensic-agents/plan.md` and
`status.md` links to `/docs/roadmap/0002-forensic-agents/status.md`.

Also update the note at the bottom of the Milestones section from:

> Only milestone 0001 is currently decomposed into the full task → subtask tree;
> 0002–0004 hold a single planning/status document each until they are decomposed.

to:

> Milestones 0001 and 0002 are fully decomposed and complete. Milestones
> 0003–0004 hold a single planning/status document each until they are
> decomposed.

---

## Ground-truth run record

If Gate 3 of subtask 04 was executed, record here:

- Model used (AI provider + model ID)
- Crash dump or log corpus used as input
- `FaultClass` detected
- Panel assembled (list of `agent_key` values)
- Consensus score and round count
- Whether `RCAReport.remediation_plan` was populated

If the gate was not executed (no dump available), write:

> Ground-truth validation: not executed. No crash dump available in the CI
> environment at milestone close. The 0001 milestone's CrashUi end-to-end
> validation (NULL-pointer write, gpt-5.4, consensus 0.97) remains the most
> recent live validation of the base pipeline.

---

## Success criteria

- [ ] Every row in `status.md` `## Current status` table is `✅ Complete`.
- [ ] `status.md` `**Current gate status:**` paragraph is updated with the
      close date and gate verdicts.
- [ ] `status.md` `## Per-task detail` section is populated for all eight tasks.
- [ ] `docs/roadmap/README.md` Milestone 0002 row has a `status.md` link.
- [ ] `docs/roadmap/README.md` footer note reflects that 0002 is complete.
- [ ] As-built roster, package layout, and weight matrix are recorded in this
      document (or in `status.md`) for permanent reference.
- [ ] Ground-truth run result is recorded (or explicitly marked as not executed).
- [ ] `python scripts/check_doc_links.py docs/` exits 0 after all edits.
- [ ] No `src/` files are modified in this subtask.
