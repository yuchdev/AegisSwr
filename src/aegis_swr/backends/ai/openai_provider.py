"""OpenAI (GPT) AI backend.

Uses the ``json_schema`` response format for structured output. OpenAI applies
prompt caching automatically for sufficiently long, stable prefixes, so no
explicit cache-control directive is required (unlike Anthropic).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import openai
from pydantic import BaseModel

from aegis_swr.backends.ai._base import _BaseAIBackend

if TYPE_CHECKING:
    from aegis_swr.config.settings import AISettings


def _to_openai_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Adapt a Pydantic JSON schema to OpenAI strict structured-output rules.

    OpenAI strict mode requires every object to set ``additionalProperties: false``
    and list all of its properties as ``required``; it also rejects ``default``.
    """
    schema = model.model_json_schema()

    def _walk(node: Any) -> None:
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


class OpenAIBackend(_BaseAIBackend):
    def __init__(self, settings: AISettings) -> None:
        super().__init__(settings)
        self._client: Any = openai.AsyncOpenAI()

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel] | None,
    ) -> tuple[str | dict[str, Any], dict[str, int]]:
        full_messages = [{"role": "system", "content": system_prompt}, *messages]
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
            "messages": full_messages,
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
            temperature=self._settings.temperature,
            max_tokens=self._settings.max_tokens,
            messages=full_messages,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
