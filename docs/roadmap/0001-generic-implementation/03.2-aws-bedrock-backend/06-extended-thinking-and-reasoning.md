# 06 - Extended thinking & `has_reasoning`

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - add a reasoningContent extraction test
**Depends on:** 01, 04
**Blocks:** none

## Objective

Enable Bedrock extended thinking on supporting model families, gated so it is
only requested where the API permits it, and expose a provider-neutral
`has_reasoning` capability flag consistent with the other backends.

## Files

- **Modify/verify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py`
- **Uses** `BedrockSettings.thinking_budget_tokens` (subtask 01)

## Symbols (in `AwsBedrockBackend`)

- Module constants:
  - `_THINKING_BUDGET_MIN = 1_024` - sub-minimum budgets count as disabled
    (Claude rejects smaller budgets).
  - `_THINKING_SUPPORTED_PATTERNS = ("anthropic.claude", "nova-pro-v1")` -
    families known to accept the `thinking` field; unknown models default to "no
    thinking" so an unsupported `additionalModelRequestFields.thinking` key never
    triggers a `ValidationException`.
- `_thinking_supported(model_id: str) -> bool` *(module function)* - case-insensitive
  pattern match.
- `_thinking_enabled(self, output_schema) -> bool`:
  - returns `False` whenever `output_schema is not None` (Claude rejects thinking
    under forced tool use).
  - otherwise `True` iff `thinking_budget_tokens >= _THINKING_BUDGET_MIN` **and**
    `_thinking_supported(self.model_name)`.
- `has_reasoning` property → `_thinking_supported(self.model_name)` (capability,
  independent of the configured budget).
- In `_build_request`: when thinking is enabled, set
  `additionalModelRequestFields = {"thinking": {"type": "enabled",
  "budget_tokens": ...}}` and force `inferenceConfig.temperature = 1.0` (Claude
  requires temperature 1 when a thinking block is present).

## Constraints

- Thinking is **never** sent for structured (schema) requests.
- Unknown model families never receive the `thinking` key.
- `has_reasoning` parity with `AnthropicBackend` (markers) and `OpenAIBackend`
  (always `False`).

## Tests

**Unit** (`tests/unit/test_ai_backends.py`):

- `test_bedrock_thinking_enabled_for_free_form` *(exists)* - supporting model +
  budget ≥ 1024 + no schema → request carries the `thinking` block and
  `temperature == 1.0`.
- `test_bedrock_has_reasoning` *(exists, parametrized)* - `has_reasoning` is
  `True` for `anthropic.claude*` / `nova-pro-v1`, `False` otherwise.
- **Add** `test_bedrock_thinking_disabled_for_structured` - schema request never
  includes the `thinking` field even when the budget qualifies.
- **Add** `test_bedrock_thinking_disabled_for_unsupported_model` - unsupported
  `model_id` never includes the `thinking` field.
- **Add** `test_bedrock_parse_ignores_reasoning_blocks` - a free-form response
  containing a `reasoningContent` block plus `text` blocks returns only the
  concatenated `text` (reasoning is not leaked into the answer).

## Success criteria

- [ ] Thinking is requested only for free-form output on a supported model with a
      qualifying budget; `temperature` is forced to `1.0` in that case.
- [ ] Structured and unsupported-model requests never carry the `thinking` field.
- [ ] `has_reasoning` reflects model capability and matches the cross-provider
      contract.
- [ ] `_parse` ignores `reasoningContent` blocks.
- [ ] All listed unit tests pass.
