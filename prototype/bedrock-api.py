"""
Amazon Bedrock API example using:
- AWS_BEARER_TOKEN_BEDROCK environment variable for bearer-token auth
- Claude Sonnet 4.6 via the AU inference profile (ap-southeast-2)
- Extended thinking / reasoning – enabled automatically for supported models,
  silently skipped for models that reject the 'thinking' key (e.g. Nova 2 Lite)
- Comprehensive error handling for all boto3/botocore exceptions
- Verbose logging of every stage: credential loading, request, response, errors

Model selection notes (ap-southeast-2, 2026-06):
    Direct model IDs require provisioned throughput - use inference profiles.

    Profile                                  Max output   Thinking
    -------                                  ----------   --------
    apac.amazon.nova-pro-v1:0                10 000       yes  ← output too small
    global.amazon.nova-2-lite-v1:0           65 535       NO   ← rejects thinking key
    au.anthropic.claude-haiku-4-5-…          64 000       yes
    au.anthropic.claude-sonnet-4-5-…         64 000       yes
    au.anthropic.claude-sonnet-4-6           unlimited*   yes  ← default
    au.anthropic.claude-opus-4-6-v1          unlimited*   yes

    * accepted maxTokens=99 999 without a ValidationException

Environment overrides:
    BEDROCK_MODEL_ID          model / inference-profile ID
    BEDROCK_MAX_TOKENS        hard output-token cap  (default 64 000)
    BEDROCK_THINKING_BUDGET   thinking budget tokens (default 32 000; set 0 to disable)

Usage:
    export AWS_BEARER_TOKEN_BEDROCK=<your-token>
    python3 bedrock-api.py
    # override model:
    BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0 python3 bedrock-api.py
"""

import json
import logging
import os
import sys
import time

import boto3
import botocore.config
import botocore.exceptions
import botocore.session
from botocore.tokens import ScopedEnvTokenProvider

# ---------------------------------------------------------------------------
# Logging setup – DEBUG level so every event is visible
# ---------------------------------------------------------------------------
LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bedrock_example")

# Reduce noise from urllib3 / botocore internals but keep their WARNINGs
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("botocore.parsers").setLevel(logging.WARNING)
logging.getLogger("botocore.endpoint").setLevel(logging.INFO)
logging.getLogger("botocore.auth").setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-2")

# AU inference profile for Claude Sonnet 4.6 – active in ap-southeast-2,
# no hard output-token cap, extended thinking supported.
# Direct model IDs (e.g. "anthropic.claude-sonnet-4-6") require provisioned
# throughput; the "au." prefix selects on-demand cross-region routing.
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "au.anthropic.claude-sonnet-4-6")

# Token budget for the reasoning / thinking phase.  Must be < MAX_TOKENS.
# Set BEDROCK_THINKING_BUDGET=0 to disable thinking for any model.
# Claude Sonnet/Opus 4.x enforce a minimum of 1 024 budget_tokens.
_THINKING_BUDGET_MIN = 1_024
THINKING_BUDGET_TOKENS = int(os.environ.get("BEDROCK_THINKING_BUDGET", 32_000))

# Hard cap on total output tokens (reasoning + answer).
# au.anthropic.claude-sonnet-4-6 imposes no server-side ceiling,
# so this is a cost/latency guard.
MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", 64_000))

