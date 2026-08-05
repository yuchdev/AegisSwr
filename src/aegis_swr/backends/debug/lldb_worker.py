"""macOS LLDB debug backend.

Parses ``lldb --batch`` backtraces (LLDB reads minidumps and Mach-O core files)
and maps Mach exception types to :class:`FaultClass`.
"""

from __future__ import annotations

import re
from typing import ClassVar

from aegis_swr.backends.debug.base import _BaseDebugBackend, normalize_address
from aegis_swr.core.fault_codes import FaultClass, map_macos_exception
from aegis_swr.core.schemas import DebugExtractionResult, DumpFormat, IncidentSource, StackFrame

# Mach exception name -> type code (matches fault_codes._MACOS_EXCEPTION_MAP).
_EXCEPTION_CODES = {
    "EXC_BAD_ACCESS": 1,
    "EXC_BAD_INSTRUCTION": 2,
    "EXC_ARITHMETIC": 3,
    "EXC_EMULATION": 4,
    "EXC_SOFTWARE": 5,
    "EXC_BREAKPOINT": 6,
    "EXC_RESOURCE": 10,
    "EXC_GUARD": 11,
}

_STOP_REASON_RE = re.compile(r"stop reason\s*=\s*(EXC_[A-Z_]+)")
_FRAME_RE = re.compile(
    r"frame #(\d+):\s+"  # frame number
    r"(0x[0-9a-fA-F]+)"  # address
    r"(?:\s+(\S+?)`([^\s(+]+))?"  # optional module`function
    r"(?:[^\n]*?\bat\s+(\S+?):(\d+))?",  # optional "at file:line"
)


def parse_lldb_frames(raw: str) -> list[StackFrame]:
    """Parse ``lldb bt`` output into :class:`StackFrame` objects.

    :param raw: combined lldb backtrace text.
    :return: the parsed stack frames in order.
    """
    frames: list[StackFrame] = []
    for match in _FRAME_RE.finditer(raw):
        number, address, module, function, source_file, source_line = match.groups()
        frames.append(
            StackFrame(
                frame_number=int(number),
                module=module,
                function=function,
                source_file=source_file,
                source_line=int(source_line) if source_line else None,
                instruction_address=normalize_address(address),
            )
        )
    return frames


class LldbBackend(_BaseDebugBackend):
    """Debug backend that extracts crash data from Mach-O cores via ``lldb --batch``."""

    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]] = [
        DumpFormat.APPLE_CRASHREPORT,
        DumpFormat.WINDOWS_MINIDUMP,
    ]
    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Darwin"]

    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: list[str],
    ) -> list[str]:
        """Build the ``lldb --batch`` argv that loads the core and prints a backtrace."""
        return [
            "lldb",
            "--batch",
            "-c",
            str(source.dump_path),
            "-o",
            "bt all",
            "-o",
            "register read pc sp",
            "-o",
            "quit",
        ]

    def _parse(self, raw: str, source: IncidentSource) -> DebugExtractionResult:
        """Map the Mach stop reason and parsed frames into a structured result."""
        reason_match = _STOP_REASON_RE.search(raw)
        reason = reason_match.group(1) if reason_match else ""
        fault_class = (
            map_macos_exception(_EXCEPTION_CODES[reason]) if reason in _EXCEPTION_CODES else FaultClass.UNKNOWN
        )

        frames = parse_lldb_frames(raw)
        faulting_module = frames[0].module if frames else None
        faulting_function = frames[0].function if frames else None
        exception_address = frames[0].instruction_address if frames else "0x0"

        return DebugExtractionResult(
            fault_class=fault_class,
            exception_code_raw=reason or "UNKNOWN",
            exception_address=exception_address,
            faulting_module=faulting_module,
            faulting_function=faulting_function,
            stack_frames=frames,
            symbol_resolution_score=self._symbol_score(frames),
            raw_text_excerpt=self._excerpt(raw),
        )
