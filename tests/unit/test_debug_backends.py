"""Unit tests for the CDB/GDB/LLDB/WinDbgJS debug backends"""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from aegis_swr.backends.debug import (
    CdbBackend,
    GdbBackend,
    LldbBackend,
    WinDbgJSBackend,
    create_debug_backend,
)
from aegis_swr.backends.debug.cdb_worker import _extract_exception_code, parse_cdb_frames
from aegis_swr.backends.debug.symbol_path import resolve_symbol_path
from aegis_swr.backends.debug.windbg_js_worker import _CallbackBridge
from aegis_swr.config.settings import DebugSettings
from aegis_swr.core.exceptions import DebugExtractionError, PlatformNotSupportedError
from aegis_swr.core.fault_codes import FaultClass, map_windows_ntstatus
from aegis_swr.core.schemas import IncidentMode, IncidentSource

FIXTURES = Path(__file__).parent / "fixtures"
_RUN = "aegis_swr.backends.debug.base.subprocess.run"


@pytest.fixture
def debug_settings() -> DebugSettings:
    return DebugSettings()


@pytest.fixture
def dump_path(tmp_path: Path) -> str:
    path = tmp_path / "crash.dmp"
    path.write_bytes(b"MDMP" + b"\x00" * 64)
    return str(path)


def _source(dump_path: str) -> IncidentSource:
    return IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path=dump_path)


def _proc(stdout: str) -> SimpleNamespace:
    return SimpleNamespace(stdout=stdout, stderr="")


# ---------------------------------------------------------------------------
# CDB
# ---------------------------------------------------------------------------


def test_cdb_extracts_fault_class_and_fields(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies cdb extracts fault class and fields.

    Scenario:
        Given test inputs and fixtures for cdb extracts fault class and fields
        When test_cdb_extracts_fault_class_and_fields executes the target flow
        Then the expected outcome for cdb extracts fault class and fields is confirmed.

    Boundaries:
        - Focus: cdb extracts fault class and fields
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb extracts fault class and fields
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])

    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "0xc0000005"
    assert result.exception_address == "0x00007ff8016a1c3f"
    assert result.faulting_module == "db_writer"
    assert result.faulting_function == "db_writer::serialize"


def test_cdb_extracts_stack_frames(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies cdb extracts stack frames.

    Scenario:
        Given test inputs and fixtures for cdb extracts stack frames
        When test_cdb_extracts_stack_frames executes the target flow
        Then the expected outcome for cdb extracts stack frames is confirmed.

    Boundaries:
        - Focus: cdb extracts stack frames
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb extracts stack frames
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])

    assert len(result.stack_frames) == 5
    top = result.stack_frames[0]
    assert top.module == "db_writer"
    assert top.function == "db_writer::serialize"
    # Frame 3 in the fixture is a garbage (0xCCCCCCCC) frame - unresolved.
    assert result.stack_frames[3].function is None
    assert result.stack_frames[3].module is None


