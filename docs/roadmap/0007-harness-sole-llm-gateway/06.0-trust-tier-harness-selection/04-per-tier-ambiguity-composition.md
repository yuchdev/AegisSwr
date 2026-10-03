# 04 — Per-tier loud-ambiguity + composition root

**Parent task:** 06.0 Trust-Tier Harness Selection
**State:** ⬜ Not started
**Depends on:** 02 (payload tier), 03 (trusted-source tier)
**Blocks:** Task 04.0
**Contracts:** C9, C12

## Objective

Preserve the 0005 C2 loud-ambiguity discipline **per tier** and wire the per-tier
composition so `create_code_intel_backend` (or the generalised composition factory)
produces one backend per trust tier for the `HarnessSessionFactory` (Task 03.0) to
draw from.

## Scope

- **Per-tier ambiguity (C9).** For each tier independently: selector unset + more
  than one presence signal *at that tier* → `HarnessConfigError` at
  settings-construction time, naming the tier and the sorted signal set (never a
  URL/token, as `harness/config.py` already does). Selector unset + zero → that
  tier's capability is unavailable (no exception). Selector set but signal absent →
  `HarnessUnavailableError` at composition/health-check time. This is the 0005 C2
  truth table applied once per tier.
- **Composition.** Extend `harness/composition.py` so it builds the trusted-source
  backend and (when Docker/OpenHands is available) the payload backend, each
  registered on the caller's `AsyncExitStack`, and exposes both to the
  `HarnessSessionFactory`. The payload-tier sandbox assertion (subtask 02) is
  enforced here at composition time.
- **Selection-matrix tests** (`tests/unit/harness/test_trust_tier.py`,
  `test_composition_tier.py`): the full per-tier matrix (unset+zero / unset+one /
  unset+many / set+present / set+absent) for both tiers, plus the payload-tier
  host-permission rejection and the trusted-source host-permission acceptance.

## Acceptance criteria

- [ ] Each tier resolves the 0005 C2 truth table independently; unset+>1 at a tier
      raises `HarnessConfigError` naming that tier (C9).
- [ ] `harness/composition.py` builds one backend per tier, registers sidecars on
      the `AsyncExitStack`, and enforces the payload-tier sandbox assertion (C9).
- [ ] The `HarnessSessionFactory` draws the right backend per role tier (Task 03.0).
- [ ] The per-tier selection matrix is fully covered (100% branch on the tier
      selection, ADR Coverage).
- [ ] Error context names only field/family/tier/signal (C12).
- [ ] `ruff` clean.
