# 02 — Payload-tier selector: sandboxed mandatory

**Parent task:** 06.0 Trust-Tier Harness Selection
**State:** ⬜ Not started
**Depends on:** 01 (trust-tier model)
**Blocks:** 04 (this task), Task 03.0
**Contracts:** C9, C12

## Objective

Enforce that the **payload tier** resolves only to a Docker-sandboxed backend
(OpenHands), rejecting any host-permission backend (Claude Code, OpenClaude) at
composition time — the sandbox is the control for running a harness over hostile
payload end-to-end.

## Scope

- In `harness/config.py`'s payload-tier resolution: a `AEGIS_PAYLOAD_TIER_BACKEND`
  set to a host-permission family raises `HarnessConfigError` at
  settings-construction time (fail loud, config-shape), naming only the field and
  the rejected family. Auto-selection for the payload tier considers **only**
  sandboxed families' presence signals.
- In `harness/composition.py`: building a payload-tier backend asserts the resolved
  family is sandboxed; a host-permission family reaching this point (e.g. via an
  inconsistent config) raises `HarnessConfigError`/`HarnessUnavailableError`-
  equivalent at composition time — never silently proceed on host permissions.
- This complements the Task 01.0 config-shape rule (a `payload`-tier *role* pinned
  to a host-permission family is rejected at YAML parse) with the **selection-level**
  enforcement: even without a per-role pin, the payload tier's active backend is
  sandbox-only.
- The consequence (ADR Negative) is documented: a host-only deployment (no Docker)
  can run **only** trusted-source-tier work; payload-tier ingestion is unavailable
  there — surfaced as a loud capability gap, not a silent host-permission fallback.

## Acceptance criteria

- [ ] `AEGIS_PAYLOAD_TIER_BACKEND` set to `openclaude`/`claude_code` raises
      `HarnessConfigError` at construction (C9).
- [ ] Payload-tier auto-selection considers only sandboxed families.
- [ ] `harness/composition.py` asserts the payload-tier backend is sandboxed and
      rejects a host-permission one at composition time (C9).
- [ ] A host-only (no Docker) deployment reports payload-tier capability
      unavailable loudly — no host-permission fallback (ADR Negative).
- [ ] Error context names only field/family/tier (C12).
- [ ] `ruff` clean; 100% branch on the payload-tier rejection path (ADR Coverage).
