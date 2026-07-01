# 04 - Hardening Gates

**Parent task:** Task 08.0 - Panel Integration, Docs & Hardening
**Status:** ⬜ Not started
**Depends on:** [01-default-panels-and-weight-audit.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/01-default-panels-and-weight-audit.md), [02-config-and-examples.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/02-config-and-examples.md),
               [03-docs.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/03-docs.md), Tasks 03.0–07.0 (all agents delivered)
**Blocks:** [05-milestone-closeout.md](/docs/roadmap/0002-forensic-agents/08.0-panel-integration-and-docs/05-milestone-closeout.md)

---

## Objective

Run the full set of exit gates that must be green before the milestone can be
declared complete. Two gates are **mandatory reviewer passes** that block the
milestone exit if they produce a CRITICAL or blocking finding.

---

## Gate 1 - Full regression suite

**Who runs it:** `testing-expert` / `python-expert` (automated)

**Command:**

```
poetry run pytest tests/unit/ tests/integration/ \
  -q \
  --cov=aegis_swr \
  --cov-report=term-missing
```

**Pass criteria:**
- Zero failures, zero errors.
- All tests that existed before Milestone 0002 still pass (back-compat gate -
  any regression here is a blocker regardless of source).
- New tests from subtasks 01 (`test_weight_audit.py`) and 02
  (`test_agents_config_roundtrip.py`) are included and pass.
- Coverage on `src/aegis_swr/agents/` does not decrease from its pre-0002
  baseline (record the baseline before opening the first 0002 task branch).

**Scope note:** the full suite includes the 478+ tests from Milestone 0001 plus
all tests added across Tasks 01.0–08.0. No test may be weakened, `xfail`'d, or
deleted to achieve green.

---

## Gate 2 - Static analysis

**Who runs it:** `python-expert` / CI

**Commands (all must exit 0):**

```
mypy --strict src/aegis_swr/
python scripts/replace_optional.py --check src/aegis_swr/
ruff check src/aegis_swr/ tests/
ruff format --check src/aegis_swr/ tests/
```

**Pass criteria:**
- `mypy --strict` produces zero errors on the full `src/aegis_swr/` tree
  including all new `agents/base/`, `agents/forensic/`, and `agents/synthesis/`
  modules.
- `replace_optional.py --check` finds no `T | None` shorthand in any new or
  modified file.
- `ruff check` is clean (no warnings suppressed for new files).
- `ruff format --check` reports no formatting drift.

---

## Gate 3 - Ground-truth validation (if applicable)

**Who runs it:** `python-expert` (manually, on a dev machine with a live AI key)

**What it is:** A live end-to-end run of the pipeline against a real crash dump
or log corpus using a specialist panel. This gate is "if applicable" - it is
required when a real dump is available in the CI/dev environment; it is
informational (not blocking) when no dump is available.

**Suggested scenario:** Re-run the CrashUi NULL-pointer-write dump from the
0001 end-to-end validation using the `memory_access_violation` panel
(`os_kernel`, `code_analyst`, `log_historian`, `memory_forensics`,
`exploitability`, `skeptic`). Assert that:
- Consensus is still reached (score >= `core.consensus_threshold`).
- `RCAReport.remediation_plan` is populated (Task 07.0 synthesis path active).
- The specialist agents' structured outputs appear in `AgentTurn` entries in
  the `InvestigationState`.

Record the result (model, consensus score, round count) in subtask 05's
as-built notes.

---

## Gate 4 - Security-auditor pass (REQUIRED - CRITICAL blocks)

**Who runs it:** `security-auditor` agent

**Scope:** The Exploitability Analyst agent (`agents/forensic/exploitability_analyst.py`,
Task 05.0) is the primary concern. It reasons directly over attacker-influenced
payload (stack frames, register values, faulting addresses) to assess exploit
potential. The agent's `system_prompt` and `run()` method must be reviewed for:

- **Injection:** Does untrusted payload text flow into a shell, SQL string,
  `eval`, or unsanitised AI prompt? The Data Adapter's PII scrub must be the
  only payload transformation - the Exploitability agent must not re-introduce
  raw payload into any other sink.
- **Disclosure:** Does `ExploitabilityOutput` (specifically `attacker_control`,
  `severity`, and the raw evidence fields) risk leaking sensitive payload into
  logs, exception messages, or API error bodies?
- **Elevation:** The agent's `exploitable: bool` and `severity: str` fields
  must not be used to trigger automated remediation. `RemediationPlannerAgent`
  consumes only the confirmed `RCAReport`, never raw `ExploitabilityOutput`
  directly - verify this boundary is intact.
