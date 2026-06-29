# 04 - Converse `generate()`: request, structured output, parse, usage

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done
**Depends on:** 01, 02, 03
**Blocks:** 05 (shares request builder), 10, 11

## Objective

Implement the non-streaming generation path against the Bedrock **Converse API**:
build a provider-neutral request, request structured output via forced tool use,
parse the response, and report token usage - reusing the shared `_BaseAIBackend`
validation + one-shot correction-retry loop so behaviour matches the Anthropic
and OpenAI providers.

## Files

- **Modify/verify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py`

## Symbols (in `AwsBedrockBackend`)

- `_to_converse_messages(messages) -> list[dict]` *(staticmethod)* - adapts the
  base's `{"role", "content": <str>}` to Converse's typed-block shape
  `{"role", "content": [{"text": ...}]}`.
- `_build_request(system_prompt, messages, output_schema) -> dict`:
  - `modelId`, `system=[{"text": system_prompt}]`,
    `messages=_to_converse_messages(...)`,
    `inferenceConfig={"maxTokens": settings.max_tokens, "temperature": ...}`.
  - when `output_schema` is given: `toolConfig` with a single `toolSpec` named
    `structured_output` whose `inputSchema.json` is
    `output_schema.model_json_schema()`, and
    `toolChoice={"tool": {"name": "structured_output"}}` (forced).
  - thinking fields handled in subtask 06.
- `_parse(response, output_schema) -> str | dict`:
  - structured: return the first `toolUse` block's `input` as a dict; if none,
    raise `AIOutputValidationError`.
  - free-form: concatenate `text` blocks, ignoring reasoning blocks.
- `_usage(response) -> dict[str, int]` *(staticmethod)* - reads
  `usage.inputTokens` / `usage.outputTokens` (cache counters are subtask 11).
- `_invoke(system_prompt, messages, output_schema) -> tuple[str | dict, dict]`:
  - `await asyncio.to_thread(self._client.converse, **request)`.
  - wraps botocore errors per subtask 02; returns `(_parse(...), _usage(...))`.
- Module constant `_STRUCTURED_TOOL_NAME = "structured_output"`.

The public `generate()` and the retry loop live in `_BaseAIBackend` (subtask
shared); this subtask only supplies `_invoke` + helpers.

## Constraints

- boto3 is synchronous → **every** call to `converse` runs on a worker thread via
  `asyncio.to_thread`; the event loop is never blocked.
- Structured output is **forced** tool use (`toolChoice`), matching the Anthropic
  backend's strategy.
- Full annotations; `Optional[type[BaseModel]]` for `output_schema`.

## Tests

**Unit / mock** (`tests/unit/test_ai_backends.py`, stub the client's `converse`):

- `test_bedrock_structured_output_valid` *(exists)* - a stubbed `toolUse`
  response validates into the target model; `last_usage` reflects token counts.
- `test_bedrock_sends_tool_config_and_system` *(exists)* - the request carries
  `modelId`, a `system` block, and a `toolConfig` with the forced
  `structured_output` tool.
- `test_bedrock_retry_then_valid` *(exists)* - first response invalid, second
  valid → returns the model; usage accumulates across both attempts.
- `test_bedrock_raises_after_retry` *(exists)* - two invalid responses →
  `AIOutputValidationError`.
- `test_bedrock_raises_when_no_tool_block` *(exists)* - structured request with no
  `toolUse` block → `AIOutputValidationError`.
- `test_bedrock_unstructured_returns_text` *(exists)* - no schema → concatenated
  text from the `text` blocks.

**Integration** - covered in subtask 10.

## Success criteria

- [ ] `generate()` with a `Hypothesis` schema returns a validated `Hypothesis`
      from a stubbed Converse `toolUse` response.
- [ ] The request forces the `structured_output` tool when a schema is supplied.
- [ ] Token usage is read from the `usage` block and surfaced via `last_usage`.
- [ ] All six unit tests pass with the client stubbed (no network).
- [ ] No `converse` call blocks the event loop (dispatched via `to_thread`).
