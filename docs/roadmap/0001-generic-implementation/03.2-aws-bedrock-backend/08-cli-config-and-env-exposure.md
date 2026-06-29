# 08 - CLI flag, config template & `.env.example`

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** 🔶 Partial - `--ai` done; config template & env doc missing
**Depends on:** 01, 07
**Blocks:** 09

## Objective

Make the Bedrock backend selectable and configurable through the operator
surface: the `--ai` provider flag (done), a documented `bedrock` section in the
config template, and an `.env.example` that documents the AWS auth variables
**without ever embedding a secret value**.

## Current state

- ✅ `--ai` flag exists in `cli/commands.py` (help: `anthropic | openai | bedrock`)
  and routes to `backends.ai.provider`.
- ✅ Bedrock sub-options (`region`, `model_id`, `thinking_budget_tokens`,
  timeouts, `max_attempts`) are reachable via `aegis config set
  backends.ai.bedrock.*` and `AEGIS__backends__ai__bedrock__*` env overrides.
- ❌ `config.example.json` has **no** `backends.ai.bedrock` section.
- ❌ There is **no** `.env.example` documenting `AWS_BEARER_TOKEN_BEDROCK` /
  `AWS_DEFAULT_REGION` / standard AWS credential variables.

## Files

- **Modify** `config.example.json` - add a `backends.ai.bedrock` block mirroring
  the `BedrockSettings` defaults (region, model_id, thinking_budget_tokens,
  connect_timeout_seconds, read_timeout_seconds, max_attempts).
- **Create** `.env.example` - document, with placeholder/empty values only:
  - `AWS_BEARER_TOKEN_BEDROCK=` (Bedrock API-key auth; optional)
  - `AWS_DEFAULT_REGION=` (used when `bedrock.region` is blank)
  - a comment that, absent the bearer token, the standard AWS credential chain
    (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / IAM role) is used by boto3.
- **Verify** `cli/commands.py` - `--ai bedrock` reaches `backends.ai.provider`.

## Decision (record in the doc, not as code)

Bedrock sub-options remain **config-/env-only** (no dedicated `--bedrock-region`
etc. CLI flags). Rationale: they are deployment-stable settings, not per-run
knobs; adding flags would bloat the `analyze` surface. If a per-run override is
later needed, add it as a follow-up - it is explicitly out of scope here.

## Constraints

- `.env.example` and `config.example.json` contain **no real secret values** -
  the `secret_scan` hook must pass on both.
- Region/model defaults in the template must match `BedrockSettings` defaults.

## Tests

**Unit / mock** (`tests/unit/test_cli.py`):

- `test_cli_ai_bedrock_sets_provider` - `aegis analyze --ai bedrock ...` results
  in `backends.ai.provider == "bedrock"` reaching the backend factory (factory
  patched; assert the provider value, no network).
- `test_config_example_has_bedrock_section` - load `config.example.json` and
  assert it parses into the four-section schema **and** contains a
  `backends.ai.bedrock` block whose keys match `BedrockSettings` fields.
- `test_env_example_documents_bedrock_auth` *(lightweight)* - `.env.example`
  exists and mentions `AWS_BEARER_TOKEN_BEDROCK` and `AWS_DEFAULT_REGION` with no
  assigned secret value.

## Success criteria

- [ ] `aegis analyze --ai bedrock` selects the Bedrock backend end to end.
- [ ] `config.example.json` carries a `backends.ai.bedrock` block matching the
      settings defaults and still parses cleanly.
- [ ] `.env.example` exists and documents the AWS auth variables with empty
      placeholders; `secret_scan` passes.
- [ ] The CLI/config tests above pass with the factory/network mocked.
