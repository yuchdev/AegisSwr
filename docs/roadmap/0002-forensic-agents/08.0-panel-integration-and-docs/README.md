# Task 08.0 - Panel Integration, Docs & Hardening

**Parent milestone:** [Milestone 0002 - Forensic Agents](/docs/roadmap/0002-forensic-agents/plan.md)
**Status:** ⬜ Not started

---

## Scope

Task 08.0 is the **milestone exit gate** for Milestone 0002. It does not add new
agents; it closes the loop on everything Tasks 01.0–07.0 built:

- Ratifies the final per-fault consensus weight matrix for all ten `FaultClass`
  values, resolving any weight conflicts left open by the individual forensic tasks.
- Writes the definitive configuration artifacts (`agents.example.json`,
  `config.yaml` panel/weights blocks) that ship with the product.
- Updates the four documentation targets (product agent roster, config reference,
  domain glossary, docs index) to reflect the full nine-agent roster.
- Runs all hardening gates: full regression, static analysis, mandatory
  `security-auditor` pass on the Exploitability agent surface, and mandatory
  `incident-analyst` pass on the consensus/panel/escalation changes.
- Records the as-built state and closes the milestone by updating `status.md`
  and the roadmap index.

No new `src/` modules are introduced in this task. Every deliverable is either a
configuration file, a documentation update, or a test assertion.

---

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Default panels & weight audit](01-default-panels-and-weight-audit.md) | ⬜ Not started | 02, 04 |
| 02 | [Config & examples](02-config-and-examples.md) | ⬜ Not started | 04 |
| 03 | [Docs](03-docs.md) | ⬜ Not started | 05 |
| 04 | [Hardening gates](04-hardening-gates.md) | ⬜ Not started | 05 |
| 05 | [Milestone closeout](05-milestone-closeout.md) | ⬜ Not started | - |

Subtasks 02 and 03 both depend on 01 and may proceed in parallel with each
other once 01 is complete. Subtask 04 depends on 01, 02, 03, and all of Tasks
03.0–07.0. Subtask 05 is the final step and depends on all four preceding
subtasks.

---

## Key constraints

**Back-compat gate (non-negotiable).** The default panel (no `fault_class`
override, no specialist configuration) must reproduce the legacy four-agent chain
`os_kernel → code_analyst → log_historian → skeptic` byte-for-byte and the
default consensus weights must reproduce the 0001 matrix exactly. Any deviation
here is a regression, not a feature.

**Weights sum to 1.0.** Every fault class's debate weight vector must sum to
1.0 (tolerance 1e-6). The weight-audit subtask (01) enforces this with an
automated test; failing the test blocks subtasks 02 and 04.

**Security gate (CRITICAL, blocks merge).** The Exploitability Analyst agent
(Task 05.0) reasons over attacker-influenced payload. Subtask 04 requires a
`security-auditor` pass that produces a threat model at
`docs/security/YYYY-MM-DD-forensic-agents.md`. A CRITICAL finding blocks the
milestone exit unconditionally.

**Lifecycle gate (REQUIRED, blocks merge).** The consensus/panel refactor
(Tasks 02.0) and the remediation planner synthesis path (Task 07.0) both touch
escalation logic. Subtask 04 requires an `incident-analyst` pass confirming that
the HITL path remains always reachable and that the remediation planner is
skipped when HITL fires.

**`Optional[T]`, never `T | None`.** All configuration models and any test
code produced in this task must use `Optional[T]` from `typing`. Run
`python scripts/replace_optional.py --check` before closing subtask 04.

**mypy `--strict` and ruff.** All new test files must pass both checks.
