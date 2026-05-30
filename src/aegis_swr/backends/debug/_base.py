"""Shared scaffolding for debug backends.

Owns the provider-neutral parts of :class:`DebugBackend`: source validation,
the RAII subprocess invocation with timeout, and the symbol-resolution score.
Each concrete worker implements ``_build_command_sequence`` (its debugger argv)
and ``_parse`` (its debugger-output parser).
"""
from __future__ import annotations

import subprocess
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from aegis_swr.backends.base import DebugBackend
from aegis_swr.core.data_adapter import apply_noise_filter
from aegis_swr.core.exceptions import DebugExtractionError, PlatformNotSupportedError
from aegis_swr.core.schemas import DebugExtractionResult, StackFrame

if TYPE_CHECKING:
    from aegis_swr.config.settings import DebugSettings
    from aegis_swr.core.schemas import IncidentSource


class _BaseDebugBackend(DebugBackend):
    def __init__(self, settings: DebugSettings) -> None:
        self._settings = settings

    # -- template method ---------------------------------------------------

    def extract(
        self,
        source: IncidentSource,
        symbol_path: str | None,
    ) -> DebugExtractionResult:
        self._validate(source)
        command = self._build_command_sequence(source, symbol_path)
        raw = self._run(command)
        return self._parse(raw, source)

    # -- shared helpers ----------------------------------------------------

    def _validate(self, source: IncidentSource) -> None:
        if not source.dump_path:
            raise DebugExtractionError("IncidentSource has no dump_path")
        if not Path(source.dump_path).exists():
            raise DebugExtractionError(f"Dump file not found: {source.dump_path}")
        fmt = source.dump_format
        if fmt is not None and fmt not in self.SUPPORTED_FORMATS:
            raise DebugExtractionError(
                f"{type(self).__name__} does not support {fmt.value}"
            )

    def _run(self, command: list[str]) -> str:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self._settings.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exc:
            raise PlatformNotSupportedError(
                f"Debugger binary not found: {command[0]!r}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise DebugExtractionError(
                f"Debugger timed out after {self._settings.timeout_seconds}s"
            ) from exc
        combined = (result.stdout or "") + (result.stderr or "")
        if not combined.strip():
            logger.warning(f"{command[0]} produced no output")
        return combined

    @staticmethod
    def _symbol_score(frames: list[StackFrame]) -> float:
        if not frames:
            return 0.0
        resolved = sum(1 for f in frames if f.function)
        return resolved / len(frames)

    @staticmethod
    def _excerpt(raw: str) -> str:
        return apply_noise_filter(raw)

    # -- provider hooks ----------------------------------------------------

    @abstractmethod
    def _parse(self, raw: str, source: IncidentSource) -> DebugExtractionResult:
        """Parse raw debugger output into a structured result."""


def normalize_address(token: str) -> str:
    """Normalise a debugger address token (strip backticks, ensure 0x prefix)."""
    cleaned = token.replace("`", "").strip()
    if not cleaned:
        return "0x0"
    if not cleaned.lower().startswith("0x"):
        cleaned = "0x" + cleaned
    return cleaned
