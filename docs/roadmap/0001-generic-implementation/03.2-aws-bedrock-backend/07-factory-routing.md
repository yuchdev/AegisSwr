# 07 - Factory routing for `provider="bedrock"`

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done
**Depends on:** 01, 03, 04
**Blocks:** 08, 10

## Objective

Wire the Bedrock backend into the AI Factory-Strategy seam so that
`provider="bedrock"` constructs an `AwsBedrockBackend`, with no provider-specific
branching leaking outside the factory.

## Files

- **Modify/verify** `src/aegis_swr/backends/ai/__init__.py`

## Symbols

- `create_ai_backend(settings: AISettings) -> AIAPIBackend`:
  - `"anthropic"` → `AnthropicBackend`
  - `"openai"` → `OpenAIBackend`
  - `"bedrock"` → `AwsBedrockBackend`
  - unknown → `raise ValueError(f"Unknown AI provider: {settings.provider!r}")`
- `__all__` includes `"AwsBedrockBackend"` and `"create_ai_backend"`.

## Constraints

- The only place that maps a provider string to a class is this factory.
- The unknown-provider branch raises `ValueError` (provider-string validation
  also happens in `AISettings`, subtask 01, but the factory stays defensive).

## Tests

**Unit** (`tests/unit/test_ai_backends.py`):

- `test_factory_returns_bedrock` *(exists)* - `create_ai_backend(settings)` with
  `provider="bedrock"` returns an `AwsBedrockBackend` instance (boto3 patched).
- `test_factory_unknown_provider_raises` *(exists/verify)* - an unknown provider
  raises `ValueError`.

## Success criteria

- [ ] `create_ai_backend` returns `AwsBedrockBackend` for `provider="bedrock"`
      and is unchanged for `anthropic`/`openai`.
- [ ] No provider branching exists outside the factory.
- [ ] `AwsBedrockBackend` is exported in `__all__`.
- [ ] The unit tests pass with boto3 patched.
