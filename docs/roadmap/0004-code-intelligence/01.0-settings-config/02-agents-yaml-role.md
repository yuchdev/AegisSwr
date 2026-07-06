# 02 - `agents.yaml` `openclaude_agent` role

**Parent task:** 01.0 OpenClaude Settings & Config
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 03 (this task)

## Objective

Add the `openclaude_agent` role to `aegis/config/agents.yaml` so `RouterConfig`
carries a placeholder entry for OpenClaude even though OpenClaude is not routed
through LiteLLM. This subtask only adds the YAML stanza; the `enabled_when` key
it introduces is given semantics in subtask 03.

## Target schema

Add the following stanza to `aegis/config/agents.yaml` under the existing
`agents:` block:

```yaml
agents:
  # ... existing roles unchanged ...

  openclaude_agent:
    provider: openclaude        # not routed through LiteLLM; see RouterConfig
    model: ~                    # model is OpenClaude's concern, not Aegis SWR's
    timeout_s: 120
    enabled_when: OPENCLAUDE_GRPC_URL   # role omitted from validation when var absent
```

## Changes

1. Add the `openclaude_agent:` entry above to the `agents:` section of
   `aegis/config/agents.yaml`. No other roles in the file are modified.
2. `enabled_when` is a new, optional key on any agent role (schema-level
   addition only in this subtask; parsing behaviour is subtask 03 /
   `03-router-config-enabled-when.md`). Its value is the **name** of an
   environment variable (not the value of that variable). The role is
   considered active when the named variable is set to any non-empty string in
   the process environment.
3. `model: ~` (YAML null) documents that OpenClaude's model choice is entirely
   the operator's concern (set via OpenClaude's own env vars, per the
   milestone's "User-supplied model contract") - Aegis SWR never resolves a
   LiteLLM model string for this role.

## Constraints

- No Python code changes in this subtask (`RouterConfig` parsing changes are
  subtask 03).
- The YAML file must remain valid against the existing schema validator after
  the addition - no extra keys rejected by strict YAML schema checks if such
  checks exist.
- No credentials or secrets in this stanza - `openclaude_agent` carries no
  `api_key` field (OpenClaude is not a `providers:` entry).

## Success criteria

- [ ] `openclaude_agent:` stanza present in `aegis/config/agents.yaml` with
      `provider`, `model`, `timeout_s`, `enabled_when` fields as specified.
- [ ] All existing roles in `agents.yaml` are byte-for-byte unchanged.
- [ ] `yamllint` (if configured) reports no errors on the updated file.
- [ ] The file still parses without raising *before* subtask 03 lands (i.e.
      an as-yet-unaware `RouterConfig.from_yaml()` does not choke on the new
      `enabled_when` key - Pydantic/dataclass parsing must tolerate or subtask
      03 must land atomically with this one; see Task 01.0 README ordering
      note).
