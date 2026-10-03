# 02 — Live per-role harness panel (OpenHands)

**Parent task:** 09.0 Test Suite — Integration
**State:** ⬜ Not started
**Depends on:** 01 (skip guards)
**Contracts:** C1, C6, C9, C10

## Objective

Verify, against a **live** sandboxed OpenHands backend, that a forensic panel of
per-role harness sessions reaches a deterministic consensus and produces a real
`RCAReport` — with no model API key held by Aegis.

## Scope (`test_live_per_role_panel.py`, gated `require_payload_tier`)

- Build the orchestrator with the live `HarnessSessionFactory`; run a full
  investigation over the fixture incident.
- Assert: each role ran on its own session (payload-tier roles on the sandboxed
  OpenHands backend; `code_analyst` on the trusted-source backend if configured);
  the panel produced a structured `RCAReport` (or a `HITLRequest` on low
  consensus); the one-arbiter invariant held.
- Assert the consensus was computed Aegis-side by `consensus.py` over structured
  `Hypothesis`/`SkepticVerdict` output (C6) — arbitration was never delegated to a
  harness.
- Assert token totals on the `RCAReport` are populated from
  `CodeResult.token_estimate` across the per-role sessions (C10).
- Assert no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/AWS cred was present in Aegis's
  environment during the run (keys live only inside OpenHands' own config) (C1).

## Acceptance criteria

- [ ] A live per-role panel produces a structured `RCAReport`/`HITLRequest` (C1).
- [ ] Each role ran on its tier-correct session; one-arbiter invariant held (C9, C6).
- [ ] Consensus was Aegis-side over structured output (C6).
- [ ] Token totals populated from `token_estimate` (C10).
- [ ] No model API key was present in Aegis's environment (C1).
- [ ] Skips cleanly without Docker/OpenHands.
