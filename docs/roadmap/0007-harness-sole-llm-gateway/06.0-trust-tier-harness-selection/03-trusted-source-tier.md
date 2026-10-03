# 03 — Trusted-source-tier selector: host-permission allowed

**Parent task:** 06.0 Trust-Tier Harness Selection
**State:** ⬜ Not started
**Depends on:** 01 (trust-tier model)
**Blocks:** 04 (this task), Task 03.0
**Contracts:** C9, C12

## Objective

Resolve the **trusted-source tier** exactly as 0005 did — any family, including a
host-permission backend (Claude Code / OpenClaude) — preserving the Milestone 0005
closing guarantee that an existing single-selector deployment keeps working
untouched.

## Scope

- Trusted-source-tier resolution accepts any `HarnessBackend` family. Its selector
  is `AEGIS_TRUSTED_TIER_BACKEND`, with `AEGIS_CODE_INTEL_BACKEND` as the
  backward-compatible alias (subtask 01). A `OPENCLAUDE_GRPC_URL`-only deployment
  (0005's guarantee) auto-selects OpenClaude at the trusted-source tier with zero
  further changes.
- The `code_analyst` role (the only `trusted_source` role, Task 01.0) resolves its
  session at this tier, keeping its existing `CodeAgent.investigate()` posture —
  the narrow read-only code-navigation use 0004/0005 established.
- The trusted-source tier is for sessions touching **only** the product's own
  already-trusted source. It must never be used to ingest raw incident payload —
  that is the payload tier's job (subtask 02). The factory (Task 03.0) binds only
  trusted-source roles here; a misbinding (a payload role requesting a
  trusted-source session) is rejected.

## Acceptance criteria

- [ ] Trusted-source tier accepts any family, including host-permission backends
      (C9).
- [ ] A `OPENCLAUDE_GRPC_URL`-only deployment auto-selects OpenClaude at the
      trusted-source tier with zero changes (0005 guarantee preserved).
- [ ] `code_analyst` resolves at the trusted-source tier with its existing
      navigation posture.
- [ ] A payload role requesting a trusted-source session is rejected loudly (no
      cross-tier downgrade) (C9).
- [ ] Error context names only field/family/tier (C12).
- [ ] `ruff` clean.
