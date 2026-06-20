"""OpenAI (GPT) AI backend.

Uses the ``json_schema`` response format for structured output. OpenAI applies
prompt caching automatically for sufficiently long, stable prefixes, so no
explicit cache-control directive is required (unlike Anthropic).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Optional

import openai
from pydantic import BaseModel

from aegis_swr.backends.ai._base import _BaseAIBackend
from aegis_swr.config.settings import AISettings


def _to_openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Adapt a Pydantic JSON schema to OpenAI strict structured-output rules.

    OpenAI strict mode requires every object to set ``additionalProperties: false``
    and list all of its properties as ``required``; it also rejects ``default``.
    """
    schema = model.model_json_schema()

    def _walk(node: Any):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for value in node:
                _walk(value)

    _walk(schema)
    return schema


# Reasoning models gpt-5 family reject `max_tokens` and any
# non-default `temperature`; they require `max_completion_tokens`. Their
# completion budget is also shared with internal reasoning tokens, so a small
# cap can starve the visible answer - give structured output ample headroom.
_REASONING_PREFIXES = ("gpt-5",)
_REASONING_MIN_COMPLETION_TOKENS = 16000


# A multi-agent investigation issues many sequential calls; one transient
# timeout must not abort the whole run. Reasoning models can also have high
# tail latency, so allow a generous per-request timeout and SDK-level retries
# (exponential backoff on timeouts / 429 / 5xx).
_REQUEST_TIMEOUT_SECONDS = 300.0
_MAX_RETRIES = 4


class OpenAIBackend(_BaseAIBackend):
    def __init__(self, settings: AISettings):
        super().__init__(settings)
        self._client: Any = openai.AsyncOpenAI(
            timeout=_REQUEST_TIMEOUT_SECONDS,
            max_retries=_MAX_RETRIES,
        )

    def _is_reasoning_model(self) -> bool:
        return self.model_name.startswith(_REASONING_PREFIXES)

    @property
    def has_reasoning(self) -> bool:
        """Always ``False``: OpenAI reasoning models (gpt-5 family) reason
        internally but the Chat Completions API used here does not return the
        reasoning trace alongside the answer - only the final message."""
        return False

    def _completion_kwargs(self) -> dict[str, Any]:
        """Token/temperature kwargs that match the model family's API contract"""
        if self._is_reasoning_model():
            # Default temperature only; reasoning needs room beyond the answer.
            return {
                "max_completion_tokens": max(
                    self._settings.max_tokens, _REASONING_MIN_COMPLETION_TOKENS
                )
            }
        return {
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> tuple[str | dict[str, Any], dict[str, int]]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": full_messages,
            **self._completion_kwargs(),
        }
        if output_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_schema.__name__,
                    "schema": _to_openai_strict_schema(output_schema),
                    "strict": True,
                },
            }

        response = await self._client.chat.completions.create(**kwargs)
        usage = {
            "input_tokens": int(response.usage.prompt_tokens),
            "output_tokens": int(response.usage.completion_tokens),
        }
        content: str = response.choices[0].message.content or ""
        return content, usage

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        stream = await self._client.chat.completions.create(
            model=self.model_name,
            messages=full_messages,
            stream=True,
            stream_options={"include_usage": True},
            **self._completion_kwargs(),
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