CONTENT = """\
0:000> !analyze -v
*******************************************************************************
*                                                                             *
*                        Exception Analysis                                   *
*                                                                             *
*******************************************************************************

KEY_VALUES_STRING: 1

    Key  : AV.Dereference
    Value: NullPtr

    Key  : AV.Type
    Value: Write

    Key  : Failure.Bucket
    Value: INVALID_POINTER_WRITE_c0000005_CrashUi.exe!std::_Func_impl_no_alloc__Crash_Window::Crash_Window_::_2_::_lambda_1_,__int64,wl::params_::_Do_call

    Key  : Failure.Exception.Code
    Value: 0xc0000005

    Key  : Failure.Exception.IP.Module
    Value: CrashUi

CONTEXT:  (.ecxr)
rip=00007ff6cf6b3c70
CrashUi!Crash_Window::on_access_violation_click [inlined in CrashUi!std::_Func_impl_no_alloc<...>::_Do_call]:
00007ff6`cf6b3c70 c70425000000002a000000 mov dword ptr [0],2Ah ds:00000000`00000000=????????

EXCEPTION_RECORD:  (.exr -1)
ExceptionAddress: 00007ff6cf6b3c70
   ExceptionCode: c0000005 (Access violation)
  ExceptionFlags: 00000000
NumberParameters: 2
   Parameter[0]: 0000000000000001
   Parameter[1]: 0000000000000000
Attempt to write to address 0000000000000000

STACK_TEXT:
(Inline) CrashUi!Crash_Window::on_access_violation_click
(Inline) CrashUi!Crash_Window::{ctor}::__l2::<lambda_1>::operator()
(Inline) CrashUi!std::invoke
00000055`3cafeee8  CrashUi!std::_Func_impl_no_alloc<...>::_Do_call
00000055`3cafeef0  CrashUi!wl::_wli::base_msg<__int64>::process_msg+0x10f
00000055`3cafef60  CrashUi!wl::_wli::base_window::_window_proc+0x5e
...

FAULTING_SOURCE_CODE:
    41: void Crash_Window::on_access_violation_click()
    42: {
    43:     // Deterministic AV: write through null pointer.
    44:     volatile int* p = nullptr;
>   45:     *p = 42;
    46: }

Followup:     MachineOwner
"""

# ---------------------------------------------------------------------------
# Thinking-support detection
# ---------------------------------------------------------------------------

# Models confirmed to accept the {"thinking": ...} additionalModelRequestFields key.
# Nova 2 Lite (and other non-Pro Nova models) reject that key with ValidationException:
#   "extraneous key [thinking] is not permitted"
_THINKING_SUPPORTED_PATTERNS = (
    "anthropic.claude",   # all Claude 4.x variants via any profile prefix (au./global./…)
    "nova-pro-v1",        # Nova Pro v1 supports thinking (hard-caps output at 10 000 though)
)


def _thinking_supported(model_id: str) -> bool:
    """
    Return True when the model is known to accept the 'thinking' field.

    Defaults to False for unrecognised models so we never send a key that
    causes a ValidationException ("extraneous key [thinking] is not permitted").
    """
    lower = model_id.lower()
    supported = any(pat in lower for pat in _THINKING_SUPPORTED_PATTERNS)
    logger.debug(
        "Thinking support check: model='%s' → %s", model_id, "YES" if supported else "NO"
    )
    return supported


# ---------------------------------------------------------------------------
# Bearer-token credential helpers
# ---------------------------------------------------------------------------

def _load_bearer_token() -> str:
    """
    Load AWS_BEARER_TOKEN_BEDROCK from the environment.

    botocore's ScopedEnvTokenProvider automatically resolves this variable
    for services whose signing name is 'bedrock', but we also load it
    explicitly here so we can validate it early and log clearly.
    """
    logger.debug("Looking for AWS_BEARER_TOKEN_BEDROCK in environment …")
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if not token:
        logger.error(
            "AWS_BEARER_TOKEN_BEDROCK is not set. "
            "Export the variable before running this script."
        )
        raise EnvironmentError("AWS_BEARER_TOKEN_BEDROCK environment variable is missing.")
    logger.info("AWS_BEARER_TOKEN_BEDROCK loaded (length=%d).", len(token))
    return token


