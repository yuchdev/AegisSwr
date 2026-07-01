# 01 - `providers` block in agents.yaml

**Parent task:** 01.0 agents.yaml Schema Extension
**State:** ⬜ Not started
**Depends on:** none
**Blocks:** 02, 03

## Objective

Add a top-level `providers` block to `aegis/config/agents.yaml` that declares
each model provider's credentials and base URL. All secret values must use
`${ENV_VAR}` references - no hard-coded credentials.

## Target schema

```yaml
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    # base_url omitted - LiteLLM uses Anthropic's hardcoded endpoint

  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    base_url: https://api.deepseek.com/v1

  self_hosted:
    base_url: ${VLLM_BASE_URL}/v1
    api_key: ${VLLM_API_KEY}      # may be empty string for unauthenticated
```

## Changes

1. Add the `providers:` section above the existing `agents:` section in
   `aegis/config/agents.yaml`.
2. Keep all existing fields in the `agents:` section unchanged (this subtask
   adds no new agent fields - that is subtask 02).
3. Update `.env.example` to document:
   - `ANTHROPIC_API_KEY`
   - `DEEPSEEK_API_KEY`
   - `VLLM_BASE_URL` (e.g. `http://localhost:8000`)
   - `VLLM_API_KEY` (optional, may be empty)

## Constraints

- The `base_url` field is optional per provider; providers with a vendor-fixed
  URL (like Anthropic) omit it.
- `api_key` is always present, even if the resolved value is an empty string
  (e.g. unauthenticated self-hosted).
- No Python code changes in this subtask.

## Success criteria

- [ ] `providers:` block with `anthropic`, `deepseek`, `self_hosted` keys
      present in `aegis/config/agents.yaml`.
- [ ] All credential values use `${ENV_VAR}` placeholders (no literal keys).
- [ ] `.env.example` documents all four environment variables.
- [ ] `yamllint` (if configured) reports no errors on the updated file.
