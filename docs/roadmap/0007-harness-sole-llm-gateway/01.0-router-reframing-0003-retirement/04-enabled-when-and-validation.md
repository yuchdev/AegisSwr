# 04 — `enabled_when` preservation + binding validation

**Parent task:** 01.0 Router Reframing & Milestone 0003 Retirement
**State:** ⬜ Not started
**Depends on:** 02 (validates the YAML it writes)
**Blocks:** Task 03.0
**Contracts:** C3, C9, C12

## Objective

Extend `tests/unit/router/test_config.py` to prove the reframed binding table
parses correctly, that `enabled_when` gating is preserved **verbatim** (0005 C11),
and that the C9 config-shape rule fails loud — the validation contract Task 03.0's
`HarnessSessionFactory` relies on.

## Scope

Unit tests over `RouterConfig.from_yaml` and `AgentConfig` validation:

1. **Binding-field parsing.** The rewritten `agents.yaml` (subtask 02) parses;
   each forensic role exposes the expected `trust_tier`, `harness_persona`,
   `tool_allowlist_tier`, and inherited (`None`) `harness_family`.
2. **Legacy-stanza parity.** A stanza with only `provider`/`model`/`timeout_s`/
   `enabled_when` parses with the documented defaults (non-breaking reframe).
3. **`enabled_when` preserved verbatim.** A role whose `enabled_when` signal is
   absent is dropped from the parsed config exactly as before; one whose signal is
   present is included — identical behaviour to the Milestone 0004/0005 tests.
4. **C9 config-shape rule.** A `payload`-tier role pinned to `openclaude` or
   `claude_code` raises the typed config error; a `payload`-tier role bound to
   `openhands` (or inheriting) parses.
5. **Error-message safety.** Every validation error names only field/role/token,
   never a secret/URL/payload (C12).
6. **No `litellm` import.** The router-package isolation test (from Milestone
   0003) still passes after the reframe (C13).

## Acceptance criteria

- [ ] The rewritten `agents.yaml` parses; binding fields resolve per the subtask
      02 table.
- [ ] A legacy stanza parses unchanged.
- [ ] `enabled_when` include/drop behaviour is byte-for-byte the prior behaviour.
- [ ] A payload-tier host-permission pin raises the typed config error; a sandboxed
      binding parses.
- [ ] No validation error exposes a secret/URL/payload.
- [ ] The `router/` no-`litellm` isolation test passes.
- [ ] `ruff` clean; coverage on the new `AgentConfig` validation paths is 100%
      branch (these feed the composition-time security check in Task 06.0).