def _verify_token_provider(bc_session: botocore.session.Session) -> None:
    """
    Confirm that botocore's ScopedEnvTokenProvider can resolve the token for
    the 'bedrock' signing name (reads AWS_BEARER_TOKEN_BEDROCK automatically).
    """
    provider = ScopedEnvTokenProvider(bc_session)
    token = provider.load_token(signing_name="bedrock")
    if token is not None:
        logger.debug(
            "ScopedEnvTokenProvider confirmed token for signing_name='bedrock' "
            "(expiration=%s).",
            token.expiration,
        )
    else:
        logger.warning(
            "ScopedEnvTokenProvider returned None for signing_name='bedrock'. "
            "Bearer token will be injected via the before-send hook instead."
        )


def _register_bearer_auth_hook(client, raw_token: str) -> None:
    """
    Register a boto3 event hook that injects:
        Authorization: Bearer <token>
    into every outgoing Bedrock request, replacing SigV4 auth.

    'before-send' fires after SigV4 signing so our header wins.
    """

    def _inject_auth_header(request, **kwargs):
        logger.debug(
            "Event hook: injecting Authorization Bearer header for %s %s",
            request.method,
            request.url,
        )
        request.headers["Authorization"] = f"Bearer {raw_token}"

    client.meta.events.register("before-send.bedrock-runtime.*", _inject_auth_header)
    logger.info("Bearer-token Authorization hook registered on bedrock-runtime client.")


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def build_client(raw_token: str):
    """
    Create a boto3 bedrock-runtime client wired for bearer-token auth.
    """
    logger.debug("Creating boto3 Session (region=%s) …", REGION)
    bc_session = botocore.session.Session()
    _verify_token_provider(bc_session)

    session = boto3.Session(botocore_session=bc_session, region_name=REGION)

    logger.debug("Instantiating bedrock-runtime client …")
    client = session.client(
        service_name="bedrock-runtime",
        region_name=REGION,
        config=botocore.config.Config(
            retries={"max_attempts": 1, "mode": "standard"},  # type: ignore[arg-type]
            connect_timeout=10,
            read_timeout=300,   # generous; reasoning can be slow
        ),
    )
    logger.info("bedrock-runtime client created (region=%s, model=%s).", REGION, MODEL_ID)

    _register_bearer_auth_hook(client, raw_token)
    return client


# ---------------------------------------------------------------------------
# Converse request builder
# ---------------------------------------------------------------------------

