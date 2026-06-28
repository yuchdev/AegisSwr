# 01 - Configuration model (`BedrockSettings` + `AISettings`)

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - verify against this spec
**Depends on:** none
**Blocks:** 02, 03, 04, 07

## Objective

Provide a typed, environment-overridable settings model for the Bedrock backend
and integrate it into `AISettings` so that selecting `provider="bedrock"`
resolves to a Bedrock inference-profile/model identity. No AWS credential value
ever lives in a settings field.

## Files

- **Modify** `src/aegis_swr/config/settings.py`

## Classes / symbols

### `BedrockSettings(BaseSettings)`

Provider-specific knobs, `model_config = SettingsConfigDict(extra="ignore")`.

| Field                     | Type  | Default                                                       | Notes                                                           |
|---------------------------|-------|---------------------------------------------------------------|-----------------------------------------------------------------|
| `region`                  | `str` | `"ap-southeast-2"`                                            | AWS region; falls back to `AWS_DEFAULT_REGION` only when blank. |
| `model_id`                | `str` | `_BEDROCK_DEFAULT_MODEL` (`"au.anthropic.claude-sonnet-4-6"`) | Model ID or cross-region inference profile.                     |
| `thinking_budget_tokens`  | `int` | `0`                                                           | Extended-thinking budget; `0` and sub-1024 mean disabled.       |
| `connect_timeout_seconds` | `int` | `10`                                                          | bedrock-runtime TCP connect timeout.                            |
| `read_timeout_seconds`    | `int` | `300`                                                         | Socket read timeout (reasoning can be slow).                    |
| `max_attempts`            | `int` | `3`                                                           | botocore standard-mode retry attempts.                          |

### `AISettings(BaseSettings)` additions

- `bedrock: BedrockSettings = Field(default_factory=BedrockSettings)` - consulted
  only when `provider == "bedrock"`.
- `provider` validator (`@field_validator("provider")`) accepts
  `{"anthropic", "openai", "bedrock"}`; rejects others with a clear `ValueError`.
- `resolved_model` property: for `provider == "bedrock"` returns
  `self.bedrock.model_id` verbatim (the top-level `model` field is ignored).

## Constraints

- **No credential fields.** `aws_secret_access_key`, session tokens, and
  `AWS_BEARER_TOKEN_BEDROCK` are read from the environment by the provider/boto3,
  never modelled here. (Enforced by 02/03.)
- Full type annotations; `Optional[T]` only (none needed here today).
- Env overrides follow the project pattern (`AEGIS__backends__ai__bedrock__*`).

## Tests

**Unit** (`tests/unit/test_settings.py` or the AI-settings test module):

- `test_bedrock_settings_defaults` - all six fields equal the table defaults.
- `test_ai_provider_validator_accepts_bedrock` - `AISettings(provider="bedrock")`
  constructs; an unknown provider raises `ValidationError`/`ValueError`.
- `test_resolved_model_bedrock_returns_profile_id` - with `provider="bedrock"`
  and a custom `bedrock.model_id`, `resolved_model == bedrock.model_id` even when
  the top-level `model` is left at the Anthropic/OpenAI default.
- `test_bedrock_env_override` - `AEGIS__backends__ai__bedrock__region` overrides
  the default region.

No mock/integration tests required (pure settings).

## Success criteria

- [ ] `BedrockSettings` exposes exactly the six fields above with the listed
      defaults and docstrings.
- [ ] `AISettings.provider` validator includes `"bedrock"`.
- [ ] `resolved_model` returns the Bedrock `model_id` for `provider="bedrock"`.
- [ ] No credential value is representable as a settings field.
- [ ] `mypy --strict` clean; the unit tests above pass.
