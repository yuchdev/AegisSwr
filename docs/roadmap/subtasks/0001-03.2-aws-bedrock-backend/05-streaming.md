# 05 - Streaming via `converse_stream`

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - add a mid-stream interruption test
**Depends on:** 03, 04
**Blocks:** 10

## Objective

Implement token streaming through Bedrock's `converse_stream`, yielding text
deltas as they arrive without blocking the event loop, and mapping any
mid-stream transport failure onto `AIBackendError`.

## Files

- **Modify/verify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py`

## Symbols (in `AwsBedrockBackend`)

- `async def stream(self, system_prompt, messages) -> AsyncGenerator[str, None]`:
  - builds a no-schema request via `_build_request(..., output_schema=None)`.
  - `response = await asyncio.to_thread(self._client.converse_stream, **request)`;
    botocore errors here map to `AIBackendError` (subtask 02).
  - iterates `response["stream"]` (a synchronous, network-backed `EventStream`)
    by pulling each event on a worker thread:
    `event = await asyncio.to_thread(next, iterator, _STREAM_DONE)`.
  - extracts `event["contentBlockDelta"]["delta"]["text"]` and yields non-empty
    text; stops on the `_STREAM_DONE` sentinel.
- Module constant `_STREAM_DONE = object()` - a sentinel distinct from a
  legitimate `None` event so exhaustion is unambiguous.

## Constraints

- Each `next()` on the event stream is dispatched via `asyncio.to_thread`, so a
  slow/network-backed iterator never blocks the loop.
- A `BotoCoreError` raised while pulling events is caught and re-raised as
  `AIBackendError` (sanitised) - the generator must not leak a raw botocore error.
- Signature parity with `AnthropicBackend.stream` / `OpenAIBackend.stream`.

## Tests

**Unit / mock** (`tests/unit/test_ai_backends.py`):

- `test_bedrock_stream_yields_tokens` *(exists)* - a stubbed event sequence with
  `contentBlockDelta` text blocks yields the expected tokens in order; empty
  deltas are skipped.
- **Add** `test_bedrock_stream_interruption_raises_backend_error` - the stubbed
  iterator raises a `BotoCoreError` partway through; the async generator surfaces
  `AIBackendError` (not the raw botocore error) after the earlier tokens.
- **Add** `test_bedrock_stream_does_not_block_loop` *(optional)* - assert the
  iteration path goes through `asyncio.to_thread` (e.g. patch and count calls).

**Integration** - `test_adapter_to_bedrock_backend_stream` (subtask 10).

## Success criteria

- [ ] `stream()` yields ≥1 non-empty token from a stubbed `converse_stream`
      sequence and terminates cleanly on exhaustion.
- [ ] A mid-stream `BotoCoreError` surfaces as `AIBackendError`.
- [ ] No event-stream `next()` blocks the event loop.
- [ ] Signature matches the other providers' `stream`.