def build_request(user_text: str) -> dict:
    """
    Construct the Converse API request dict.
    Extended thinking is included only when the model supports it AND
    BEDROCK_THINKING_BUDGET > 0.
    """
    thinking_enabled = (
        THINKING_BUDGET_TOKENS >= _THINKING_BUDGET_MIN
        and _thinking_supported(MODEL_ID)
    )

    inference_config: dict = {"maxTokens": MAX_TOKENS}
    if thinking_enabled:
        # Claude requires temperature == 1 when the thinking block is present
        inference_config["temperature"] = 1
        logger.debug(
            "Extended thinking enabled (budget_tokens=%d); temperature forced to 1.",
            THINKING_BUDGET_TOKENS,
        )
    else:
        if THINKING_BUDGET_TOKENS > 0 and THINKING_BUDGET_TOKENS < _THINKING_BUDGET_MIN:
            logger.warning(
                "BEDROCK_THINKING_BUDGET=%d is below the model minimum of %d; "
                "thinking disabled. Set to 0 to suppress this warning.",
                THINKING_BUDGET_TOKENS,
                _THINKING_BUDGET_MIN,
            )
        else:
            logger.debug(
                "Extended thinking disabled for model '%s' "
                "(not supported by this model, or BEDROCK_THINKING_BUDGET=0).",
                MODEL_ID,
            )

    request: dict = {
        "modelId": MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [{"text": user_text}],
            }
        ],
        "inferenceConfig": inference_config,
    }

    if thinking_enabled:
        request["additionalModelRequestFields"] = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": THINKING_BUDGET_TOKENS,
            }
        }

    logger.debug(
        "Built Converse request: modelId=%s, maxTokens=%d, thinking=%s%s.",
        MODEL_ID,
        MAX_TOKENS,
        "enabled" if thinking_enabled else "disabled",
        f" (budget={THINKING_BUDGET_TOKENS})" if thinking_enabled else "",
    )
    logger.debug("Full request payload:\n%s", json.dumps(request, indent=2, default=str))
    return request


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def parse_response(response: dict) -> tuple[str, str]:
    """
    Extract the thinking trace and the final answer from the Converse response.
    Returns (thinking_text, answer_text).
    """
    logger.debug(
        "HTTP status: %d, requestId: %s",
        response["ResponseMetadata"]["HTTPStatusCode"],
        response["ResponseMetadata"]["RequestId"],
    )
    usage = response.get("usage", {})
    logger.debug(
        "Usage – input tokens: %s, output tokens: %s",
        usage.get("inputTokens"),
        usage.get("outputTokens"),
    )
    logger.debug("Stop reason: %s", response.get("stopReason"))

    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    logger.info("Response contains %d content block(s).", len(content_blocks))

    thinking_parts: list[str] = []
    answer_parts: list[str] = []

    for i, block in enumerate(content_blocks):
        if "reasoningContent" in block:
            # Claude 4.x via Bedrock Converse API returns extended thinking as:
            #   {"reasoningContent": {"reasoningText": {"text": "...", "signature": "..."}}}
            reasoning = block["reasoningContent"]
            text = reasoning.get("reasoningText", {}).get("text", "")
            thinking_parts.append(text)
            logger.debug("  Block[%d] reasoningContent (%d chars).", i, len(text))
        elif "thinking" in block:
            # Fallback: older / direct-invoke format {"thinking": "...", "type": "thinking"}
            thinking_parts.append(block["thinking"])
            logger.debug("  Block[%d] thinking (%d chars).", i, len(block["thinking"]))
        elif "text" in block:
            answer_parts.append(block["text"])
            logger.debug("  Block[%d] text (%d chars).", i, len(block["text"]))
        else:
            logger.warning("  Block[%d] unknown keys: %s", i, list(block.keys()))

    thinking_text = "\n\n".join(thinking_parts)
    answer_text = "\n\n".join(answer_parts)
    logger.info(
        "Parsed response: thinking=%d chars, answer=%d chars.",
        len(thinking_text),
        len(answer_text),
    )
    return thinking_text, answer_text


# ---------------------------------------------------------------------------
# Error handling helpers
# ---------------------------------------------------------------------------

def _log_client_error(exc: botocore.exceptions.ClientError) -> None:
    err = exc.response.get("Error", {})
    logger.error(
        "ClientError: code=%s, message=%s, requestId=%s",
        err.get("Code", "unknown"),
        err.get("Message", "unknown"),
        exc.response.get("ResponseMetadata", {}).get("RequestId", "n/a"),
    )
    logger.debug("Full error response:\n%s", json.dumps(exc.response, indent=2, default=str))


_CLIENT_ERROR_HINTS: dict[str, str] = {
    "ValidationException": (
        "Request payload is invalid – common causes:\n"
        "  • Model does not support the 'thinking' key (e.g. Nova 2 Lite).\n"
        "    The script auto-detects this; if you hit it anyway, set BEDROCK_THINKING_BUDGET=0.\n"
        "  • Direct model IDs (without 'au.'/'global.' prefix) require provisioned throughput.\n"
        "  • Nova Pro hard-caps output at 10 000 tokens.\n"
        "  • Recommended: BEDROCK_MODEL_ID=au.anthropic.claude-sonnet-4-6"
    ),
    "AccessDeniedException": "Access denied – verify your bearer token and IAM permissions.",
    "ResourceNotFoundException": f"Model/profile '{MODEL_ID}' not found in region '{REGION}'.",
    "ThrottlingException": "Request throttled – reduce request rate or request a quota increase.",
    "ServiceUnavailableException": "Bedrock service is temporarily unavailable – retry later.",
    "ModelTimeoutException": "Model timed out generating a response.",
    "ModelErrorException": "The model returned an internal error.",
    "ModelNotReadyException": "The model is not ready – it may still be warming up.",
}


