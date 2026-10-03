# 01 — `RouterConfig`/`AgentConfig` binding-table fields

**Parent task:** 01.0 Router Reframing & Milestone 0003 Retirement
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 04 (this task); Task 03.0 (consumes the binding table)
**Contracts:** C3, C12, C13

## Objective

Extend the existing `AgentConfig` (parsed by `RouterConfig.from_yaml`, built as
the Milestone 0003 config slice) with the fields that express the **role →
harness-session binding** per ADR 0006 §A.3, so each forensic role declares how a
harness session is built for it — without introducing any dispatch behaviour or
any `litellm` dependency.

## Fields to add to `AgentConfig`

| Field | Type | Meaning | Default |
|-------|------|---------|---------|
| `harness_family` | `Optional[str]` | Which harness family backs this role (`openclaude` \| `claude_code` \| `openhands`), or `None` to inherit the tier's active backend (C9). | `None` |
| `harness_persona` | `Optional[str]` | The persona/allowlist posture, one of `read_only_context` \| `code_navigation` \| `no_tools` (the empty-allowlist `claude_code` persona that replaces `claude_cli_provider`, Task 02.0). | `read_only_context` |
| `trust_tier` | `str` | `payload` or `trusted_source` (C9). Investigator/arbiter reasoning roles are `payload`; the `code_analyst` navigation role is `trusted_source`. | `payload` |
| `tool_allowlist_tier` | `str` | Symbolic allowlist tier name resolved to a concrete allowlist by the `HarnessSessionFactory` (Task 03.0). | `read_only` |

The existing `provider` and `model` fields are **retained but reframed** as
**advisory metadata**: their docstrings must state they document what the backing
harness is configured with and are **never** an Aegis dispatch instruction. The
existing optional `enabled_when` and `timeout_s` fields are unchanged.

## Behaviour

- A role stanza omitting all new fields parses with the documented defaults — a
  role that today only sets `provider`/`model`/`timeout_s`/`enabled_when` keeps
  parsing (non-breaking reframe).
- Validation rejects an unknown `harness_family`, `harness_persona`, `trust_tier`,
  or `tool_allowlist_tier` value by raising the router's existing typed config
  error (the `ConfigValidationError` lineage), naming only the offending
  field/role and the rejected token — never a secret, URL, or payload (C12).
- A **cross-field rule** mirroring C9: a role with `trust_tier="payload"` whose
  `harness_family` is a host-permission family (`openclaude` or `claude_code`) is
  rejected at parse time — payload reasoning must be sandboxed. (This is the
  config-shape half of the composition-time enforcement Task 06.0 owns; keeping it
  here fails the operator early.)
- `RouterConfig` continues to import no `litellm`/`anthropic`/`openai` (C13); the
  Milestone 0003 isolation test stays green.

## Acceptance criteria

- [ ] `AgentConfig` carries `harness_family`, `harness_persona`, `trust_tier`,
      `tool_allowlist_tier` with the documented defaults and RST docstrings.
- [ ] `provider`/`model` docstrings state they are advisory metadata, never a
      dispatch instruction (C3).
- [ ] A legacy stanza (only `provider`/`model`/`timeout_s`/`enabled_when`) parses
      unchanged.
- [ ] An unknown value for any new field raises the typed config error naming only
      field/role/token (C12).
- [ ] A `payload`-tier role bound to `openclaude`/`claude_code` is rejected at
      parse time (C9 config-shape half).
- [ ] `router/` imports no `litellm`; the 0003 isolation test passes (C13).
- [ ] `ruff` clean; `Optional[T]` not `T | None`; `from __future__ import
      annotations` present (C12).
