# 02 - Error taxonomy & sanitised botocore mapping

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - broaden error-code coverage
**Depends on:** 01
**Blocks:** 04, 05

## Objective

Map every `botocore` failure mode (client error, transport error, throttling,
mid-stream interruption) onto the project's `AIBackendError`, carrying a
**sanitised** message only - never the raw provider payload, request metadata, or
any credential. No `botocore` exception may escape the backend.

The plan text (§3.2) originally named a `BedrockBackendError`; the codebase
instead reuses the **generic `AIBackendError`** shared by all AI providers. That
is the accepted decision - one transport-layer error type across providers keeps
the orchestrator's failure handling provider-neutral. This subtask records and
enforces that choice.

## Files

- **Verify** `src/aegis_swr/core/exceptions.py` - `AIBackendError(AegisSWRError)`
  exists with a docstring stating it carries a sanitised message only.
- **Modify/verify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py` - the
  `except` blocks in `_invoke` and `stream`.

## Symbols

- `AIBackendError(AegisSWRError)` - already defined; no new exception class.
- In the provider, both `converse` and `converse_stream` call sites catch:
  - `botocore.exceptions.ClientError` → extract `Error.Code` only, log the code,
    raise `AIBackendError(f"... ({code})")`.
  - `botocore.exceptions.BotoCoreError` (transport/timeout) → raise
    `AIBackendError(f"... transport error ... {type(exc).__name__}")`.
  - Stream `next()` interruption → `BotoCoreError` → `AIBackendError`.
- `from exc` chaining is preserved internally; the public message stays sanitised.

## Constraints

- **No credential or payload text** in any raised message or log line. Only the
  error **code** / exception **type name** and the model id may appear.
- No bare `except:`; catch the specific botocore base classes.
- The `SensitiveFilter` on the logging layer remains the backstop for any
  botocore/urllib3 debug logging; this module logs only non-sensitive metadata.

## Tests

**Unit / mock** (`tests/unit/test_ai_backends.py`):

- `test_bedrock_client_error_becomes_backend_error` *(exists)* - a stubbed
  `ClientError` with `ThrottlingException` raises `AIBackendError`, not the raw
  `ClientError`.
- **Add** `test_bedrock_client_error_codes_parametrized` - parametrise over
  `AccessDeniedException`, `ServiceUnavailableException`,
  `ValidationException`, `ModelTimeoutException`; each surfaces as
  `AIBackendError` and the message contains the code but **no** credential text.
- **Add** `test_bedrock_error_message_is_sanitised` - the raised message contains
  no `AWS_BEARER_TOKEN_BEDROCK` value and no `aws_secret_access_key` even when the
  stubbed error response embeds them in metadata.

**Integration** (`tests/integration/test_bedrock_integration.py`):

- `test_bedrock_transport_error_raises_backend_error` *(exists)* - a
  `ReadTimeoutError` (`BotoCoreError`) from the real backend over a mocked client
  surfaces as `AIBackendError`.

## Success criteria

- [ ] No `botocore` exception type escapes `_invoke` or `stream`.
- [ ] `ClientError` and `BotoCoreError` both map to `AIBackendError`.
- [ ] Raised messages and emitted logs contain no credential/payload text
      (verified by an assertion, not just by inspection).
- [ ] Parametrised error-code test passes for ≥4 distinct Bedrock error codes.