- **DoS:** Token-budget exhaustion from a pathologically large crash dump. The
  Data Adapter truncation must fire before the Exploitability agent prompt is
  assembled.

Additionally review the consensus/panel changes (Tasks 02.0):
- The `create_agent_panel()` factory must not be influenceable by data from the
  incident payload (panel selection is driven only by `FaultClass`, which is
  determined by the debug backend before payload enters the LLM path).

**Output:** A threat model written to
`docs/security/YYYY-MM-DD-forensic-agents.md` (date = run date) using the
standard `security-auditor` output format (Assets & trust boundaries, Findings,
Verdict).

**Blocking condition:** Any CRITICAL finding produces verdict `BLOCK`. The
milestone exit is gated on verdict `PASS` or `PASS_WITH_FOLLOWUP`. A
`PASS_WITH_FOLLOWUP` may close if all follow-up items are filed as tracked
issues with P1 or P2 priority before the milestone is declared complete.

---

## Gate 5 - Incident-analyst pass (REQUIRED - blocks merge)

**Who runs it:** `incident-analyst` agent

**Scope:** Two changes from this milestone directly touch the escalation path:

1. **Data-driven consensus (Task 02.0).** `ConsensusEvaluator.calculate()` now
   iterates a variable-length `weights` dict instead of a fixed four-key set.
   Verify that:
   - A panel with more than four agents does not artificially raise the
     consensus score above `core.consensus_threshold` due to weight dilution
     (the weights sum to 1.0 invariant from subtask 01 prevents this, but the
     analyst must confirm the formula is correct).
   - `is_deadlocked()` still fires correctly when the variable panel cannot
     converge within `core.max_debate_rounds`.
   - `ConfidenceLevel.LOW` + rejected `SkepticVerdict` still always produces a
     `HITLRequest`, never a weak RCA - with a larger panel this path must not
     be accidentally bypassed.

2. **Remediation planner synthesis path (Task 07.0).** `RemediationPlannerAgent`
   runs in `output_synthesizer_node` after convergence. Verify that:
   - The planner is always skipped when the investigation reaches the HITL path
     (low confidence or Skeptic rejection beyond `max_debate_rounds`).
   - The planner's output (`RemediationPlan`) is not attached to a `HITLRequest`
     - an escalated incident carries no auto-remediation plan.
   - The planner does not itself trigger HITL: if the planner fails or produces
     low-confidence output, it should fail open (omit `remediation_plan` from
     the `RCAReport`) rather than escalating the already-converged investigation.

**Output:** A written verdict appended to the security threat model at
`docs/security/YYYY-MM-DD-forensic-agents.md` under a "Lifecycle gate" section,
or as a separate `docs/security/YYYY-MM-DD-forensic-agents-lifecycle.md` file
if the security-auditor wrote the threat model first. The verdict must state
"PASS" or list blocking issues.

**Blocking condition:** Any finding that the HITL path is not always reachable
or that the remediation planner can run on a HITL outcome blocks the milestone
exit until resolved.

---

## Gate summary

| Gate | Automated? | Mandatory? | Blocking condition |
|------|-----------|------------|-------------------|
| 1 - Full regression | Yes (CI) | Yes | Any failure |
| 2 - Static analysis | Yes (CI) | Yes | Any mypy/ruff/optional error |
| 3 - Ground-truth | Manual | If dump available | Informational only |
| 4 - Security-auditor | Agent | Yes (CRITICAL blocks) | CRITICAL finding or BLOCK verdict |
| 5 - Incident-analyst | Agent | Yes | HITL path not always reachable; planner runs on HITL |

All five gates must be green (or informational for Gate 3) before subtask 05
may proceed.

---

## Success criteria

- [ ] `poetry run pytest tests/unit/ tests/integration/` exits 0 with zero
      failures; coverage on `src/aegis_swr/agents/` does not decrease.
- [ ] `mypy --strict src/aegis_swr/` exits 0.
- [ ] `python scripts/replace_optional.py --check src/aegis_swr/` exits 0.
- [ ] `ruff check src/aegis_swr/ tests/` exits 0.
- [ ] `ruff format --check src/aegis_swr/ tests/` exits 0.
- [ ] Ground-truth run result recorded in subtask 05 as-built notes (or marked
      "not available" with a reason).
- [ ] `security-auditor` threat model exists at
      `docs/security/YYYY-MM-DD-forensic-agents.md` with verdict `PASS` or
      `PASS_WITH_FOLLOWUP`; no CRITICAL finding outstanding.
- [ ] `incident-analyst` verdict recorded; HITL path confirmed always reachable;
      remediation planner confirmed skipped on HITL outcome.
