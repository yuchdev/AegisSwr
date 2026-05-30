"""Shared scaffolding for AI backends.

Holds the provider-neutral parts of :class:`AIAPIBackend`: structured-output
validation, the one-shot correction retry, and per-call token accounting. Each
concrete provider implements only :meth:`_invoke` (a single API round-trip) and
:meth:`stream`.
"""
from __future__ import annotations

import json
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel, ValidationError

from aegis_swr.backends.base import AIAPIBackend
from aegis_swr.core.exceptions import AIOutputValidationError

if TYPE_CHECKING:
    from aegis_swr.config.settings import AISettings


class _BaseAIBackend(AIAPIBackend):
    """Common generate()/token logic; providers implement _invoke() + stream()."""

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings
        self.model_name = settings.resolved_model
        self._last_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}

    # -- token accounting --------------------------------------------------

    @property
    def last_usage(self) -> dict[str, int]:
        """Token usage of the most recent :meth:`generate` call (incl. retries)."""
        return dict(self._last_usage)

    def _reset_usage(self) -> None:
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}

    def _accumulate(self, usage: dict[str, int]) -> None:
        self._last_usage["input_tokens"] += usage.get("input_tokens", 0)
        self._last_usage["output_tokens"] += usage.get("output_tokens", 0)

    # -- public API --------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel] | None = None,
    ) -> BaseModel | str:
        self._reset_usage()

        if output_schema is None:
            raw, usage = await self._invoke(system_prompt, list(messages), None)
            self._accumulate(usage)
            return raw if isinstance(raw, str) else json.dumps(raw)

        working = list(messages)
        last_error: str | None = None
        for attempt in range(2):
            raw, usage = await self._invoke(system_prompt, working, output_schema)
            self._accumulate(usage)
            try:
                data = raw if isinstance(raw, dict) else json.loads(raw)
                return output_schema.model_validate(data)
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                logger.warning(
                    f"{self.model_name} structured output invalid "
                    f"(attempt {attempt + 1}/2): {last_error}"
                )
                working = working + self._correction_turn(raw, last_error, output_schema)

        raise AIOutputValidationError(
            f"{self.model_name} failed to satisfy {output_schema.__name__} "
            f"after one retry. Last error: {last_error}"
        )

    @staticmethod
    def _correction_turn(
        raw: str | dict[str, Any],
        errors: str,
        output_schema: type[BaseModel],
    ) -> list[dict[str, Any]]:
        previous = raw if isinstance(raw, str) else json.dumps(raw)
        return [
            {"role": "assistant", "content": previous},
            {
                "role": "user",
                "content": (
                    f"Your previous response did not match the required "
                    f"{output_schema.__name__} schema. Validation errors:\n{errors}\n"
                    "Reply again with ONLY a valid JSON object matching the schema."
                ),
            },
        ]

    # -- provider hooks ----------------------------------------------------

    @abstractmethod
    async def _invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel] | None,
    ) -> tuple[str | dict[str, Any], dict[str, int]]:
        """One API round-trip.

        Returns ``(payload, usage)`` where payload is a parsed dict when
        ``output_schema`` is given, otherwise the raw response text.
        """
