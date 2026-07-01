"""Integration tests for the debug backends inside the full preprocessing path.

Replaces the MockDebugBackend used in earlier steps with the *real* CDB/GDB
backends (driven by fixture subprocess output), proving that
``IncidentSource → DebugBackend → DataAdapter → IncidentBrief → AI backend``
holds end to end. Covers Steps 1, 2 and 4 together.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from aegis_swr.backends.debug import CdbBackend, create_debug_backend
from aegis_swr.config.settings import DebugSettings, Settings
from aegis_swr.core.data_adapter import DataAdapter
from aegis_swr.core.fault_codes import FaultClass
from aegis_swr.core.schemas import IncidentMode, IncidentSource, OSKernelOutput
from tests.unit.fixtures.mock_ai_backend import MockAIBackend

FIXTURES = Path(__file__).parent.parent / "unit" / "fixtures"
_RUN = "aegis_swr.backends.debug._base.subprocess.run"


def _proc(stdout: str) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="")


def _os_kernel_payload() -> dict[str, object]:
    return {
        "exception_summary": {
            "fault_class": "memory_access_violation",
            "exception_code_raw": "0xc0000005",
            "exception_address": "0x00007ff8016a1c3f",
            "faulting_module": "db_writer",
            "faulting_function": "db_writer::serialize",
            "interpretation": "Access violation dereferencing a freed pointer.",
        },
        "hypotheses": [
            {"root_cause": "use-after-free", "faulting_module": "db_writer", "confidence": 0.8}
        ],
        "confidence_score": 0.8,
    }


async def test_real_cdb_backend_through_adapter(settings: Settings, tmp_path: Path):
    """
    [Integration] debug pipeline: verifies real cdb backend through adapter.

    Scenario:
        Given test inputs and fixtures for real cdb backend through adapter
        When test_real_cdb_backend_through_adapter executes the target flow
        Then the expected outcome for real cdb backend through adapter is confirmed.

    Boundaries:
        - Focus: real cdb backend through adapter
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to real cdb backend through adapter
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug pipeline
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))

    backend = CdbBackend(DebugSettings())
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    adapter = DataAdapter(settings)

    with mock.patch(_RUN, return_value=_proc(raw)):
        brief = await adapter.process(source, debug_backend=backend)

    assert brief.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert brief.faulting_module == "db_writer"
    assert brief.symbol_resolution_score == 0.8
    assert len(brief.stack_frames) == 5
    assert brief.dump_hash is not None and brief.dump_hash.startswith("sha256:")
    # Noise filter ran on the debugger output before it entered the brief.
    assert brief.raw_text_excerpt is not None
    assert "DBGHELP" not in brief.raw_text_excerpt
    # Symbol score 0.8 is not below 0.5, so no low-coverage warning.
    assert brief.low_symbol_coverage_warning is None


async def test_real_cdb_then_mock_ai(settings: Settings, tmp_path: Path):
    """
    [Integration] debug pipeline: verifies real cdb then mock ai.

    Scenario:
        Given test inputs and fixtures for real cdb then mock ai
        When test_real_cdb_then_mock_ai executes the target flow
        Then the expected outcome for real cdb then mock ai is confirmed.

    Boundaries:
        - Focus: real cdb then mock ai
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to real cdb then mock ai
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug pipeline
    """
    dump = tmp_path / "app.dmp"
    dump.write_bytes(b"MDMP" + b"\x00" * 64)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    adapter = DataAdapter(settings)

    with mock.patch(_RUN, return_value=_proc(raw)):
        brief = await adapter.process(source, debug_backend=CdbBackend(DebugSettings()))

    ai = MockAIBackend(responses=[_os_kernel_payload()])
    messages = [{"role": "user", "content": str(brief.model_dump(mode="json"))}]
    result = await ai.generate("You are the OS Kernel Agent.", messages, OSKernelOutput)

    assert isinstance(result, OSKernelOutput)
    assert result.exception_summary.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION


async def test_factory_linux_backend_through_adapter(settings: Settings, tmp_path: Path):
    # ELF magic so the adapter detects LINUX_CORE; the GDB backend supports it.
    """
    [Integration] debug pipeline: verifies factory linux backend through adapter.

    Scenario:
        Given test inputs and fixtures for factory linux backend through adapter
        When test_factory_linux_backend_through_adapter executes the target flow
        Then the expected outcome for factory linux backend through adapter is confirmed.

    Boundaries:
        - Focus: factory linux backend through adapter
        - Fixtures/params: settings, tmp_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory linux backend through adapter
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug pipeline
    """
    dump = tmp_path / "core.1234"
    dump.write_bytes(b"\x7fELF" + b"\x00" * 64)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=str(dump))

    backend = create_debug_backend(DebugSettings(), platform="linux")
    raw = (FIXTURES / "sample_gdb_bt.txt").read_text()
    adapter = DataAdapter(settings)

    with mock.patch(_RUN, return_value=_proc(raw)):
        brief = await adapter.process(source, debug_backend=backend)

    assert brief.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert brief.faulting_function == "db_writer::serialize"
