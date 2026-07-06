# Threat Model - AWS Bedrock AI backend - 2026-06-29

Scope reviewed:

- `src/aegis_swr/backends/ai/aws_bedrock_provider.py` (auth hook, client build, request build, converse/stream, error mapping)
- `src/aegis_swr/config/settings.py` (`BedrockSettings`, `_SECRET_KEYS`, `redacted_dump`/`_redact_secrets`)
- `src/aegis_swr/backends/ai/__init__.py` (factory)
- `config.example.json` (bedrock config block)
- Cross-cutting: `src/aegis_swr/cli/aegis_logging.py` (`_sensitive_filter`, `NOISY_LIBRARY_LOGGERS`), `src/aegis_swr/core/exceptions.py`, `src/aegis_swr/backends/ai/_base.py`

## Assets & trust boundaries

Assets:

- **Bedrock bearer token** (`AWS_BEARER_TOKEN_BEDROCK`) - long-lived API-key credential, radioactive.
- **SigV4 credential chain** (env / shared config / IAM role) - fallback auth material.
- **Incident payload text** (crash dumps, stacks, logs) - attacker-influenced and may contain third-party secrets/PII. Flows into the Converse request `messages`/`system`.
- **Model output** - returned to the pipeline; downstream report storage is out of scope here.

Trust boundaries crossed:

1. Untrusted payload → `_build_request` → Bedrock Converse request body → network → AWS (egress of confidential data to an external service; expected and authorised).
2. Environment (secret) → `_register_bearer_auth_hook` closure → HTTP `Authorization` header on every request.
3. botocore/urllib3 internals → stdlib `logging` → log sinks (the SensitiveFilter coverage boundary).
4. botocore exceptions (which may echo request data / headers) → `AIBackendError` → caller/API error body.

The boundary that matters most: the bearer token and the raw payload both transit the same client that emits verbose stdlib debug logs, so log-sink coverage is the critical control.

## Findings

### [MEDIUM] botocore / urllib3 stdlib loggers are not redacted and not clamped to WARNING

- Vector / evidence: `src/aegis_swr/cli/aegis_logging.py:31-37` - `NOISY_LIBRARY_LOGGERS` clamps only `anthropic, openai, httpx, google.auth, google.api_core`. **`botocore`, `boto3`, `botocore.endpoint`, `botocore.auth`, `urllib3` are absent.** The Bedrock backend is the only AI provider that routes through botocore/urllib3, so it is uniquely exposed. The redaction filter `_sensitive_filter` (`aegis_logging.py:40-44`) is a **loguru** filter; it is attached only to loguru sinks (`aegis_logging.py:138,74`). There is no `logging.Handler`/InterceptHandler bridging stdlib logging into loguru (confirmed: no intercept handler anywhere in `src/`), so botocore/urllib3 records bypass `_sensitive_filter` entirely.
- The module docstring's claim is therefore inaccurate: `aws_bedrock_provider.py:21-22` states "botocore/urllib3 request-body logging is left to the project `SensitiveFilter` applied at the logging layer" - but that filter does not see those records, and the loggers are not clamped. At DEBUG, `botocore.endpoint`/`urllib3` emit full request bodies (the incident payload) and `botocore.auth`/wire debug can emit headers (the `Authorization: Bearer <token>`).
- Impact: information disclosure (CWE-532 Insufficiently Protected Credentials in log / OWASP A09:2021 Security Logging Failures). At an operator-selected DEBUG/TRACE level, the bearer token and raw incident payload could be written to the application log file. Requires DEBUG logging to trigger (the default is INFO), so not CRITICAL, but the defence-in-depth control the code claims to rely on is absent.
- Mitigation: add `botocore`, `boto3`, `urllib3` (and explicitly `botocore.endpoint`, `botocore.auth`) to `NOISY_LIBRARY_LOGGERS` so they are clamped to WARNING regardless of the user level; and/or install a stdlib→loguru InterceptHandler so the redaction filter actually covers these records. Then correct the docstring at `aws_bedrock_provider.py:21-22` to match reality.

### [MEDIUM] Redaction regex misses the live `Authorization: Bearer <token>` form

- Vector / evidence: `src/aegis_swr/cli/aegis_logging.py:20-26`. The alternation `(... |bearer)\s*[=:]\s*\S+` requires `bearer` to be followed by `=` or `:`. The header the backend actually injects is `Authorization: Bearer <token>` (`aws_bedrock_provider.py:138`), where `Bearer` is followed by a **space**. Verified empirically: `Authorization: Bearer ABCXYZTOKEN123` and bare `Bearer ABCXYZTOKEN123` are **not** redacted; only the `AWS_BEARER_TOKEN_BEDROCK=...` env-style form is caught.
- Impact: if the token ever reaches a loguru message in header form (e.g. a future log line, or a stdlib record once the InterceptHandler from the previous finding is added), it would pass through unredacted. CWE-532. Compounds finding 1.
- Mitigation: extend the regex to match `bearer\s+\S+` (whitespace-separated) and an `authorization\s*[=:]\s*\S+` clause. Hand to `python-expert`; add a regression test (token in `Authorization: Bearer ...` form is redacted) via `testing-expert`.

### [LOW] Token interpolated into header value via f-string - header-injection assessment

