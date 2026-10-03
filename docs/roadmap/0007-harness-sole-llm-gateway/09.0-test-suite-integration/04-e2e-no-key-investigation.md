# 04 — End-to-end no-key investigation

**Parent task:** 09.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards)
**Contracts:** C1, C9, C11

## Objective

Run a full `aegis analyze` investigation end-to-end against a live sandboxed
backend, with **no** model API key in Aegis's environment, verifying the complete
inversion including the Stage 0/1 autonomy posture.

## Scope (`test_e2e_no_key_investigation.py`, gated `require_payload_tier`)

- With all provider keys unset, run `aegis analyze` (non-dry-run) over the fixture
  incident through the real CLI composition root.
- Assert a real `RCAReport` is produced (or a `HITLRequest` on low consensus) with
  no key present in Aegis's environment (C1).
- **Stage 0 (default):** assert the report carries no `candidate_remediation` and
  nothing was executed.
- **Stage 1 (opt-in variant):** with the Stage 1 flag set, assert the report
  carries a `candidate_remediation` marked `never_executed=True`, produced on the
  sandboxed backend, and that **nothing was executed** (no process spawned to run
  the patch, no production credential used) (C11, C9).
- Assert HITL escalation is reachable (force a low-consensus fixture variant and
  assert the `HITLRequest` path fires at both stages).
- Reuse the hostile fixture to assert no seeded secret/PII reaches the persisted
  report, logs, or any session context (C8 cross-check).

## Acceptance criteria

- [ ] A live no-key investigation produces a real `RCAReport`/`HITLRequest` (C1).
- [ ] Stage 0 report has no candidate patch; nothing executed.
- [ ] Stage 1 opt-in attaches a `never_executed` candidate patch on the sandboxed
      backend; nothing executed (C11, C9).
- [ ] HITL escalation fires at both stages on low consensus (C11).
- [ ] No seeded secret/PII in the persisted report/logs/session context (C8).
- [ ] Skips cleanly without Docker/OpenHands.
