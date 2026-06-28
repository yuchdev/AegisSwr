# 03 - Client construction & dual-mode authentication

**Parent milestone:** 3.2 AWS Bedrock Backend
**State:** ✅ Done - add a region-precedence test
**Depends on:** 01, 02
**Blocks:** 04, 05

## Objective

Construct the `bedrock-runtime` client with the configured timeouts/retries and
support **two** authentication modes without ever storing or logging a secret:

1. **Bearer token** - when `AWS_BEARER_TOKEN_BEDROCK` is set, inject
   `Authorization: Bearer <token>` on every request (Bedrock API-key auth).
2. **SigV4 credential chain** - otherwise rely on the standard boto3 chain (env
   vars / shared config / IAM role).

## Files

- **Modify/verify** `src/aegis_swr/backends/ai/aws_bedrock_provider.py`

## Symbols (in `AwsBedrockBackend`)

- `__init__(self, settings: AISettings)` - stores `self._bedrock`, builds
  `self._client: Any` via `_build_client()`. Typed `Any` to avoid coupling to
  botocore's generated stubs.
- `_build_client(self) -> Any`:
  - region precedence: `settings.bedrock.region` wins; falls back to
    `os.environ["AWS_DEFAULT_REGION"]` only when the setting is blank.
  - `botocore.config.Config(retries={"max_attempts": ..., "mode": "standard"},
    connect_timeout=..., read_timeout=...)`.
  - creates the client via `boto3.Session(region_name=...).client("bedrock-runtime", ...)`.
  - registers the bearer hook when the env token is present; logs only
    non-sensitive metadata (region, model, auth-mode label).
- `_register_bearer_auth_hook(client, raw_token) -> None` *(staticmethod)*:
  - registers a `before-send.bedrock-runtime.*` event handler that sets the
    `Authorization` header; the token is captured in the closure and never logged.
- Module constants: `_BEARER_TOKEN_ENV = "AWS_BEARER_TOKEN_BEDROCK"`.

## Constraints

- The bearer token and AWS secrets are read from the environment only; they are
  never assigned to an instance attribute beyond the closure, never logged, and
  never serialised.
- `before-send` is chosen deliberately so the injected header wins over SigV4.
- All network round-trips happen later (04/05) on a worker thread via
  `asyncio.to_thread`; the client itself is constructed synchronously in
  `__init__`.

## Tests

**Unit / mock** (`tests/unit/test_ai_backends.py`, patch `boto3.Session`):

- `test_bedrock_registers_bearer_hook_when_token_present` *(exists)* - with
  `AWS_BEARER_TOKEN_BEDROCK` set, `client.meta.events.register` is called for
  `before-send.bedrock-runtime.*`.
- `test_bedrock_no_bearer_hook_without_token` *(exists)* - without the env token,
  no bearer hook is registered (SigV4 path).
- **Add** `test_bedrock_region_precedence` - `bedrock.region` set → client built
  with that region; `bedrock.region` blank + `AWS_DEFAULT_REGION` set → client
  built with the env region.
- **Add** `test_bedrock_bearer_hook_does_not_log_token` - the captured log
  records contain the auth-mode label but not the token value.

## Success criteria

- [ ] Client is built with the configured connect/read timeouts and
      `max_attempts` retry config.
- [ ] Bearer-token mode injects the `Authorization` header via a `before-send`
      hook; SigV4 mode registers no hook.
- [ ] Region precedence is `settings.bedrock.region` → `AWS_DEFAULT_REGION`.
- [ ] No token/secret appears in any instance attribute, log line, or repr.
- [ ] The four unit tests above pass with `boto3` fully patched (no network).
