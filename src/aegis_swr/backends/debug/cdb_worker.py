"""Windows CDB debug backend.

Wraps ``cdb.exe`` (Debugging Tools for Windows). Regexes are ported from the
WinCrashAnalyzer prototype (see docs/prototype-analysis-specs/PROMPT_HEURISTICS.md
§4 and WIN_DEPENDENCIES.md §8).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from aegis_swr.backends.debug._base import _BaseDebugBackend, normalize_address
from aegis_swr.backends.debug._symbol_path import resolve_symbol_path
from aegis_swr.core.fault_codes import map_windows_ntstatus
from aegis_swr.core.schemas import DebugExtractionResult, DumpFormat, StackFrame

if TYPE_CHECKING:
    from aegis_swr.core.schemas import IncidentSource

_DEFAULT_SYMBOL_SERVER = "https://msdl.microsoft.com/download/symbols"

# !analyze -v reports the fault code under several different keys depending on
# the crash. Try them in priority order; the prototype only matched the first,
# which silently yielded 0x0 (→ FaultClass.UNKNOWN) for NULL_POINTER_WRITE dumps
# that use ERROR_CODE / EXCEPTION_CODE_STR instead.
_EXC_CODE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"EXCEPTION_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"ERROR_CODE:\s+\((?:NTSTATUS|HRESULT)\)\s+(0x[0-9a-fA-F]+)", re.IGNORECASE),
    re.compile(r"EXCEPTION_CODE_STR:\s+([0-9a-fA-F]{8})\b", re.IGNORECASE),
    re.compile(r"ExceptionCode:\s+([0-9a-fA-F]{8})\b", re.IGNORECASE),
)
_EXC_ADDR_RE = re.compile(r"ExceptionAddress:\s+([0-9a-fA-F`]+)", re.IGNORECASE)


def _extract_exception_code(raw: str) -> str:
    """Return the fault code as ``0x``-prefixed lowercase hex, or ``0x0``."""
    for pattern in _EXC_CODE_RES:
        match = pattern.search(raw)
        if match:
            token = match.group(1).lower()
            return token if token.startswith("0x") else f"0x{token}"
    return "0x0"
_MODULE_RE = re.compile(r"MODULE_NAME:\s+(\S+)")
_TIMESTAMP_RE = re.compile(r"Debug session time:\s+(.*?)\s+\(UTC")
_FRAME_RE = re.compile(
    r"^\s*[0-9a-f]+\s+"          # frame number
    r"[0-9a-f`]+\s+"            # child SP
    r"([0-9a-fx`]+)\s+"        # return address
    r"(\S+)"                   # call site symbol
    r"(?:\s+\[(.+?)\s+@\s+(\d+)\])?",  # optional [file @ line]
    re.IGNORECASE,
)


def _parse_callsite(symbol: str) -> tuple[str | None, str | None]:
    """Split a CDB call-site token into (module, function)."""
    if symbol.startswith("0x") or symbol.startswith("<"):
        return None, None
    if "!" in symbol:
        module, func_part = symbol.split("!", 1)
        function = func_part.split("+", 1)[0]
        return module, function
    if "+" in symbol:
        return symbol.split("+", 1)[0], None  # module known, function unresolved
    return symbol, None


def parse_cdb_frames(raw: str) -> list[StackFrame]:
    frames: list[StackFrame] = []
    in_stack = False
    number = 0
    for line in raw.splitlines():
        if "STACK_TEXT:" in line:
            in_stack = True
            continue
        if not in_stack:
            continue
        if not line.strip():
            break
        match = _FRAME_RE.match(line)
        if not match:
            continue
        ret_addr, symbol, source_file, source_line = match.groups()
        module, function = _parse_callsite(symbol)
        frames.append(
            StackFrame(
                frame_number=number,
                module=module,
                function=function,
                source_file=source_file,
                source_line=int(source_line) if source_line else None,
                instruction_address=normalize_address(ret_addr),
            )
        )
        number += 1
    return frames


class CdbBackend(_BaseDebugBackend):
    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]] = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Windows"]

    def _symbol_path_string(self, symbol_path: str | None) -> str:
        cache = resolve_symbol_path(self._settings.symbol_cache)
        server = self._settings.symbol_server_url or _DEFAULT_SYMBOL_SERVER
        chain = f"srv*{cache}*{server}"
        if symbol_path:
            chain = f"{chain};{symbol_path}"
        return chain

    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: str | None,
    ) -> list[str]:
        return [
            "cdb.exe",
            "-z",
            str(source.dump_path),
            "-y",
            self._symbol_path_string(symbol_path),
            "-c",
            ".reload /f /i; !analyze -v; q",
        ]

    def _parse(self, raw: str, source: IncidentSource) -> DebugExtractionResult:
        exception_code = _extract_exception_code(raw)
        fault_class = map_windows_ntstatus(exception_code)

        frames = parse_cdb_frames(raw)

        addr_match = _EXC_ADDR_RE.search(raw)
        if addr_match:
            exception_address = normalize_address(addr_match.group(1))
        elif frames:
            exception_address = frames[0].instruction_address
        else:
            exception_address = "0x0"

        module_match = _MODULE_RE.search(raw)
        faulting_module = module_match.group(1) if module_match else None
        if faulting_module is None and frames:
            faulting_module = frames[0].module
        faulting_function = frames[0].function if frames else None

        return DebugExtractionResult(
            fault_class=fault_class,
            exception_code_raw=exception_code,
            exception_address=exception_address,
            faulting_module=faulting_module,
            faulting_function=faulting_function,
            stack_frames=frames,
            debug_timestamp=self._parse_timestamp(raw),
            symbol_resolution_score=self._symbol_score(frames),
            raw_text_excerpt=self._excerpt(raw),
        )

    @staticmethod
    def _parse_timestamp(raw: str) -> datetime | None:
        match = _TIMESTAMP_RE.search(raw)
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1).strip(), "%a %b %d %H:%M:%S.%f %Y")
        except ValueError:
            return None
