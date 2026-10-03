# 01 — Trust-tier model + `HarnessSettings` amendment

**Parent task:** 06.0 Trust-Tier Harness Selection
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03, 04 (this task)
**Contracts:** C9, C12

## Objective

Introduce the trust-tier model and extend `HarnessSettings` (`harness/config.py`)
to resolve **one active backend per trust tier**, replacing the single
`active_backend` computed property with per-tier resolution, while keeping a
backward-compatible path for the 0005 single-selector deployment.

## Scope

- Add a `TrustTier` enum (`PAYLOAD`, `TRUSTED_SOURCE`) and a mapping of each
  `HarnessBackend` family to its sandbox posture (OpenHands = sandboxed;
  OpenClaude / Claude Code = host-permission). The sandbox posture is the existing
  0005 fact (OpenHands Docker-sandboxed; the other two host-permission).
- Extend `HarnessSettings` with two tier selectors (proposed naming, flagged):
  - `AEGIS_PAYLOAD_TIER_BACKEND` — the payload-tier selector (`openhands` only,
    enforced in subtask 02).
  - `AEGIS_TRUSTED_TIER_BACKEND` — the trusted-source-tier selector (any family).
  - `AEGIS_CODE_INTEL_BACKEND` is **retained as a backward-compatible alias** for
    `AEGIS_TRUSTED_TIER_BACKEND` (a 0005 deployment that only ran code navigation
    keeps working). Document the alias precedence (explicit tier selector wins over
    the alias).
- Replace the single `active_backend` property with `active_backend_for(tier)` (and
  a per-tier `presence_signals` view), so each tier resolves the C2 truth table
  **independently** — selector set → that family; selector unset + exactly one
  signal at that tier → that family; unset + zero → unavailable; unset + >1 →
  `HarnessConfigError` **for that tier** (subtask 04).
- The nested per-family settings (`openclaude`, `claude_code`, `openhands`) are
  unchanged; presence signals are read off them as today (`harness/config.py`).

## Selector-naming note (flagged)

The two-selector + alias scheme is a **proposal** to resolve the ADR's unnamed
"tier-aware selector." Record it in `status.md` → Open items and confirm with the
user before implementing; an alternative (a single structured
`AEGIS_HARNESS_TIERS` map) is noted there.

## Acceptance criteria

- [ ] `TrustTier` enum + family→sandbox-posture map exist; OpenHands is the only
      sandboxed family (C9).
- [ ] `HarnessSettings` exposes `active_backend_for(tier)` resolving each tier
      independently (C9).
- [ ] `AEGIS_PAYLOAD_TIER_BACKEND` / `AEGIS_TRUSTED_TIER_BACKEND` selectors exist;
      `AEGIS_CODE_INTEL_BACKEND` aliases the trusted-source tier with documented
      precedence.
- [ ] Nested per-family settings and presence-signal reads are unchanged.
- [ ] Error context names only field/family/tier/signal, never a secret/URL (C12).
- [ ] The naming proposal is recorded as a flagged open item.
- [ ] `ruff` clean; `Optional[T]` not `T | None`; RST docstrings.
