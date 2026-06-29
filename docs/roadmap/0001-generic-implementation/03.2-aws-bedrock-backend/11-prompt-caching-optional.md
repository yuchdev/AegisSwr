# 11 - Prompt caching via `cachePoint` (optional / deferred)

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ⬜ Deferred - enhancement, not required for the milestone
**Depends on:** 04
**Blocks:** none

## Objective

Reduce token cost on repeated, stable prefixes (the agent persona + the
`IncidentBrief`) by inserting Bedrock **`cachePoint`** blocks where the target
model supports prompt caching, and account for cache token counts in usage. This
mirrors the Anthropic backend's `cache_control: {"type": "ephemeral"}` intent,
adapted to Converse.

> Scoping note: Bedrock Converse supports explicit `cachePoint` content blocks
> and returns cache token counters in `usage` **only for supported models**
> (e.g. recent Claude and Nova families). The feature must **degrade gracefully**
> to a no-op on models that do not support it - never send a `cachePoint` that
> would raise a `ValidationException`. Because support is model-dependent and the
> core path already works without it, this is intentionally deferred.

## Files

- **Modify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py`
- **Modify** `src/aegis_swr/config/settings.py` - add
  `BedrockSettings.enable_prompt_cache: bool = False` (opt-in).

## Symbols (in `AwsBedrockBackend`)

- `_CACHE_SUPPORTED_PATTERNS` - model families known to accept `cachePoint`.
- `_cache_supported(model_id) -> bool` - pattern match, analogous to
  `_thinking_supported`.
- `_build_request` - when `enable_prompt_cache` **and** `_cache_supported(...)`,
  append a `{"cachePoint": {"type": "default"}}` block after the stable `system`
  content (and optionally after the tool config); otherwise omit it.
- `_usage` - additionally read `cacheReadInputTokenCount` /
  `cacheWriteInputTokenCount` when present and fold them into the returned dict
  (e.g. `cache_read_tokens`, `cache_write_tokens`), defaulting to 0.

## Constraints

- Off by default; enabling is opt-in via `BedrockSettings.enable_prompt_cache`.
- No `cachePoint` is ever sent to an unsupported model (guard with
  `_cache_supported`).
- Cache token counters must default to 0 and never break `last_usage` consumers.

## Tests

**Unit / mock** (`tests/unit/test_ai_backends.py`):

- `test_bedrock_cache_point_added_when_enabled_and_supported` - opt-in + supported
  model → request carries a `cachePoint` block after the system content.
- `test_bedrock_no_cache_point_when_unsupported` - unsupported model → no
  `cachePoint` even when enabled.
- `test_bedrock_no_cache_point_when_disabled` - default settings → no `cachePoint`.
- `test_bedrock_usage_reads_cache_counters` - a stubbed response with
  `cacheReadInputTokenCount` populates the cache fields in `last_usage`.

## Success criteria

- [ ] `cachePoint` is inserted only when opt-in **and** the model supports it.
- [ ] Cache token counters are surfaced in usage, defaulting to 0.
- [ ] Unsupported/disabled paths send no `cachePoint` and raise no `ValidationException`.
- [ ] All four unit tests pass with the client stubbed.
- [ ] Explicitly **excluded** from the milestone's definition of done.
