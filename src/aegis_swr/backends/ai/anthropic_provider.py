"""Anthropic (Claude) AI backend.

Uses Messages API tool-use for structured output and always attaches
``cache_control: {"type": "ephemeral"}`` to the system prompt block so the
stable persona/schema instructions are billed at the cached rate.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

import anthropic
from pydantic import BaseModel

from aegis_swr.backends.ai._base import _BaseAIBackend
from aegis_swr.core.exceptions import AIOutputValidationError

if TYPE_CHECKING:
    from aegis_swr.config.settings import AISettings

_STRUCTURED_TOOL_NAME = "structured_output"


class AnthropicBackend(_BaseAIBackend):
    def __init__(self, settings: AISettings) -> None:
        super().__init__(settings)
        # Typed as Any so the rest of the module is not coupled to the SDK's
        # internal TypedDict parameter types.
        self._client: Any = anthropic.AsyncAnthropic()

    def _system_blocks(self, system_prompt: str) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel] | None,
    ) -> tuple[str | dict[str, Any], dict[str, int]]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self._settings.max_tokens,
            "temperature": self._settings.temperature,
            "system": self._system_blocks(system_prompt),
            "messages": messages,
        }
        if output_schema is not None:
            kwargs["tools"] = [
                {
                    "name": _STRUCTURED_TOOL_NAME,
                    "description": "Return the analysis as a structured object.",
                    "input_schema": output_schema.model_json_schema(),
                }
            ]
            kwargs["tool_choice"] = {"type": "tool", "name": _STRUCTURED_TOOL_NAME}

        response = await self._client.messages.create(**kwargs)
        usage = {
            "input_tokens": int(response.usage.input_tokens),
            "output_tokens": int(response.usage.output_tokens),
        }

        if output_schema is not None:
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    return dict(block.input), usage
            raise AIOutputValidationError(
                f"{self.model_name} returned no tool_use block for structured output"
            )

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return text, usage

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        async with self._client.messages.stream(
            model=self.model_name,
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
            system=self._system_blocks(system_prompt),
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