def test_cdb_symbol_resolution_score(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies cdb symbol resolution score.

    Scenario:
        Given test inputs and fixtures for cdb symbol resolution score
        When test_cdb_symbol_resolution_score executes the target flow
        Then the expected outcome for cdb symbol resolution score is confirmed.

    Boundaries:
        - Focus: cdb symbol resolution score
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb symbol resolution score
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    # 4 of 5 frames resolve to a function.
    assert result.symbol_resolution_score == pytest.approx(0.8)


def test_cdb_noise_filter_applied(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies cdb noise filter applied.

    Scenario:
        Given test inputs and fixtures for cdb noise filter applied
        When test_cdb_noise_filter_applied executes the target flow
        Then the expected outcome for cdb noise filter applied is confirmed.

    Boundaries:
        - Focus: cdb noise filter applied
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb noise filter applied
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert "DBGHELP" not in result.raw_text_excerpt
    assert "ModuleLoad" not in result.raw_text_excerpt


def test_cdb_parses_debug_timestamp(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies cdb parses debug timestamp.

    Scenario:
        Given test inputs and fixtures for cdb parses debug timestamp
        When test_cdb_parses_debug_timestamp executes the target flow
        Then the expected outcome for cdb parses debug timestamp is confirmed.

    Boundaries:
        - Focus: cdb parses debug timestamp
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb parses debug timestamp
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert result.debug_timestamp is not None
    assert result.debug_timestamp.year == 2026


def test_cdb_command_sequence(debug_settings: DebugSettings, dump_path: str):
    """
    [Unit] debug backends: verifies cdb command sequence.

    Scenario:
        Given test inputs and fixtures for cdb command sequence
        When test_cdb_command_sequence executes the target flow
        Then the expected outcome for cdb command sequence is confirmed.

    Boundaries:
        - Focus: cdb command sequence
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb command sequence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = CdbBackend(debug_settings)
    cmd = backend._build_command_sequence(_source(dump_path), ["C:/extra/syms"])
    assert cmd[0] == "cdb.exe"
    assert "-z" in cmd and dump_path in cmd
    assert ".reload /f /i; !analyze -v; q" in cmd
    sym_chain = cmd[cmd.index("-y") + 1]
    assert sym_chain.startswith("srv*")
    assert "msdl.microsoft.com" in sym_chain
    assert sym_chain.endswith("C:/extra/syms")


def test_cdb_symbol_chain_no_extra_paths(debug_settings: DebugSettings):
    """Empty symbol list produces a chain with no semicolons (SRV entry only)."""
    backend = CdbBackend(debug_settings)
    chain = backend._symbol_path_string([])
    assert chain.startswith("srv*")
    assert "msdl.microsoft.com" in chain
    assert ";" not in chain


def test_cdb_symbol_chain_two_paths(debug_settings: DebugSettings):
    """Two paths are both present in the chain in order."""
    backend = CdbBackend(debug_settings)
    chain = backend._symbol_path_string(["C:/proj/x64/Release", "C:/symbols"])
    assert "C:/proj/x64/Release" in chain
    assert "C:/symbols" in chain
    assert chain.index("C:/proj/x64/Release") < chain.index("C:/symbols")


def test_sym_paths_flow_from_incident_source_to_command(debug_settings: DebugSettings, dump_path: str):
    """symbol_path list on IncidentSource is forwarded verbatim to the -y chain."""
    backend = CdbBackend(debug_settings)
    source = IncidentSource(
        mode=IncidentMode.CRASH_DUMP,
        dump_path=dump_path,
        symbol_path=["C:/proj/x64/Release", "C:/symbols"],
    )
    cmd = backend._build_command_sequence(source, source.symbol_path)
    sym_chain = cmd[cmd.index("-y") + 1]
    assert "C:/proj/x64/Release" in sym_chain
    assert "C:/symbols" in sym_chain
    assert sym_chain.index("C:/proj/x64/Release") < sym_chain.index("C:/symbols")


@pytest.mark.parametrize(
    "raw",
    [
        "EXCEPTION_CODE: (NTSTATUS) 0xc0000005 - access violation",
        "ERROR_CODE: (NTSTATUS) 0xc0000005 - The instruction at 0x%p referenced memory",
        "EXCEPTION_CODE_STR:  c0000005",
        "ExceptionCode: c0000005 (Access violation)",
    ],
)
def test_cdb_extracts_exception_code_from_any_key(raw: str):
    # A NULL_POINTER_WRITE dump reports the code under ERROR_CODE /
    # EXCEPTION_CODE_STR rather than EXCEPTION_CODE; all must resolve.
    """
    [Unit] debug backends: verifies cdb extracts exception code from any key.

    Scenario:
        Given test inputs and fixtures for cdb extracts exception code from any key
        When test_cdb_extracts_exception_code_from_any_key executes the target flow
        Then the expected outcome for cdb extracts exception code from any key is confirmed.

    Boundaries:
        - Focus: cdb extracts exception code from any key
        - Fixtures/params: raw (parametrized, 4 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb extracts exception code from any key
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    code = _extract_exception_code(raw)
    assert code == "0xc0000005"
    assert map_windows_ntstatus(code) == FaultClass.MEMORY_ACCESS_VIOLATION


def test_cdb_extracts_exception_code_absent():
    """
    [Unit] debug backends: verifies cdb extracts exception code absent.

    Scenario:
        Given test inputs and fixtures for cdb extracts exception code absent
        When test_cdb_extracts_exception_code_absent executes the target flow
        Then the expected outcome for cdb extracts exception code absent is confirmed.

    Boundaries:
        - Focus: cdb extracts exception code absent
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb extracts exception code absent
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    assert _extract_exception_code("no code here") == "0x0"


def test_cdb_frame_source_line_parsing():
    """
    [Unit] debug backends: verifies cdb frame source line parsing.

    Scenario:
        Given test inputs and fixtures for cdb frame source line parsing
        When test_cdb_frame_source_line_parsing executes the target flow
        Then the expected outcome for cdb frame source line parsing is confirmed.

    Boundaries:
        - Focus: cdb frame source line parsing
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb frame source line parsing
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (
        "STACK_TEXT:\n"
        "00 00000012`abcd0000 00007ff8`016a1c3f "
        "db_writer!db_writer::serialize+0x4a [c:\\src\\db_writer.cpp @ 142]\n"
        "\n"
    )
    frames = parse_cdb_frames(raw)
    assert len(frames) == 1
    assert frames[0].source_file == "c:\\src\\db_writer.cpp"
    assert frames[0].source_line == 142


def test_cdb_parses_analyze_stack_text_format():
    # Real `!analyze -v` STACK_TEXT: backtick 64-bit addresses, colon-delimited
    # argument columns, no leading frame number, plus a column header to skip.
    """
    [Unit] debug backends: verifies cdb parses analyze stack text format.

    Scenario:
        Given test inputs and fixtures for cdb parses analyze stack text format
        When test_cdb_parses_analyze_stack_text_format executes the target flow
        Then the expected outcome for cdb parses analyze stack text format is confirmed.

    Boundaries:
        - Focus: cdb parses analyze stack text format
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to cdb parses analyze stack text format
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (
        "STACK_TEXT:  \n"
        "Child-SP          RetAddr               : Args to Child           : Call Site\n"
        "000000af`8e7de420 00007ff7`2a734087     : 000001d1`00000007 00007ff7`2a742ed0 "
        ": CrashUi!Crash_Window::on_access_violation_click+0x509\n"
        "000000af`8e7de8e0 00007ffa`ade2e858     : 00000000`00000000 00000000`ade28f71 "
        ": user32!UserCallWinProcCheckWow+0x2f8\n"
        "\n"
    )
    frames = parse_cdb_frames(raw)
    assert len(frames) == 2  # header row is skipped
    assert frames[0].module == "CrashUi"
    assert frames[0].function == "Crash_Window::on_access_violation_click"
    assert frames[0].instruction_address == "0x00007ff72a734087"
    assert frames[1].module == "user32"
    # All frames resolve a function on this trace.
    backend_score = sum(1 for f in frames if f.function) / len(frames)
    assert backend_score == 1.0


# ---------------------------------------------------------------------------
# GDB
# ---------------------------------------------------------------------------


def test_gdb_maps_sigsegv(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies gdb maps sigsegv.

    Scenario:
        Given test inputs and fixtures for gdb maps sigsegv
        When test_gdb_maps_sigsegv executes the target flow
        Then the expected outcome for gdb maps sigsegv is confirmed.

    Boundaries:
        - Focus: gdb maps sigsegv
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to gdb maps sigsegv
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_gdb_bt.txt").read_text()
    backend = GdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "SIGSEGV"


def test_gdb_parses_frames(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies gdb parses frames.

    Scenario:
        Given test inputs and fixtures for gdb parses frames
        When test_gdb_parses_frames executes the target flow
        Then the expected outcome for gdb parses frames is confirmed.

    Boundaries:
        - Focus: gdb parses frames
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to gdb parses frames
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_gdb_bt.txt").read_text()
    backend = GdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert len(result.stack_frames) == 5
    assert result.faulting_function == "db_writer::serialize"
    assert result.stack_frames[0].source_line == 142
    # frame #3 is "?? ()" - unresolved.
    assert result.stack_frames[3].function is None
    assert result.symbol_resolution_score == pytest.approx(0.8)


def test_gdb_command_sequence(debug_settings: DebugSettings, dump_path: str):
    """
    [Unit] debug backends: verifies gdb command sequence.

    Scenario:
        Given test inputs and fixtures for gdb command sequence
        When test_gdb_command_sequence executes the target flow
        Then the expected outcome for gdb command sequence is confirmed.

    Boundaries:
        - Focus: gdb command sequence
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to gdb command sequence
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = GdbBackend(debug_settings)
    cmd = backend._build_command_sequence(_source(dump_path), [])
    assert cmd[0] == "gdb"
    assert "--batch" in cmd
    assert any(f"core-file {dump_path}" == part for part in cmd)


# ---------------------------------------------------------------------------
# LLDB
# ---------------------------------------------------------------------------


def test_lldb_maps_exc_bad_access(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies lldb maps exc bad access.

    Scenario:
        Given test inputs and fixtures for lldb maps exc bad access
        When test_lldb_maps_exc_bad_access executes the target flow
        Then the expected outcome for lldb maps exc bad access is confirmed.

    Boundaries:
        - Focus: lldb maps exc bad access
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to lldb maps exc bad access
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_lldb_bt.txt").read_text()
    backend = LldbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "EXC_BAD_ACCESS"


def test_lldb_parses_frames(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies lldb parses frames.

    Scenario:
        Given test inputs and fixtures for lldb parses frames
        When test_lldb_parses_frames executes the target flow
        Then the expected outcome for lldb parses frames is confirmed.

    Boundaries:
        - Focus: lldb parses frames
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to lldb parses frames
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    raw = (FIXTURES / "sample_lldb_bt.txt").read_text()
    backend = LldbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), [])
    assert len(result.stack_frames) == 5
    assert result.faulting_module == "libdbwriter.dylib"
    assert result.faulting_function == "db_writer::serialize"
    assert result.stack_frames[0].source_line == 142
    # frame #4 has no module backtick - unresolved.
    assert result.stack_frames[4].function is None
    assert result.symbol_resolution_score == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Validation & subprocess error handling
# ---------------------------------------------------------------------------


def test_extract_without_dump_path_raises(debug_settings: DebugSettings):
    """
    [Unit] debug backends: verifies extract without dump path raises.

    Scenario:
        Given test inputs and fixtures for extract without dump path raises
        When test_extract_without_dump_path_raises executes the target flow
        Then the expected outcome for extract without dump path raises is confirmed.

    Boundaries:
        - Focus: extract without dump path raises
        - Fixtures/params: debug_settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to extract without dump path raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = CdbBackend(debug_settings)
    with pytest.raises(DebugExtractionError):
        backend.extract(IncidentSource(mode=IncidentMode.CRASH_DUMP), [])


def test_extract_missing_file_raises(debug_settings: DebugSettings):
    """
    [Unit] debug backends: verifies extract missing file raises.

    Scenario:
        Given test inputs and fixtures for extract missing file raises
        When test_extract_missing_file_raises executes the target flow
        Then the expected outcome for extract missing file raises is confirmed.

    Boundaries:
        - Focus: extract missing file raises
        - Fixtures/params: debug_settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to extract missing file raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = CdbBackend(debug_settings)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path="/no/such/file.dmp")
    with pytest.raises(DebugExtractionError):
        backend.extract(source, [])


def test_missing_binary_raises_platform_error(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies missing binary raises platform error.

    Scenario:
        Given test inputs and fixtures for missing binary raises platform error
        When test_missing_binary_raises_platform_error executes the target flow
        Then the expected outcome for missing binary raises platform error is confirmed.

    Boundaries:
        - Focus: missing binary raises platform error
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to missing binary raises platform error
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, side_effect=FileNotFoundError()):  # noqa: SIM117
        with pytest.raises(PlatformNotSupportedError):
            backend.extract(_source(dump_path), [])


def test_timeout_raises_debug_error(debug_settings: DebugSettings, dump_path: str):
    """
    [Mock] debug backends: verifies timeout raises debug error.

    Scenario:
        Given test inputs and fixtures for timeout raises debug error
        When test_timeout_raises_debug_error executes the target flow
        Then the expected outcome for timeout raises debug error is confirmed.

    Boundaries:
        - Focus: timeout raises debug error
        - Fixtures/params: debug_settings, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to timeout raises debug error
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = CdbBackend(debug_settings)
    err = subprocess.TimeoutExpired(cmd="cdb.exe", timeout=1)
    with mock.patch(_RUN, side_effect=err):  # noqa: SIM117
        with pytest.raises(DebugExtractionError):
            backend.extract(_source(dump_path), [])


# ---------------------------------------------------------------------------
# Factory & symbol path
# ---------------------------------------------------------------------------


_JS_AVAIL = "aegis_swr.backends.debug._windbg_js_available"


@pytest.mark.parametrize(
    "platform,expected",
    [("linux", GdbBackend), ("darwin", LldbBackend)],
)
def test_factory_selects_non_windows_backend(debug_settings: DebugSettings, platform: str, expected: type):
    """
    [Unit] debug backends: verifies factory selects non windows backend.

    Scenario:
        Given test inputs and fixtures for factory selects non windows backend
        When test_factory_selects_non_windows_backend executes the target flow
        Then the expected outcome for factory selects non windows backend is confirmed.

    Boundaries:
        - Focus: factory selects non windows backend
        - Fixtures/params: debug_settings, platform, expected (parametrized, 2 cases)
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory selects non windows backend
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = create_debug_backend(debug_settings, platform=platform)
    assert isinstance(backend, expected)


def test_factory_unsupported_platform_raises(debug_settings: DebugSettings):
    """
    [Unit] debug backends: verifies factory unsupported platform raises.

    Scenario:
        Given test inputs and fixtures for factory unsupported platform raises
        When test_factory_unsupported_platform_raises executes the target flow
        Then the expected outcome for factory unsupported platform raises is confirmed.

    Boundaries:
        - Focus: factory unsupported platform raises
        - Fixtures/params: debug_settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory unsupported platform raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with pytest.raises(PlatformNotSupportedError):
        create_debug_backend(debug_settings, platform="freebsd")


def test_resolve_symbol_path_explicit():
    """
    [Unit] debug backends: verifies resolve symbol path explicit.

    Scenario:
        Given test inputs and fixtures for resolve symbol path explicit
        When test_resolve_symbol_path_explicit executes the target flow
        Then the expected outcome for resolve symbol path explicit is confirmed.

    Boundaries:
        - Focus: resolve symbol path explicit
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolve symbol path explicit
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    assert resolve_symbol_path("D:/symbols") == Path("D:/symbols")


def test_resolve_symbol_path_default(monkeypatch: pytest.MonkeyPatch):
    """
    [Mock] debug backends: verifies resolve symbol path default.

    Scenario:
        Given test inputs and fixtures for resolve symbol path default
        When test_resolve_symbol_path_default executes the target flow
        Then the expected outcome for resolve symbol path default is confirmed.

    Boundaries:
        - Focus: resolve symbol path default
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolve symbol path default
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    monkeypatch.delenv("AEGIS_SYMBOL_CACHE", raising=False)
    path = resolve_symbol_path(None)
    assert "symbols" in str(path).lower()


def test_resolve_symbol_path_env_override(monkeypatch: pytest.MonkeyPatch):
    """
    [Mock] debug backends: verifies resolve symbol path env override.

    Scenario:
        Given test inputs and fixtures for resolve symbol path env override
        When test_resolve_symbol_path_env_override executes the target flow
        Then the expected outcome for resolve symbol path env override is confirmed.

    Boundaries:
        - Focus: resolve symbol path env override
        - Fixtures/params: monkeypatch
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to resolve symbol path env override
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    monkeypatch.setenv("AEGIS_SYMBOL_CACHE", "/tmp/mysyms")
    assert resolve_symbol_path(None) == Path("/tmp/mysyms")


# ---------------------------------------------------------------------------
# WinDbgJSBackend - callback bridge unit tests (real sockets, no subprocess)
# ---------------------------------------------------------------------------


def test_callback_bridge_assigns_ephemeral_port():
    """_CallbackBridge must bind to an OS-assigned non-zero port"""
    with _CallbackBridge(callback_timeout=2) as bridge:
        assert bridge.port > 0
        assert bridge.port < 65536


def test_callback_bridge_receives_payload():
    """A POST to the bridge port should be returned by wait_for_payload"""
    with _CallbackBridge(callback_timeout=2) as bridge:
        body = json.dumps({"hello": "world"})
        req = urllib.request.Request(
            f"http://127.0.0.1:{bridge.port}/",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)  # noqa: S310
        payload = bridge.wait_for_payload()

    assert json.loads(payload) == {"hello": "world"}


def test_callback_bridge_per_instance_queue_isolation():
    """Two simultaneous bridges must not receive each other's payloads"""
    with (
        _CallbackBridge(callback_timeout=2) as bridge_a,
        _CallbackBridge(callback_timeout=2) as bridge_b,
    ):
        # Send only to bridge_b
        body = b'{"target": "b"}'
        req = urllib.request.Request(
            f"http://127.0.0.1:{bridge_b.port}/",
            data=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)  # noqa: S310
        payload_b = bridge_b.wait_for_payload()
        # bridge_a's queue must still be empty
        with pytest.raises(DebugExtractionError):
            bridge_a.wait_for_payload()

    assert json.loads(payload_b)["target"] == "b"


def test_callback_bridge_timeout_raises():
    """
    [Unit] debug backends: verifies callback bridge timeout raises.

    Scenario:
        Given test inputs and fixtures for callback bridge timeout raises
        When test_callback_bridge_timeout_raises executes the target flow
        Then the expected outcome for callback bridge timeout raises is confirmed.

    Boundaries:
        - Focus: callback bridge timeout raises
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to callback bridge timeout raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with _CallbackBridge(callback_timeout=0) as bridge:
        assert bridge.port > 0
        with pytest.raises(DebugExtractionError, match="Timed out"):
            bridge.wait_for_payload()


# ---------------------------------------------------------------------------
# WinDbgJSBackend - backend tests (subprocess + bridge mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def js_settings() -> DebugSettings:
    return DebugSettings(engine="windbg_js")


@pytest.fixture
def js_backend(js_settings: DebugSettings) -> WinDbgJSBackend:
    return WinDbgJSBackend(js_settings)


def _mock_bridge(payload: str) -> mock.MagicMock:
    """Return a mock _CallbackBridge instance that yields *payload*"""
    bridge = mock.MagicMock(spec=_CallbackBridge)
    bridge.__enter__ = mock.Mock(return_value=bridge)
    bridge.__exit__ = mock.Mock(return_value=None)
    bridge.port = 54321
    bridge.wait_for_payload.return_value = payload
    return bridge


_JS_PROVIDER_STDOUT = "Loaded extension DLL JsProvider.dll\nReady.\n"
_BRIDGE_PATH = "aegis_swr.backends.debug.windbg_js_worker._CallbackBridge"


def test_windbg_js_parses_ddm_json(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Mock] debug backends: verifies windbg js parses ddm json.

    Scenario:
        Given test inputs and fixtures for windbg js parses ddm json
        When test_windbg_js_parses_ddm_json executes the target flow
        Then the expected outcome for windbg js parses ddm json is confirmed.

    Boundaries:
        - Focus: windbg js parses ddm json
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js parses ddm json
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    payload = (FIXTURES / "sample_windbg_js_payload.json").read_text()
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge(payload)),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
    ):
        result = js_backend.extract(_source(dump_path), [])

    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "0xc0000005"
    assert result.exception_address == "0x00007ff8016a1c3f"
    assert result.faulting_module == "db_writer"
    assert result.faulting_function == "db_writer::serialize"
    assert len(result.stack_frames) == 5
    # 4 resolved functions out of 5 frames
    assert result.symbol_resolution_score == pytest.approx(0.8)
    # Frame 5 (index 4) has an empty module + function → unresolved
    assert result.stack_frames[4].function is None
    assert result.stack_frames[4].module is None


def test_windbg_js_command_uses_scriptload(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Unit] debug backends: verifies windbg js command uses scriptload.

    Scenario:
        Given test inputs and fixtures for windbg js command uses scriptload
        When test_windbg_js_command_uses_scriptload executes the target flow
        Then the expected outcome for windbg js command uses scriptload is confirmed.

    Boundaries:
        - Focus: windbg js command uses scriptload
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js command uses scriptload
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    cmd = js_backend._js_command(_source(dump_path), [], "/tmp/test.js")
    assert cmd[0] == "cdb.exe"
    assert "-z" in cmd
    joined = " ".join(cmd)
    assert ".scriptload" in joined
    assert "test.js" in joined


def test_windbg_js_raises_on_missing_jsprovider(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Mock] debug backends: verifies windbg js raises on missing jsprovider.

    Scenario:
        Given test inputs and fixtures for windbg js raises on missing jsprovider
        When test_windbg_js_raises_on_missing_jsprovider executes the target flow
        Then the expected outcome for windbg js raises on missing jsprovider is confirmed.

    Boundaries:
        - Focus: windbg js raises on missing jsprovider
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js raises on missing jsprovider
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    payload = (FIXTURES / "sample_windbg_js_payload.json").read_text()
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge(payload)),
        mock.patch(_RUN, return_value=_proc("CDB version 10.0\nReady.\n")),
        pytest.raises(DebugExtractionError, match="JsProvider"),
    ):
        js_backend.extract(_source(dump_path), [])


def test_windbg_js_raises_on_callback_timeout(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Mock] debug backends: verifies windbg js raises on callback timeout.

    Scenario:
        Given test inputs and fixtures for windbg js raises on callback timeout
        When test_windbg_js_raises_on_callback_timeout executes the target flow
        Then the expected outcome for windbg js raises on callback timeout is confirmed.

    Boundaries:
        - Focus: windbg js raises on callback timeout
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js raises on callback timeout
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    bridge = _mock_bridge("")
    bridge.wait_for_payload.side_effect = DebugExtractionError("Timed out")
    with (
        mock.patch(_BRIDGE_PATH, return_value=bridge),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
        pytest.raises(DebugExtractionError, match="Timed out"),
    ):
        js_backend.extract(_source(dump_path), [])


def test_windbg_js_missing_asset_raises(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Mock] debug backends: verifies windbg js missing asset raises.

    Scenario:
        Given test inputs and fixtures for windbg js missing asset raises
        When test_windbg_js_missing_asset_raises executes the target flow
        Then the expected outcome for windbg js missing asset raises is confirmed.

    Boundaries:
        - Focus: windbg js missing asset raises
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js missing asset raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with (
        mock.patch.object(js_backend, "_asset_path", return_value=Path("/no/such.js")),
        pytest.raises(DebugExtractionError, match="asset not found"),
    ):
        js_backend.extract(_source(dump_path), [])


def test_windbg_js_parses_invalid_json_raises(js_backend: WinDbgJSBackend, dump_path: str):
    """
    [Mock] debug backends: verifies windbg js parses invalid json raises.

    Scenario:
        Given test inputs and fixtures for windbg js parses invalid json raises
        When test_windbg_js_parses_invalid_json_raises executes the target flow
        Then the expected outcome for windbg js parses invalid json raises is confirmed.

    Boundaries:
        - Focus: windbg js parses invalid json raises
        - Fixtures/params: js_backend, dump_path
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js parses invalid json raises
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge("not json {")),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
        pytest.raises(DebugExtractionError, match="invalid JSON"),
    ):
        js_backend.extract(_source(dump_path), [])


def test_windbg_js_inject_params_substitutes_all_tokens(
    js_backend: WinDbgJSBackend,
):
    """
    [Unit] debug backends: verifies windbg js inject params substitutes all tokens.

    Scenario:
        Given test inputs and fixtures for windbg js inject params substitutes all tokens
        When test_windbg_js_inject_params_substitutes_all_tokens executes the target flow
        Then the expected outcome for windbg js inject params substitutes all tokens is confirmed.

    Boundaries:
        - Focus: windbg js inject params substitutes all tokens
        - Fixtures/params: js_backend
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to windbg js inject params substitutes all tokens
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    template = "URL=__CALLBACK_URL__ F=__MAX_FAULTING_FRAMES__ O=__MAX_OTHER_FRAMES__"
    result = js_backend._inject_params(template, port=12345)
    assert "127.0.0.1:12345" in result
    assert "__CALLBACK_URL__" not in result
    assert "__MAX_FAULTING_FRAMES__" not in result
    assert "__MAX_OTHER_FRAMES__" not in result


def test_windbg_js_symbol_chain_two_paths(
    js_settings: DebugSettings,
):
    """WinDbgJSBackend uses the same chain logic as CDB: both paths appear in order."""
    backend = WinDbgJSBackend(js_settings)
    chain = backend._symbol_path_string(["C:/proj/x64/Release", "C:/symbols"])
    assert "C:/proj/x64/Release" in chain
    assert "C:/symbols" in chain
    assert chain.index("C:/proj/x64/Release") < chain.index("C:/symbols")


# ---------------------------------------------------------------------------
# Factory - Windows engine selection
# ---------------------------------------------------------------------------


def test_factory_returns_windbg_js_when_engine_forced(js_settings: DebugSettings):
    """
    [Unit] debug backends: verifies factory returns windbg js when engine forced.

    Scenario:
        Given test inputs and fixtures for factory returns windbg js when engine forced
        When test_factory_returns_windbg_js_when_engine_forced executes the target flow
        Then the expected outcome for factory returns windbg js when engine forced is confirmed.

    Boundaries:
        - Focus: factory returns windbg js when engine forced
        - Fixtures/params: js_settings
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory returns windbg js when engine forced
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = create_debug_backend(js_settings, platform="win32")
    assert isinstance(backend, WinDbgJSBackend)


def test_factory_returns_cdb_when_engine_forced():
    """
    [Unit] debug backends: verifies factory returns cdb when engine forced.

    Scenario:
        Given test inputs and fixtures for factory returns cdb when engine forced
        When test_factory_returns_cdb_when_engine_forced executes the target flow
        Then the expected outcome for factory returns cdb when engine forced is confirmed.

    Boundaries:
        - Focus: factory returns cdb when engine forced
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory returns cdb when engine forced
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    backend = create_debug_backend(DebugSettings(engine="cdb"), platform="win32")
    assert isinstance(backend, CdbBackend)


def test_factory_auto_returns_cdb_when_js_unavailable():
    """
    [Mock] debug backends: verifies factory auto returns cdb when js unavailable.

    Scenario:
        Given test inputs and fixtures for factory auto returns cdb when js unavailable
        When test_factory_auto_returns_cdb_when_js_unavailable executes the target flow
        Then the expected outcome for factory auto returns cdb when js unavailable is confirmed.

    Boundaries:
        - Focus: factory auto returns cdb when js unavailable
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory auto returns cdb when js unavailable
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with mock.patch(_JS_AVAIL, return_value=False):
        backend = create_debug_backend(DebugSettings(engine="auto"), platform="win32")
    assert isinstance(backend, CdbBackend)


def test_factory_auto_returns_windbg_js_when_available():
    """
    [Mock] debug backends: verifies factory auto returns windbg js when available.

    Scenario:
        Given test inputs and fixtures for factory auto returns windbg js when available
        When test_factory_auto_returns_windbg_js_when_available executes the target flow
        Then the expected outcome for factory auto returns windbg js when available is confirmed.

    Boundaries:
        - Focus: factory auto returns windbg js when available
        - Fixtures/params: none
        - Scope: assertions and setup in this test case only

    On failure, first check:
        - Assertion details tied to factory auto returns windbg js when available
        - Fixture or parameter values used by this test
        - Recent changes in code paths exercised by debug backends
    """
    with mock.patch(_JS_AVAIL, return_value=True):
        backend = create_debug_backend(DebugSettings(engine="auto"), platform="win32")
    assert isinstance(backend, WinDbgJSBackend)
