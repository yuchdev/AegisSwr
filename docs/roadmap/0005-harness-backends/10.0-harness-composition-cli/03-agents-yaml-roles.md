# 03 - agents.yaml claude_code_agent / openhands_agent roles

**Parent task:** 10.0 Harness Composition Root & CLI
**State:** ⬜ Not started
**Depends on:** Task 02.0 (`ClaudeCodeSettings.request_timeout_s` default, the
`CLAUDE_CODE_ENABLED` signal); Task 06.0 (`OpenHandsSettings.request_timeout_s`
default, the `OPENHANDS_SERVER_URL` signal); Task 04.0 (the two C7 auth modes the
`claude_code_agent` comment references)
**Blocks:** none

## Objective

Add a `claude_code_agent` and an `openhands_agent` role stanza to
`src/aegis_swr/config/agents.yaml`, **alongside** the existing `openclaude_agent`,
each replicating that stanza's pattern (C11): `provider: <family>`, `model: ~`
(Aegis SWR resolves no LiteLLM model), `timeout_s` matching that backend's own
`request_timeout_s` default, and an `enabled_when` tied to **that backend's own
presence signal**. As with `openclaude_agent`, these roles are inert config
parsed only by `RouterConfig` — they are not routed through LiteLLM;
`enabled_when` merely suppresses validation errors when the signal is absent.

## Existing pattern (to mirror — `openclaude_agent`, do not change it)

```yaml
  openclaude_agent:
    provider: openclaude        # not routed through LiteLLM; see RouterConfig
    # Model selection is entirely OpenClaude's / the operator's concern, set via
    # OpenClaude's own env vars (CLAUDE_CODE_USE_OPENAI, OPENAI_BASE_URL,
    # OPENAI_MODEL, OPENAI_API_KEY). Aegis SWR never resolves a model for this
    # role - see the milestone's "User-supplied model contract".
    model: ~                    # YAML null - Aegis SWR resolves no LiteLLM model
    timeout_s: 120              # matches OpenClaudeSettings.request_timeout_s default (C1)
    enabled_when: OPENCLAUDE_GRPC_URL   # role inactive when the var is unset
```

## File: `src/aegis_swr/config/agents.yaml` (two new stanzas, appended after `openclaude_agent`)

```yaml
  claude_code_agent:
    provider: claude_code       # not routed through LiteLLM; see RouterConfig
    # Model + credentials are Claude Code's / the operator's concern. Two
    # authentication modes exist (C7): `api_key` (ANTHROPIC_API_KEY /
    # ANTHROPIC_AUTH_TOKEN) and `subscription` (a `claude login` session or a
    # CLAUDE_CODE_OAUTH_TOKEN minted by `claude setup-token`). The mode is chosen
    # by ClaudeCodeSettings.auth_mode (CLAUDE_CODE_AUTH_MODE), NOT here — it lives
    # in the backend settings, exactly as OpenClaude's model env vars do. See
    # docs/claude-code-setup.md (Task 13.0) for both modes and the subscription
    # licensing caveat.
    model: ~                    # YAML null - Aegis SWR resolves no LiteLLM model
    timeout_s: 120              # matches ClaudeCodeSettings.request_timeout_s default (C6)
    enabled_when: CLAUDE_CODE_ENABLED   # explicit opt-in; PATH presence is NOT a signal (C6)

  openhands_agent:
    provider: openhands         # not routed through LiteLLM; see RouterConfig
    # Model selection is OpenHands' / the operator's concern via its own LiteLLM
    # configuration. Aegis SWR never resolves a model for this role. The runtime
    # is Docker-sandboxed by default (C8). See docs/openhands-setup.md (Task 13.0).
    model: ~                    # YAML null - Aegis SWR resolves no LiteLLM model
    timeout_s: 120              # matches OpenHandsSettings.request_timeout_s default (C8)
    enabled_when: OPENHANDS_SERVER_URL   # role inactive when the URL is unset
```

## Implementation notes

- **`timeout_s` must equal each backend's `request_timeout_s` default** (C11 /
  C1). The `120` values above are placeholders pending the confirmed defaults
  Task 02.0 (Claude Code) and Task 06.0 (OpenHands) ship; reconcile each to its
  authoritative `*Settings.request_timeout_s` default before merge. The YAML is a
  router/agent-role bookkeeping value; the actual per-call deadline is enforced
  inside each tool from `settings.request_timeout_s`. They must not contradict.
- **`enabled_when` is an env-var name, not its value** (same semantics as
  `openclaude_agent`, Task 01.0 subtask 03 in 0004). `CLAUDE_CODE_ENABLED` and
  `OPENHANDS_SERVER_URL` are the presence signals (C2/C6/C8); when absent,
  `RouterConfig` omits the role from validation.
- **`auth_mode` is NOT in `agents.yaml`** (C11). It lives on `ClaudeCodeSettings`
  sourced from `CLAUDE_CODE_AUTH_MODE`, exactly as OpenClaude's model env vars
  are not in the YAML. The `claude_code_agent` comment only *names* the two modes
  and points at the Task 13.0 setup guide; it configures nothing.
- **No credentials/secrets in any stanza.** These are inert `RouterConfig`
  entries, not `providers:` entries; the OAuth token, `ANTHROPIC_API_KEY`, and
  OpenHands' LiteLLM keys never appear here (C11 / C7 / security rules).
- **Do not add speculative fields.** No `max_tokens`, no `retry`, no `fallback`
  on these roles — mirror the `openclaude_agent` stanza's minimal shape exactly.
- **Keep every other role byte-for-byte unchanged**, including `openclaude_agent`.

## Constraints

- Both stanzas mirror `openclaude_agent`'s shape: `provider`, `model: ~`,
  `timeout_s`, `enabled_when` — no extra fields (C11).
- `enabled_when` is tied to each backend's own presence signal:
  `CLAUDE_CODE_ENABLED` and `OPENHANDS_SERVER_URL` respectively (C11).
- `timeout_s` equals the respective `request_timeout_s` default (C11).
- No `api_key`/secret field on either role (C11 / security rules).
- The `claude_code_agent` comment names both C7 auth modes and points at
  `docs/claude-code-setup.md` (Task 13.0), and states `auth_mode` lives in
  settings, not the YAML.
- YAML stays valid against the existing schema and `RouterConfig.from_yaml` with
  each `enabled_when` var both set and unset.
- All other agent roles unchanged.

## Success criteria

- [ ] `agents.yaml` contains `claude_code_agent` and `openhands_agent` roles
      alongside `openclaude_agent`.
- [ ] Each new role has `provider`, `model: ~`, `timeout_s`, `enabled_when` and
      no other fields.
- [ ] `claude_code_agent.enabled_when == CLAUDE_CODE_ENABLED`;
      `openhands_agent.enabled_when == OPENHANDS_SERVER_URL` (C11).
- [ ] Each `timeout_s` equals its backend's `request_timeout_s` default (C11).
- [ ] The `claude_code_agent` comment names both C7 auth modes, states `auth_mode`
      lives in `ClaudeCodeSettings` (not the YAML), and links the setup guide.
- [ ] No credential/secret field on either role.
- [ ] `RouterConfig.from_yaml` parses the file with each `enabled_when` var both
      set and unset; all other roles unchanged.
- [ ] `yamllint` (if configured) clean.
