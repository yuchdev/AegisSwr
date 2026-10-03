# 03 — `HarnessSessionFactory` (role binding + allowlist)

**Parent task:** 03.0 Harness Session Adapter & Factory
**State:** ⬜ Not started
**Depends on:** 01 (`HarnessSession`)
**Blocks:** Task 04.0, Task 06.0
**Contracts:** C5, C9, C12

## Objective

Implement `HarnessSessionFactory` in `harness/session.py`: the one place a
forensic role is bound to a concrete `HarnessSession` with the role-scoped tool
allowlist and the correct trust tier. Built at the composition root and injected
into `Orchestrator` (Task 04.0), never imported by it.

## Design

```python
class HarnessSessionFactory:
    """Builds a per-role HarnessSession from the Task 01.0 binding table (C5).

    Owned by harness/; constructed at the composition root with the resolved
    per-tier backends (C9) and the role bindings. session_for(role_key) returns a
    HarnessSessionBackend bound to a HarnessSession carrying the role's trust
    tier, tool-allowlist tier, and timeout.
    """

    def session_for(self, role_key: str) -> HarnessSessionBackend: ...
```

- The factory reads each role's binding (`trust_tier`, `harness_persona`,
  `tool_allowlist_tier`, optional `harness_family`) from the reframed
  `RouterConfig` (Task 01.0).
- It resolves the backend at the role's **trust tier** via the Task 06.0 tier-aware
  `HarnessSettings` (C9): payload-tier roles → the payload-tier (sandboxed)
  backend; the `code_analyst` trusted-source role → the trusted-source-tier
  backend (may be host-permission).
- It maps `harness_persona` to a concrete tool allowlist: `read_only_context`
  (investigators/skeptic — read-only context tools), `code_navigation`
  (`code_analyst` — the existing `CodeAgent.investigate()` posture),
  `no_tools` (empty allowlist — the `claude_cli_provider` replacement, Task 02.0).
- It registers any sidecar the resolved backend owns on the caller's
  `AsyncExitStack` for RAII teardown (mirrors 0005 C4).
- If a role's binding is unresolvable (e.g. its tier has no active backend, or a
  payload-tier role resolves to a host-permission backend — which Task 06.0's
  composition already rejects), the factory raises the harness typed error loudly
  (`HarnessConfigError`/`HarnessUnavailableError`) — never a silent fallback.

## Constraints

- The factory is the **single** place roles are bound to sessions (C5); no role
  binding logic leaks into `Orchestrator` or `resolve_panel`.
- Error messages name only role/family/tier, never a secret/URL/payload (C12).

## Acceptance criteria

- [ ] `HarnessSessionFactory.session_for(role_key)` returns a
      `HarnessSessionBackend` with the role's trust tier, persona allowlist, and
      timeout from the binding table (C5).
- [ ] Payload-tier roles resolve to the sandboxed backend; `code_analyst` resolves
      at the trusted-source tier (C9).
- [ ] `no_tools` persona resolves to an empty allowlist (Task 02.0 replacement).
- [ ] Any sidecar is registered on the caller's `AsyncExitStack`.
- [ ] An unresolvable binding raises the harness typed error loudly; no fallback
      (C9).
- [ ] `ruff` clean; RST docstrings.
