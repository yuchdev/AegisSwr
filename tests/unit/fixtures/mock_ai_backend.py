"""Reusable mock AI backend for unit and integration tests.

Returns pre-scripted responses without any network access. Shared by the AI
backend tests (Step 3) and the orchestrator tests (Step 5).
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel

from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.core.exceptions import AIOutputValidationError


class MockAIBackend(AIAPIBackend):
    """An ``AIAPIBackend`` driven by a scripted list of responses.

    ``responses`` are consumed in order, one per :meth:`generate` call. Each item
    may be a ``BaseModel`` instance, a ``dict`` (validated against the requested
    schema), or a ``str`` (returned verbatim for unstructured calls).
    """

    def __init__(
        self,
        responses: list[Any] | None = None,
        stream_tokens: list[str] | None = None,
        usage: dict[str, int] | None = None,
    ):
        self.model_name = "mock-model"
        self._responses: list[Any] = list(responses or [])
        self._stream_tokens: list[str] = list(stream_tokens or ["mock ", "response"])
        self.last_usage: dict[str, int] = usage or {"input_tokens": 10, "output_tokens": 5}
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        self.calls.append(
            {"system": system_prompt, "messages": messages, "schema": output_schema}
        )
        response = self._responses.pop(0) if self._responses else None

        if output_schema is not None:
            if isinstance(response, output_schema):
                return response
            if isinstance(response, dict):
                return output_schema.model_validate(response)
            raise AIOutputValidationError(
                f"MockAIBackend has no scripted {output_schema.__name__} response"
            )

        if isinstance(response, str):
            return response
        return "mock text response"

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        for token in self._stream_tokens:
            yield token
