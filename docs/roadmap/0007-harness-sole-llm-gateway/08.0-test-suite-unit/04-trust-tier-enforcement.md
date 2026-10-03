# 04 — Trust-tier enforcement test

**Parent task:** 08.0 Test Suite — Unit
**State:** ⬜ Not started
**Depends on:** Task 06.0
**Contracts:** C9

## Objective

Prove the ADR's "Trust-tier enforcement" criterion: composition **rejects** a
host-permission backend for a payload-tier session and accepts only a sandboxed
one; the trusted-source tier still accepts host-permission backends; loud-ambiguity
is preserved per tier.

## Scope (`tests/unit/harness/test_trust_tier.py`, `test_composition_tier.py`)

- **Payload-tier rejection:** `AEGIS_PAYLOAD_TIER_BACKEND=openclaude` (or
  `claude_code`) raises `HarnessConfigError` at construction; composing a
  payload-tier session on a host-permission backend raises at composition time.
- **Payload-tier acceptance:** `openhands` (sandboxed) is accepted for the payload
  tier.
- **Trusted-source acceptance:** a host-permission backend is accepted for the
  trusted-source tier (the `code_analyst` posture); a `OPENCLAUDE_GRPC_URL`-only
  deployment auto-selects OpenClaude there (0005 guarantee).
- **Per-tier ambiguity:** selector unset + >1 presence signal *at a tier* raises
  `HarnessConfigError` naming that tier; unset + zero → unavailable (no exception);
  set + absent → `HarnessUnavailableError`.
- **Config-shape half:** a `payload`-tier *role* pinned to a host-permission family
  in `agents.yaml` is rejected at parse (Task 01.0 subtask 04 cross-check).
- **Error-safety:** no error message carries a secret/URL/payload.

## Acceptance criteria

- [ ] Payload tier rejects host-permission (construction + composition); accepts
      sandboxed (C9).
- [ ] Trusted-source tier accepts host-permission; 0005 auto-select guarantee holds.
- [ ] Per-tier ambiguity/unavailable/absent cases match the C9 truth table.
- [ ] A payload-tier host-permission role pin is rejected at parse.
- [ ] No error exposes a secret/URL/payload.
- [ ] 100% branch on the per-tier selection + rejection paths (ADR Coverage).
