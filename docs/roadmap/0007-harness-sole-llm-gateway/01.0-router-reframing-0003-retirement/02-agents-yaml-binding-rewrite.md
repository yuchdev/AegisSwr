# 02 — `agents.yaml` role → harness-session rewrite

**Parent task:** 01.0 Router Reframing & Milestone 0003 Retirement
**State:** ⬜ Not started
**Depends on:** 01 (the fields this populates)
**Blocks:** 04 (this task); Task 03.0
**Contracts:** C3, C9, C12

## Objective

Rewrite `src/aegis_swr/config/agents.yaml` so each forensic role stanza expresses
its **harness-session binding** (the fields added in subtask 01), repurposing the
file from inert routing config into the role → harness-session binding table ADR
0006 §A.3 defines.

## Role bindings to author

Each of the forensic roles gets a stanza with the new binding fields. The binding
posture per ADR 0006 §B.5 and C5/C9:

| Role | `trust_tier` | `harness_persona` | `tool_allowlist_tier` | Notes |
|------|-------------|-------------------|-----------------------|-------|
| `os_kernel` | `payload` | `read_only_context` | `read_only` | Investigator; ingests raw dump/log payload → sandboxed (C9). |
| `log_historian` | `payload` | `read_only_context` | `read_only` | Investigator; reads log corpora → sandboxed. |
| `code_analyst` | `trusted_source` | `code_navigation` | `code_navigation` | Keeps its existing `CodeAgent.investigate()` posture over trusted source; **may** use a host-permission backend (C9). |
| `skeptic` / arbiter | `payload` | `read_only_context` | `read_only` | Adversarial validation over the structured debate; sandboxed. |

- `harness_family` is left **unset** (`None`) on every role so each inherits its
  tier's active backend from `HarnessSettings` (C9), **except** where an operator
  deliberately pins a family — document the pin-override syntax in a comment.
- `provider`/`model` become **advisory comments/metadata**: keep a `model: ~`
  placeholder and a comment naming that the backing harness owns model/credential
  selection (the 0005 `openclaude_agent` stanza pattern).
- `enabled_when` is kept **verbatim** where present; the existing
  `openclaude_agent` / `claude_code_agent` / `openhands_agent` harness-role
  stanzas (0005 C11) are retained unchanged — they gate *backend availability*;
  the forensic-role bindings gate *which backend each panel role uses*.
- The `no_tools` persona (the empty-allowlist `claude_code` posture replacing
  `claude_cli_provider`, Task 02.0) is documented in a comment as an available
  `harness_persona` value, used by operators who want "Claude Code as just an LLM"
  for a trusted-source role.

## Acceptance criteria

- [ ] Each forensic role (`os_kernel`, `log_historian`, `code_analyst`,
      `skeptic`/arbiter) carries a binding stanza with `trust_tier`,
      `harness_persona`, `tool_allowlist_tier` matching the table above (C3, C9).
- [ ] `code_analyst` is the only `trusted_source`-tier role; every payload-reasoning
      role is `payload` tier (C9).
- [ ] No payload-tier role pins a host-permission `harness_family` (C9).
- [ ] `provider`/`model` are present only as advisory placeholders/comments; no
      secret or key appears in the file (C3, C12).
- [ ] `enabled_when` gating is unchanged for every stanza that had it (0005 C11).
- [ ] `RouterConfig.from_yaml` parses the rewritten file without error (validated
      by subtask 04).
