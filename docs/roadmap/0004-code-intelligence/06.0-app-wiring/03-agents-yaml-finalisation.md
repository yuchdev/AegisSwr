# 03 - agents.yaml openclaude_agent finalisation

**Parent task:** 06.0 App Wiring & agents.yaml
**State:** ⬜ Not started
**Depends on:** 01 (composition root uses `settings.openclaude`); Task 01.0
subtask 02 (initial `openclaude_agent` stanza) and subtask 03 (`enabled_when`
parsing)
**Blocks:** none

## Objective

Finalise and verify the `openclaude_agent` role in `aegis/config/agents.yaml`
now that the full wiring exists. This is a **finalisation / verification pass**,
not a new-field addition: Task 01.0 subtask 02 already introduced the stanza
(`provider: openclaude`, `model: ~`, `timeout_s: 120`, `enabled_when:
OPENCLAUDE_GRPC_URL`) and subtask 03 gave `enabled_when` its semantics. This
subtask confirms `timeout_s` matches the effective per-request deadline
(`OpenClaudeSettings.request_timeout_s` default of 120s, C1), confirms the
model-selection comment reflects the user-supplied-model contract, and only
edits the stanza if the final `app.py` wiring reveals a mismatch.

## Target stanza (expected final state — confirm, do not gratuitously rewrite)

```yaml
agents:
  # ... existing roles unchanged ...

  openclaude_agent:
    provider: openclaude        # not routed through LiteLLM; see RouterConfig
    # Model selection is entirely OpenClaude's / the operator's concern, set via
    # OpenClaude's own env vars (CLAUDE_CODE_USE_OPENAI, OPENAI_BASE_URL,
    # OPENAI_MODEL, OPENAI_API_KEY). Aegis SWR never resolves a model for this
    # role — see the milestone's "User-supplied model contract".
    model: ~
    timeout_s: 120              # matches OpenClaudeSettings.request_timeout_s default (C1)
    enabled_when: OPENCLAUDE_GRPC_URL   # role inactive when the var is unset
```

## Verification checklist (the substance of this subtask)

1. `timeout_s: 120` equals the `OpenClaudeSettings.request_timeout_s` default
   (C1). If Task 01.0 shipped a different default, reconcile to match — the
   authoritative source is `OpenClaudeSettings`, and the YAML should mirror it
   so the router-level timeout and the gRPC per-request deadline do not diverge.
   Note: `timeout_s` here is the router/agent-role bookkeeping value; the actual
   stream deadline enforced on the wire is `settings.request_timeout_s` inside
   `OpenClaudeGrpcClient`/`OpenClaudeTool`. They must not contradict each other.
2. `model: ~` (YAML null) remains — Aegis SWR resolves no LiteLLM model for this
   role. Confirm the accompanying comment names the OpenClaude env vars.
3. `enabled_when: OPENCLAUDE_GRPC_URL` is present and its parsing (Task 01.0
   subtask 03) leaves the role omitted from validation when the var is unset —
   consistent with C4 (no backend registered when `grpc_url is None`).
4. No `api_key` or any secret appears on the role (OpenClaude is not a
   `providers:` entry; credentials are the operator's, set on the OpenClaude
   process, never in `agents.yaml`).

## Implementation notes

- If (and only if) final wiring requires an adjustment, state it in the PR: the
  most likely change is aligning `timeout_s` to `request_timeout_s` should the
  01.0 default have drifted. No other field is expected to change.
- Do not add fields speculatively (e.g. no `max_tokens` in the role — that lives
  on `OpenClaudeSettings.max_response_tokens`, not the agent stanza).
- Keep all other agent roles byte-for-byte unchanged.

## Constraints

- No credentials/secrets in the stanza (C7 / security rules).
- YAML remains valid against the existing schema and `RouterConfig.from_yaml`
  after Task 01.0 subtask 03 has landed.
- `enabled_when` value is an env-var **name**, not its value (Task 01.0
  subtask 02 semantics).

## Success criteria

- [ ] `openclaude_agent` role present with `provider`, `model: ~`, `timeout_s`,
      `enabled_when` exactly as the target stanza.
- [ ] `timeout_s` equals `OpenClaudeSettings.request_timeout_s` default (120).
- [ ] The model-selection comment names OpenClaude's own env vars and states
      Aegis SWR does not select the model.
- [ ] No `api_key`/secret field on the role.
- [ ] All other roles in `agents.yaml` unchanged; `RouterConfig.from_yaml`
      parses the file with `OPENCLAUDE_GRPC_URL` both set and unset.
- [ ] `yamllint` (if configured) clean.
