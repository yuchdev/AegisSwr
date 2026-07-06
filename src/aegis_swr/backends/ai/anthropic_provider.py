"""Anthropic (Claude) AI backend.

Uses Messages API tool-use for structured output and always attaches
``cache_control: {"type": "ephemeral"}`` to the system prompt block so the
stable persona/schema instructions are billed at the cached rate.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Optional, Union

import anthropic
from pydantic import BaseModel

from aegis_swr.backends.ai.base import _BaseAIBackend
from aegis_swr.config.settings import AnthropicSettings
from aegis_swr.core.exceptions import AIOutputValidationError

_STRUCTURED_TOOL_NAME = "structured_output"

# Claude families that support extended thinking and return the trace as
# ``thinking`` blocks: Claude 3.7 and the entire Claude 4 line. Anything else
# (legacy Claude 3.0/3.5) answers without an exposed reasoning trace.
_REASONING_MODEL_MARKERS = (
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-4",
    "claude-3-7",
)

# Claude rejects an extended-thinking budget below this floor, so a sub-minimum
# budget is treated as "thinking disabled".
_THINKING_BUDGET_MIN = 1_024


class AnthropicBackend(_BaseAIBackend[AnthropicSettings]):
    def __init__(self, settings: AnthropicSettings):
        super().__init__(settings)
        # Typed as Any so the rest of the module is not coupled to the SDK's
        # internal TypedDict parameter types.
        self._client: Any = anthropic.AsyncAnthropic(
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    @property
    def has_reasoning(self) -> bool:
        """``True`` for extended-thinking models: Claude, OpenAI, Nova Pro"""
        return any(marker in self.model_name for marker in _REASONING_MODEL_MARKERS)

    def _system_blocks(self, system_prompt: str) -> list[dict[str, Any]]:
        block: dict[str, Any] = {"type": "text", "text": system_prompt}
        if self._settings.prompt_caching:
            block["cache_control"] = {"type": "ephemeral"}
        return [block]

    def _thinking_enabled(self, output_schema: Optional[type[BaseModel]]) -> bool:
        """Extended thinking applies only to free-form output on a capable model.

        Claude rejects extended thinking alongside a forced tool choice, so any
        structured (schema) request disables it regardless of the budget.
        """
        if output_schema is not None:
            return False
        return (
            self._settings.thinking_budget_tokens >= _THINKING_BUDGET_MIN
            and self.has_reasoning
        )

    def _create_request(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        thinking: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self._settings.max_tokens,
            "temperature": 1.0 if thinking else self._settings.temperature,
            "system": self._system_blocks(system_prompt),
            "messages": messages,
        }
        if thinking:
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": self._settings.thinking_budget_tokens,
            }
        return kwargs

    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: Optional[type[BaseModel]],
    ) -> tuple[Union[str, dict[Any, Any]], dict[str, int]]:
        """
        Invoke the model and return the raw response text or a parsed object.
        Note that Claude requires temperature == 1 whenever extended thinking is on.
        :param system_prompt: The system prompt to guide the model's behavior.
        :param messages: A list of messages to provide context for the model.
        :param output_schema: An optional Pydantic model for structured output.
        :return: A tuple containing the model's response and token usage.
        """
        thinking = self._thinking_enabled(output_schema)
        kwargs = self._create_request(system_prompt, messages, thinking)
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
        thinking = self._thinking_enabled(output_schema=None)
        kwargs = self._create_request(system_prompt, messages, thinking)
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
