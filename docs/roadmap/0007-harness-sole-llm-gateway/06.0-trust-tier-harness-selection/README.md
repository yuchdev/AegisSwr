# Task 06.0 — Trust-Tier Harness Selection

**Parent milestone:** [Milestone 0007 — Harness as the Sole LLM Gateway](/docs/roadmap/0007-harness-sole-llm-gateway/plan.md)
**Status:** ⬜ Not started
**Implements:** ADR 0006 §D.8 (split the single-active-backend selector into two
trust tiers)
**Contracts:** C9 (the deliberate amendment to 0005 C2)
**Gate:** `security-auditor` — `harness/` is the one place that decides whether a
host-permission or a sandboxed backend is activated (0005 note); the payload-tier
sandbox mandate is the control.

## Scope

0005's C2 assumed **one** active backend for **one** narrow read-only role.
Promoting the harness to ingest raw dump/log content end-to-end (C1) breaks that
assumption, so selection generalises from "one active backend" to **"one active
backend per trust tier"** (C9) — the **single** 0005 contract this milestone
deliberately amends:

- **Payload tier** — any session ingesting raw/attacker-influenced incident payload
  (the investigator/arbiter reasoning roles, `analyze_incident`). **MUST be a
  Docker-sandboxed backend → OpenHands.** Host-permission backends (Claude Code,
  OpenClaude) are **rejected at composition time** for this tier.
- **Trusted-source tier** — sessions touching only the product's own trusted source
  (the `code_analyst` `CodeAgent` use). **May** use a host-permission backend,
  exactly as today.

The loud-ambiguity discipline of 0005 C2 (`HarnessConfigError` on an unresolved
selector) is preserved **per tier**. `HarnessSettings`
(`harness/config.py`) is extended to resolve each tier independently at
construction time; `harness/composition.py` composes one backend per tier and
enforces the payload-tier sandbox mandate.

> **Open item flagged (status.md): selector naming.** ADR §D.8 says
> `AEGIS_CODE_INTEL_BACKEND` alone is "no longer sufficient" and must be
> "complemented by a tier-aware selector (named in task breakdown below)" but the
> ADR does not actually name it. Subtask 01 proposes `AEGIS_PAYLOAD_TIER_BACKEND` +
> `AEGIS_TRUSTED_TIER_BACKEND`, keeping `AEGIS_CODE_INTEL_BACKEND` as a
> backward-compatible alias for the trusted-source tier, and flags the naming for
> confirmation.

## Subtasks

| # | Document | Status | Blocks |
|---|----------|--------|--------|
| 01 | [Trust-tier model + `HarnessSettings` amendment](01-trust-tier-model.md) | ⬜ Not started | 02, 03, 04 |
| 02 | [Payload-tier selector: sandboxed mandatory](02-payload-tier-sandboxed.md) | ⬜ Not started | 04, 03.0 |
| 03 | [Trusted-source-tier selector: host-permission allowed](03-trusted-source-tier.md) | ⬜ Not started | 04, 03.0 |
| 04 | [Per-tier loud-ambiguity + composition root](04-per-tier-ambiguity-composition.md) | ⬜ Not started | 04.0 |

Subtask 01 (the model + settings shape) is the foundation; 02/03 (the two tiers)
depend on it and may proceed in parallel; 04 (per-tier ambiguity + composition
wiring) depends on 02 and 03.

## Contracts touched

- **C9** — defined and implemented here; it amends 0005 C2.

## Key constraints

- The amendment is **additive-with-a-constraint**: a 0005 single-backend deployment
  that only ran the trusted-source navigation must keep working (the alias maps it
  to the trusted-source tier) — but a payload-tier session now *requires* a
  sandboxed backend, so a host-only deployment can run only trusted-source-tier work
  (the documented consequence, ADR Negative).
- `HarnessConfigError`/`HarnessUnavailableError` carry only field/family/tier/signal
  names, never a secret/URL/payload (C12, as `harness/config.py` already does).

## Files created or modified by this task

```
src/aegis_swr/harness/
├── config.py          ← modified: per-tier resolution; two tier selectors + alias (C9)
├── composition.py     ← modified: compose one backend per tier; payload tier rejects host-permission
└── exceptions.py      ← modified if needed: tier-aware error context (no new type required)

docs/config/harness-selection.md   ← updated in Task 10.0 (the two-tier truth table)

tests/unit/harness/
├── test_trust_tier.py           ← NEW (selection matrix per tier)
└── test_composition_tier.py     ← NEW (payload-tier host-permission rejection)
```
