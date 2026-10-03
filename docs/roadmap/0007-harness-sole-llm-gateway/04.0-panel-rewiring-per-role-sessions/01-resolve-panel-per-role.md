# 01 — `resolve_panel` per-role session injection

**Parent task:** 04.0 Panel Rewiring onto Per-Role Sessions
**State:** ⬜ Not started
**Depends on:** Task 03.0 (`HarnessSessionFactory`)
**Blocks:** 02, 03 (this task)
**Contracts:** C5, C6, C12

## Objective

Change `resolve_panel` (`agents/panel.py:39`) so each agent is constructed with
its **own** per-role `HarnessSessionBackend` from the `HarnessSessionFactory`,
instead of one shared `ai_backend` fanned to every agent — preserving the
exactly-one-ARBITER enforcement and the unknown-key tolerance verbatim.

## Scope

- Replace the `ai_backend: AIAPIBackend` parameter of `resolve_panel` with a
  `session_factory: HarnessSessionFactory` (or accept both during a transition and
  deprecate the single-backend path — prefer the clean swap, since all production
  construction now goes through the factory). The signature change is internal; no
  stable external API.
- For each enabled spec, call `create_agent(spec, session_factory.session_for(spec.agent_key), settings)` so every agent receives the backend for *its* role — the
  `code_analyst` gets a `code_navigation`/trusted-source session; the investigators
  and skeptic/arbiter get `read_only_context`/payload sessions (C5, C9).
- **Preserve verbatim:**
  - Unknown-key tolerance — a spec naming an unregistered `agent_key` is warned and
    skipped (not fatal).
  - Exactly-one-ARBITER enforcement — zero or two-plus arbiters raise
    `PanelResolutionError`.
  - Returned-list ordering mirrors input spec order.
- `resolve_consensus_weights` (`agents/panel.py:89`) is **unchanged** — weight is
  still each agent's intrinsic `default_weight` with the explicit-override
  precedence (ADR 0002, C6).

## Constraints

- No agent's reasoning behaviour changes; only the identity/source of its backend
  does (C6).
- If a role's session cannot be built, the factory raises loudly (Task 03.0); the
  panel does not fall back to a shared backend (C9).

## Acceptance criteria

- [ ] `resolve_panel` injects a per-role `HarnessSessionBackend` keyed by
      `agent_key`/role (C5).
- [ ] `code_analyst` receives a `code_navigation`/trusted-source session; other
      roles receive `read_only_context`/payload sessions (C9).
- [ ] Unknown-key tolerance and exactly-one-ARBITER enforcement are preserved
      verbatim (C6).
- [ ] `resolve_consensus_weights` is unchanged (C6).
- [ ] `ruff` clean; RST docstrings updated to reflect per-role injection.
