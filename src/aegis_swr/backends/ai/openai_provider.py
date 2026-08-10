"""OpenAI (GPT) AI backend.

Uses the ``json_schema`` response format for structured output. OpenAI applies
prompt caching automatically for sufficiently long, stable prefixes, so no
explicit cache-control directive is required (unlike Anthropic).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Optional, Union

import openai
from pydantic import BaseModel

from aegis_swr.backends.ai.base import _BaseAIBackend
from aegis_swr.config.settings import OpenAISettings


def _to_openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Adapt a Pydantic JSON schema to OpenAI strict structured-output rules.

    OpenAI strict mode requires every object to set ``additionalProperties: false``
    and list all of its properties as ``required``; it also rejects ``default``.
    """
    schema = model.model_json_schema()

    def _walk(node: Any):
        """Recursively rewrite *node* in place for OpenAI strict-schema rules."""
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
# cap can starve the visible answer - configure ample headroom via
# ``OpenAISettings.max_completion_tokens``.
_REASONING_PREFIXES = ("gpt-5",)


class OpenAIBackend(_BaseAIBackend[OpenAISettings]):
    """AI backend that generates RCA content via the OpenAI Chat Completions API."""

    def __init__(self, settings: OpenAISettings):
        """Build the async OpenAI client from *settings* (timeout, retries)."""
        super().__init__(settings)
        # A multi-agent investigation issues many sequential calls; one
        # transient timeout must not abort the whole run. Reasoning models can
        # have high tail latency, so timeout and retries are configurable.
        self._client: Any = openai.AsyncOpenAI(
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    def _is_reasoning_model(self) -> bool:
        """Return True when the configured model is a gpt-5-family reasoning model."""
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
            kwargs: dict[str, Any] = {"max_completion_tokens": self._settings.max_completion_tokens}
            if self._settings.reasoning_effort is not None:
                kwargs["reasoning_effort"] = self._settings.reasoning_effort
            return kwargs
        return {
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> tuple[Union[str, dict[str, Any]], dict[str, int]]:
        """Issue one Chat Completions round-trip, returning the text and token usage."""
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
        """Stream free-form response text token by token from Chat Completions."""
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
