# 06 — Autonomy stage-gate test

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Task 07.0
**Contracts:** C11, C9

## Objective

Prove the ADR's "Autonomy gating" criterion: Stages 1–3 are off by default; each
requires explicit opt-in; `HITLRequest` escalation is reachable in every stage;
execution occurs only inside the sandboxed runtime; `/playbook-validate` precedes
any Stage-2+ run (stub only — no execution path is wired).

## Scope (`tests/unit/core/test_autonomy.py`)

- **Default.** With no opt-in flag, `AutonomyGate` resolves Stage 0; the report
  carries no `candidate_remediation`; behaviour matches today.
- **Opt-in required.** Stage 1 is active only with its explicit flag; `autonomous`
  (Stage 3) is rejected loudly at the gate.
- **Stage 1 output.** With Stage 1 opted in, the report carries a
  `candidate_remediation` marked `never_executed=True`; no execution occurs; the
  candidate patch was produced on a sandboxed (payload-tier) session (C9).
- **HITL reachable at every stage.** A low-consensus run yields a `HITLRequest` at
  Stage 0 and Stage 1.
- **No execution path.** `execution_allowed()` is always `False`; selecting
  `execute_validated` reaches the `PlaybookValidationHook` stub and is **refused**
  loudly — nothing is run.
- **Sandbox-only.** A write-capable stage requested with no sandboxed backend active
  is refused (C9).
- **100% branch** on `core/autonomy.py` (ADR Coverage).

## Acceptance criteria

- [ ] Default is Stage 0; Stages 1–3 off without opt-in; `autonomous` rejected (C11).
- [ ] Stage 1 attaches a `never_executed` candidate patch on a sandboxed session;
      nothing is executed (C11, C9).
- [ ] `HITLRequest` is reachable at Stage 0 and Stage 1 (C11).
- [ ] `execution_allowed()` is always `False`; the Stage 2 stub refuses loudly.
- [ ] A write-capable stage with no sandbox active is refused (C9).
- [ ] 100% branch on `core/autonomy.py` (ADR Coverage).
