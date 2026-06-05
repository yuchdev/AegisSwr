"""Linux GDB debug backend.

Parses ``gdb --batch`` backtraces from ELF core files and maps POSIX signals to
:class:`FaultClass`.
"""
from __future__ import annotations

import re
from typing import ClassVar

from aegis_swr.backends.debug._base import _BaseDebugBackend, normalize_address
from aegis_swr.core.fault_codes import FaultClass, map_linux_signal
from aegis_swr.core.schemas import DebugExtractionResult, DumpFormat, StackFrame
from aegis_swr.core.schemas import IncidentSource

# Signal name -> number (kept local so it works identically on any host OS).
_SIGNAL_NUMBERS = {
    "SIGILL": 4,
    "SIGABRT": 6,
    "SIGBUS": 7,
    "SIGFPE": 8,
    "SIGSEGV": 11,
    "SIGSYS": 31,
}

_SIGNAL_RE = re.compile(r"signal\s+(SIG[A-Z]+)")
_FRAME_RE = re.compile(
    r"^#(\d+)\s+"                         # frame number
    r"(?:(0x[0-9a-fA-F]+)\s+in\s+)?"     # optional "0x... in "
    r"(\S+)\s*\([^)]*\)"                 # function (...)
    r"(?:\s+at\s+(\S+?):(\d+))?",        # optional "at file:line"
)


def parse_gdb_frames(raw: str) -> list[StackFrame]:
    frames: list[StackFrame] = []
    for line in raw.splitlines():
        match = _FRAME_RE.match(line.strip())
        if not match:
            continue
        number, address, function, source_file, source_line = match.groups()
        resolved = function not in ("??", "?? ()", None)
        frames.append(
            StackFrame(
                frame_number=int(number),
                module=None,  # gdb bt does not reliably surface the module name
                function=function if resolved else None,
                source_file=source_file,
                source_line=int(source_line) if source_line else None,
                instruction_address=normalize_address(address) if address else "0x0",
            )
        )
    return frames


class GdbBackend(_BaseDebugBackend):
    SUPPORTED_FORMATS: ClassVar[list[DumpFormat]] = [
        DumpFormat.LINUX_CORE,
        DumpFormat.WINDOWS_MINIDUMP,
    ]
    SUPPORTED_PLATFORMS: ClassVar[list[str]] = ["Linux"]

    def _build_command_sequence(
        self,
        source: IncidentSource,
        symbol_path: str | None,
    ) -> list[str]:
        return [
            "gdb",
            "--batch",
            "--quiet",
            "-ex",
            f"core-file {source.dump_path}",
            "-ex",
            "bt 20",
            "-ex",
            "info registers rip rsp rbp",
            "-ex",
            "quit",
        ]

    def _parse(self, raw: str, source: IncidentSource) -> DebugExtractionResult:
        signal_match = _SIGNAL_RE.search(raw)
        signal_name = signal_match.group(1) if signal_match else ""
        fault_class = (
            map_linux_signal(_SIGNAL_NUMBERS[signal_name])
            if signal_name in _SIGNAL_NUMBERS
            else FaultClass.UNKNOWN
        )

        frames = parse_gdb_frames(raw)
        faulting_function = frames[0].function if frames else None
        exception_address = frames[0].instruction_address if frames else "0x0"

        return DebugExtractionResult(
            fault_class=fault_class,
            exception_code_raw=signal_name or "UNKNOWN",
            exception_address=exception_address,
            faulting_module=None,
            faulting_function=faulting_function,
            stack_frames=frames,
            symbol_resolution_score=self._symbol_score(frames),
            raw_text_excerpt=self._excerpt(raw),
        )
