"""Amazon Bedrock AI backend.

Talks to Bedrock through the **Converse API**, which gives a single
provider-neutral request/response shape across every hosted model family
(Anthropic Claude, Amazon Nova, …). Structured output is requested with the
Converse ``toolConfig`` (forced tool use), mirroring the Anthropic backend's
tool-use strategy; free-form generation streams via ``converse_stream``.

Authentication is dual-mode:

* If ``AWS_BEARER_TOKEN_BEDROCK`` is set, an Authorization Bearer header is
  injected on every request (Bedrock API-key auth).
* Otherwise the standard boto3 credential chain (env / shared config / IAM
  role) is used via SigV4.

boto3 is synchronous, so every network round-trip is dispatched to a worker
thread with :func:`asyncio.to_thread` to keep the event loop free.

Security: the bearer token is read from the environment, never logged, and
never stored on the instance beyond what botocore needs to sign a request.
This module logs only non-sensitive metadata. The ``botocore``/``boto3``/
``urllib3`` stdlib loggers (which would emit full request bodies and wire
headers, including the bearer token, at DEBUG) are stdlib loggers that bypass
loguru's ``SensitiveFilter``; they are therefore clamped to WARNING in
:mod:`aegis_swr.cli.aegis_logging` (``NOISY_LIBRARY_LOGGERS``) so that request
bodies and headers are never emitted regardless of the operator log level.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Iterator
from typing import Any, Optional

import boto3
import botocore.config
import botocore.exceptions
from loguru import logger
from pydantic import BaseModel

from aegis_swr.backends.ai.base import _BaseAIBackend
from aegis_swr.config.settings import BedrockSettings
from aegis_swr.core.exceptions import AIBackendError, AIOutputValidationError

_STRUCTURED_TOOL_NAME = "structured_output"
_BEARER_TOKEN_ENV = "AWS_BEARER_TOKEN_BEDROCK"

# Claude enforces a minimum extended-thinking budget; anything smaller is
# rejected, so we treat sub-minimum budgets as "thinking disabled".
_THINKING_BUDGET_MIN = 1_024

# Model families known to accept the ``thinking`` additionalModelRequestFields
# key. Unrecognised models default to "no thinking" so we never send a key that
# triggers a ValidationException ("extraneous key [thinking] is not permitted").
_THINKING_SUPPORTED_PATTERNS = ("anthropic.claude", "nova-pro-v1")

# A sentinel so a thread-fetched ``next()`` can signal stream exhaustion without
# colliding with a legitimate ``None`` event.
_STREAM_DONE = object()


def _thinking_supported(model_id: str) -> bool:
    """Return True when *model_id* is known to accept the ``thinking`` field."""
    lowered = model_id.lower()
    return any(pat in lowered for pat in _THINKING_SUPPORTED_PATTERNS)


class AwsBedrockBackend(_BaseAIBackend[BedrockSettings]):
    """AI backend backed by Amazon Bedrock's Converse API.

    :param settings: The Bedrock provider sub-config; the model identity is
        read from ``settings.resolved_model`` (the configured inference-profile
        ID) and all other knobs (region, budgets, timeouts, auth) directly from
        the typed fields.
    """

    def __init__(self, settings: BedrockSettings):
        """Build the bedrock-runtime client wired for the configured auth mode."""
        super().__init__(settings)
        # Typed as Any so the module is not coupled to botocore's generated
        # client type stubs.
        self._client: Any = self._build_client()

    # -- client construction ----------------------------------------------

    def _build_client(self) -> Any:
        """Create a bedrock-runtime client wired for the configured auth mode.

        Region precedence: explicit ``settings.region`` wins, falling back to
        ``AWS_DEFAULT_REGION`` only when the setting is blank. ``auth_mode``
        selects bearer-token vs SigV4 auth (``"auto"`` prefers a bearer token
        when one is present, otherwise SigV4).
        """
        region = self._settings.region or os.environ.get("AWS_DEFAULT_REGION")
        config = botocore.config.Config(
            retries={"max_attempts": self._settings.max_attempts, "mode": "standard"},
            connect_timeout=self._settings.connect_timeout_seconds,
            read_timeout=self._settings.read_timeout_seconds,
        )
        client = boto3.Session(region_name=region).client(
            service_name="bedrock-runtime",
            region_name=region,
            config=config,
        )

        token = None
        if self._settings.auth_mode in ("auto", "bearer"):
            token = os.environ.get(_BEARER_TOKEN_ENV)
        if token:
            self._register_bearer_auth_hook(client, token)
            logger.debug(
                "Bedrock client created (region={}, model={}, auth=bearer-token).",
                region,
                self.model_name,
            )
        else:
            logger.debug(
                "Bedrock client created (region={}, model={}, auth=sigv4-credential-chain). "
                "Set {} to use Bedrock API-key auth instead.",
                region,
                self.model_name,
                _BEARER_TOKEN_ENV,
            )
        return client

    @property
    def has_reasoning(self) -> bool:
        """``True`` when the configured Bedrock model can emit a reasoning
        trace (``reasoningContent``) - i.e. a thinking-capable Claude or Nova
        Pro inference profile. Reflects model capability regardless of the
        currently configured thinking budget."""
        return _thinking_supported(self.model_name)

    @staticmethod
    def _register_bearer_auth_hook(client: Any, raw_token: str) -> None:
        """Inject ``Authorization: Bearer <token>`` on every Bedrock request.

        ``before-send`` fires after SigV4 signing, so this header wins. The
        token is captured in the closure and never logged.
        """

        def _inject_auth_header(request: Any, **_: Any) -> None:
            """Set the bearer ``Authorization`` header on the outgoing request."""
            request.headers["Authorization"] = f"Bearer {raw_token}"

        client.meta.events.register("before-send.bedrock-runtime.*", _inject_auth_header)

    # -- request construction ----------------------------------------------

    @staticmethod
    def _to_converse_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Adapt the provider-neutral message list to the Converse content shape.

        The shared base passes ``{"role": ..., "content": <str>}``; Converse
        expects ``content`` to be a list of typed blocks (``[{"text": ...}]``).
        """
        return [{"role": m["role"], "content": [{"text": str(m["content"])}]} for m in messages]

    def _thinking_enabled(self, output_schema: Optional[type[BaseModel]]) -> bool:
        """Thinking is only valid for free-form output on a supporting model.

        Claude rejects extended thinking when a tool choice is forced, so any
        structured (schema) request disables it regardless of the budget.
        """
        if output_schema is not None:
            return False
        return self._settings.thinking_budget_tokens >= _THINKING_BUDGET_MIN and _thinking_supported(self.model_name)

    def _build_request(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> dict[str, Any]:
        """Assemble the Converse request, adding thinking or a forced tool as needed."""
        thinking = self._thinking_enabled(output_schema)

        inference_config: dict[str, Any] = {"maxTokens": self._settings.max_tokens}
        # Claude requires temperature == 1 whenever a thinking block is present.
        inference_config["temperature"] = 1.0 if thinking else self._settings.temperature

        request: dict[str, Any] = {
            "modelId": self.model_name,
            "system": [{"text": system_prompt}],
            "messages": self._to_converse_messages(messages),
            "inferenceConfig": inference_config,
        }

        if thinking:
            request["additionalModelRequestFields"] = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": self._settings.thinking_budget_tokens,
                }
            }

        if output_schema is not None:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": _STRUCTURED_TOOL_NAME,
                            "description": "Return the analysis as a structured object.",
                            "inputSchema": {"json": output_schema.model_json_schema()},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": _STRUCTURED_TOOL_NAME}},
            }
        return request

    # -- response parsing --------------------------------------------------

    @staticmethod
    def _usage(response: dict[str, Any]) -> dict[str, int]:
        """Extract input/output token counts from a Converse *response*."""
        usage = response.get("usage", {}) or {}
        return {
            "input_tokens": int(usage.get("inputTokens", 0)),
            "output_tokens": int(usage.get("outputTokens", 0)),
        }

    def _parse(
        self,
        response: dict[str, Any],
        output_schema: Optional[type[BaseModel]],
    ) -> str | dict[str, Any]:
        """Extract the tool payload or concatenated text from a Converse response.

        Reasoning-content blocks are ignored so internal chain-of-thought never
        leaks into the returned text.
        """
        content_blocks = response.get("output", {}).get("message", {}).get("content", []) or []

        if output_schema is not None:
            for block in content_blocks:
                if "toolUse" in block:
                    return dict(block["toolUse"].get("input", {}))
            raise AIOutputValidationError(f"{self.model_name} returned no toolUse block for structured output")

        # Free-form text: concatenate text blocks, ignoring reasoning blocks.
        return "".join(block["text"] for block in content_blocks if "text" in block)

    # -- provider hooks ----------------------------------------------------

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> tuple[str | dict[str, Any], dict[str, int]]:
        """Issue one Converse round-trip off the event loop, returning payload+usage.

        :raises AIBackendError: on any boto client or transport error, surfacing only
            the error code (never the message, which may contain secrets).
        """
        request = self._build_request(system_prompt, messages, output_schema)
        try:
            response = await asyncio.to_thread(self._client.converse, **request)
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.error("Bedrock converse ClientError: code={}", code)
            raise AIBackendError(f"Bedrock converse failed for {self.model_name} ({code})") from exc
        except botocore.exceptions.BotoCoreError as exc:
            logger.error("Bedrock converse transport error: {}", type(exc).__name__)
            raise AIBackendError(
                f"Bedrock converse transport error for {self.model_name}: " f"{type(exc).__name__}"
            ) from exc

        return self._parse(response, output_schema), self._usage(response)

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """Stream free-form response text token by token from Converse.

        :raises AIBackendError: on any boto client or transport error (code only).
        """
        request = self._build_request(system_prompt, messages, output_schema=None)
        try:
            response = await asyncio.to_thread(self._client.converse_stream, **request)
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            logger.error("Bedrock converse_stream ClientError: code={}", code)
            raise AIBackendError(f"Bedrock converse_stream failed for {self.model_name} ({code})") from exc
        except botocore.exceptions.BotoCoreError as exc:
            logger.error("Bedrock converse_stream transport error: {}", type(exc).__name__)
            raise AIBackendError(
                f"Bedrock converse_stream transport error for {self.model_name}: " f"{type(exc).__name__}"
            ) from exc

        # The EventStream is a synchronous, network-backed iterator; pull each
        # event on a worker thread so iteration never blocks the event loop.
        iterator: Iterator[Any] = iter(response["stream"])
        while True:
            try:
                event: Any = await asyncio.to_thread(next, iterator, _STREAM_DONE)
            except botocore.exceptions.BotoCoreError as exc:
                logger.error("Bedrock stream interrupted: {}", type(exc).__name__)
                raise AIBackendError(
                    f"Bedrock stream interrupted for {self.model_name}: " f"{type(exc).__name__}"
                ) from exc
            if event is _STREAM_DONE:
                break
            delta = event.get("contentBlockDelta", {}).get("delta", {})
            text = delta.get("text")
            if text:
                yield text
