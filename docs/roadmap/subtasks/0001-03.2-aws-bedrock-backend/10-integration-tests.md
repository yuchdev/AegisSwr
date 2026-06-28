# 10 - End-to-end integration tests

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - extend coverage
**Depends on:** 04, 05, 07
**Blocks:** none

## Objective

Prove the Bedrock backend works through the real pipeline seam - `IncidentSource
→ DataAdapter → IncidentBrief → AwsBedrockBackend` - with the boto3 client fully
mocked (zero network), per the testing mandate that every external integration
ships an integration test with the external mocked.

## Files

- **Modify/verify** `tests/integration/test_bedrock_integration.py`

## Existing tests

- `test_adapter_to_bedrock_backend_structured` - adapter output drives a real
  `AwsBedrockBackend.generate()` (client stubbed) to a validated `OSKernelOutput`;
  asserts adapter-extracted fields reach the request and PII stays scrubbed.
- `test_adapter_to_bedrock_backend_stream` - the same path through `stream()`,
  asserting ordered text deltas.
- `test_bedrock_transport_error_raises_backend_error` - a `BotoCoreError`
  (`ReadTimeoutError`) surfaces as `AIBackendError`.

## Tests to add

- `test_bedrock_token_usage_propagates_to_state` - after a generate call, the
  accumulated `last_usage` is non-zero and would feed `InvestigationState.token_tracker`.
- `test_bedrock_structured_retry_end_to_end` - first stubbed response invalid,
  second valid → the pipeline yields a validated structured object (exercises the
  base retry loop through the real backend).
- `test_bedrock_pii_never_reaches_request` - an `IncidentSource` carrying PII is
  processed; assert the Converse request body contains only scrubbed text.

## Constraints

- **Zero network**: stub `boto3` / the `bedrock-runtime` client (or
  `botocore.stub.Stubber`); no live AWS calls.
- Reuse the shared adapter/source fixtures from `tests/unit/fixtures/`.
- Assertions confirm scrubbed payloads and sanitised errors, never raw secrets.

## Success criteria

- [ ] The adapter→Bedrock structured and streaming paths pass with the client
      mocked.
- [ ] Transport and retry failure paths are covered end to end.
- [ ] Token usage propagation and PII-scrubbing-before-request are asserted.
- [ ] `poetry run pytest tests/integration/test_bedrock_integration.py -q`
      passes with no network access.