# ---------------------------------------------------------------------------
# Main invocation
# ---------------------------------------------------------------------------

def invoke(user_text: str) -> None:
    logger.info(
        "=== Bedrock invocation started (model=%s, region=%s, "
        "maxTokens=%d, thinkingBudget=%d) ===",
        MODEL_ID, REGION, MAX_TOKENS, THINKING_BUDGET_TOKENS,
    )
    start = time.perf_counter()

    # 1. Load and validate bearer token
    try:
        raw_token = _load_bearer_token()
    except EnvironmentError as exc:
        logger.critical("Aborting: %s", exc)
        sys.exit(1)

    # 2. Build client
    try:
        client = build_client(raw_token)
    except Exception as exc:
        logger.critical("Failed to build Bedrock client: %s", exc, exc_info=True)
        sys.exit(1)

    # 3. Build request payload
    request = build_request(user_text)

    # 4. Call the Converse API with exhaustive error handling
    logger.info("Sending Converse request to %s …", MODEL_ID)
    try:
        response = client.converse(**request)

    except botocore.exceptions.ClientError as exc:
        _log_client_error(exc)
        code = exc.response.get("Error", {}).get("Code", "")
        hint = _CLIENT_ERROR_HINTS.get(code)
        if hint:
            logger.error(hint)
        else:
            logger.error("Unhandled ClientError code '%s'.", code)
        sys.exit(1)

    except botocore.exceptions.NoCredentialsError:
        logger.critical(
            "No AWS credentials found. Ensure AWS_BEARER_TOKEN_BEDROCK is set "
            "or configure ~/.aws/credentials."
        )
        sys.exit(1)

    except botocore.exceptions.PartialCredentialsError as exc:
        logger.critical("Partial credentials: %s", exc)
        sys.exit(1)

    except botocore.exceptions.NoRegionError:
        logger.critical(
            "No region configured. Set AWS_DEFAULT_REGION or pass region_name."
        )
        sys.exit(1)

    except botocore.exceptions.EndpointResolutionError as exc:
        logger.critical("Endpoint resolution failed: %s", exc)
        sys.exit(1)

    except botocore.exceptions.ConnectTimeoutError as exc:
        logger.error("Connection timed out reaching Bedrock endpoint: %s", exc)
        sys.exit(1)

    except botocore.exceptions.ReadTimeoutError as exc:
        logger.error(
            "Read timed out waiting for model response "
            "(thinkingBudget=%d – consider lowering BEDROCK_THINKING_BUDGET): %s",
            THINKING_BUDGET_TOKENS,
            exc,
        )
        sys.exit(1)

    except botocore.exceptions.BotoCoreError as exc:
        logger.critical("Unexpected BotoCore error: %s", exc, exc_info=True)
        sys.exit(1)

    except Exception as exc:
        logger.critical("Unexpected error: %s", exc, exc_info=True)
        sys.exit(1)

    elapsed = time.perf_counter() - start
    logger.info("Converse call completed in %.2f s.", elapsed)

    # 5. Parse and display
    try:
        thinking_text, answer_text = parse_response(response)
    except (KeyError, TypeError) as exc:
        logger.error("Failed to parse response structure: %s", exc, exc_info=True)
        logger.debug("Raw response:\n%s", json.dumps(response, indent=2, default=str))
        sys.exit(1)

    print("\n" + "=" * 72)
    print("REASONING / THINKING PROCESS")
    print("=" * 72)
    print(thinking_text or "(no thinking blocks returned)")

    print("\n" + "=" * 72)
    print("ANSWER")
    print("=" * 72)
    print(answer_text or "(no answer text returned)")

    logger.info("=== Invocation finished (total %.2f s) ===", elapsed)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    prompt = (
        "Read the output of WinDbg and tell everything you can get from the "
        f"crash-dump analysis:\n\n{CONTENT}"
    )
    invoke(prompt)