- Vector / evidence: `aws_bedrock_provider.py:137-138` - `request.headers["Authorization"] = f"Bearer {raw_token}"`. The value originates solely from `os.environ[AWS_BEARER_TOKEN_BEDROCK]` (`:103`), an operator-controlled trusted secret, never from incident payload. The header **name** is a constant. urllib3 rejects CR/LF in header values, so a malformed token would error rather than inject. No untrusted data participates.
- Impact: negligible header/CRLF-injection risk under the current trust model (the secret is operator-supplied, not attacker-influenced). Noted only because a credential interpolated into a header is a pattern worth guarding if the token source ever changes.
- Mitigation: none required now. If a future change sources the token from anywhere less trusted, strip/validate (reject CR/LF) before assignment.

### [LOW] No client-side request-size / payload cap before egress (DoS / cost)

- Vector / evidence: `aws_bedrock_provider.py:169-209` builds the Converse request from `messages` with no client-side size guard; the incident payload (`_to_converse_messages`, `:144-154`) is sent verbatim. Output is bounded (`maxTokens`, `:177`) and all network calls have connect/read timeouts and bounded retries (`:90-94`, `BedrockSettings.connect_timeout_seconds/read_timeout_seconds/max_attempts` at `settings.py:293-295`), so the call cannot hang the loop and streaming is pulled via `asyncio.to_thread(next, ...)` with a sentinel (`aws_bedrock_provider.py:292-303`) - no unbounded loop-blocking. The residual risk is a very large attacker-influenced payload inflating input-token cost / latency.
- Impact: token-budget / cost-exhaustion DoS on huge dumps (the `core/tokens.py` budget concern). Input-side truncation is the pipeline's responsibility (`CoreSettings.stack_frames_limit`, `user_assumption_token_limit`), so this is a defence-in-depth note, not a backend defect.
- Mitigation: confirm upstream truncation/token-budgeting is enforced before `generate()`; optionally add an input-token guard in the shared base. Follow-up, not blocking.

## Things verified clean (no finding)

- **Token never stored on the instance**: held only in the `_inject_auth_header` closure (`aws_bedrock_provider.py:137-140`); not assigned to `self`, not in `BedrockSettings` (`settings.py:257-310`), not serialised. `redacted_dump`/`_redact_secrets` (`settings.py:725-751`) operates on settings only; since the token is not a settings field there is nothing to leak there.
- **`_SECRET_KEYS` coverage** (`settings.py:54`): `{"api_key","password","secret","token","database_url"}` is substring/case-insensitive matched. No new sensitive *config* keys were introduced by Bedrock (`region`, `model_id`, budgets, timeouts, `auth_mode` are all non-secret); the token lives in env, not config, so the set remains adequate.
- **`config.example.json`**: the `backends.ai.bedrock` block (`config.example.json:78-94`) carries only region/model/budgets/timeouts/`auth_mode` - **no token, no AWS keys, no secret of any kind**. Clean.
- **Auth-mode debug logs**: `aws_bedrock_provider.py:106-118` log region, model, and the auth *mode* string only - never the token value.
- **Error mapping does not leak request data**: `ClientError` is mapped using only `Error.Code` (`:255-259`, `:278-282`); `BotoCoreError`/stream-interrupt use only `type(exc).__name__` (`:260-265`, `:283-288`, `:296-301`). Raw botocore exceptions (which can echo request bodies/headers) are chained via `from exc` but never stringified into the `AIBackendError` message, which `exceptions.py:11-15` documents as sanitised-only. No raw payload or credential reaches the caller/API error body.
- **Injection**: untrusted payload reaches only the AI prompt (expected). It never touches a shell, SQL string, `eval`, or a path; the request is a plain dict passed to boto3 (`:253`, `:276`). No injection sink.
- **Untrusted endpoint**: `AWS_BEDROCK_URL` / `AWS_ENDPOINT_NAME_BEDROCK` are **not** referenced in product code (grep-confirmed); the endpoint is derived from `region` by boto3. No SSRF / endpoint-redirection surface today. (Note for future: if a custom `endpoint_url` is ever wired in, it must be validated/allow-listed - an attacker-controlled endpoint would receive both the payload and the bearer token.)

## Verdict: PASS_WITH_FOLLOWUP

No CRITICAL or HIGH finding. The Bedrock provider itself handles the token and payload correctly (closure-scoped secret, metadata-only logs, error mapping by code/type only, region-derived endpoint, fully-timed calls, no injection sink, clean example config). 

The two MEDIUM findings are in the shared logging layer the provider *relies on*, not in the provider's own code: botocore/urllib3 are neither redaction-filtered nor WARNING-clamped (finding 1), and the redaction regex misses the live `Authorization: Bearer <token>` form (finding 2). Together they mean the "SensitiveFilter covers it" assumption in the module docstring is currently false. These are real defence-in-depth gaps but require operator-selected DEBUG/TRACE logging to be exploitable (default is INFO), so they do not block merge.

Required follow-ups (track before relying on Bedrock in production):

1. Clamp/redact botocore, boto3, urllib3 stdlib loggers (or add a stdlib→loguru InterceptHandler), and fix the docstring at `aws_bedrock_provider.py:21-22` - `python-expert`.
2. Extend `_REDACT_RE` to catch `bearer\s+\S+` / `authorization: ...` forms - `python-expert`, with a redaction regression test - `testing-expert`.
3. Confirm upstream input-token/payload truncation before `generate()` (LOW, cost-DoS).
