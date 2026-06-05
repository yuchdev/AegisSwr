"""Reusable mock debug backend for tests (shared across unit + integration)"""
from __future__ import annotations

from aegis_swr.backends.base import DebugBackend
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import (
    DebugExtractionResult,
    DumpFormat,
    IncidentSource,
    StackFrame,
)


class MockDebugBackend(DebugBackend):
    SUPPORTED_FORMATS = [DumpFormat.WINDOWS_MINIDUMP]
    SUPPORTED_PLATFORMS = ["Windows"]

    def __init__(self, result: DebugExtractionResult):
        self._result = result
        self.extract_called = False

    def extract(self, source: IncidentSource, symbol_path: str | None) -> DebugExtractionResult:
        self.extract_called = True
        return self._result

    def _build_command_sequence(
        self, source: IncidentSource, symbol_path: str | None
    ) -> list[str]:
        return ["mock"]


def default_extraction(symbol_score: float = 0.87) -> DebugExtractionResult:
    return DebugExtractionResult(
        fault_class=FaultClass.MEMORY_ACCESS_VIOLATION,
        exception_code_raw="0xc0000005",
        exception_address="0x00007ff8016a1c3f",
        faulting_module="db_writer",
        faulting_function="db_writer::serialize",
        stack_frames=[
            StackFrame(
                frame_number=0,
                module="db_writer",
                function="db_writer::serialize",
                instruction_address="0x00007ff8016a1c3f",
            )
        ],
        symbol_resolution_score=symbol_score,
        raw_text_excerpt="DBGHELP: ntdll.pdb - file not found\nEXCEPTION_CODE: 0xc0000005\n",
    )
