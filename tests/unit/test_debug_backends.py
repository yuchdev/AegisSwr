"""Unit tests for the CDB/GDB/LLDB/WinDbgJS debug backends."""
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
from aegis_swr.backends.debug._symbol_path import resolve_symbol_path
from aegis_swr.backends.debug.cdb_worker import _extract_exception_code, parse_cdb_frames
from aegis_swr.backends.debug.windbg_js_worker import _CallbackBridge
from aegis_swr.config.settings import DebugSettings
from aegis_swr.core.exceptions import DebugExtractionError, PlatformNotSupportedError
from aegis_swr.core.fault_codes import FaultClass, map_windows_ntstatus
from aegis_swr.core.schemas import IncidentMode, IncidentSource

FIXTURES = Path(__file__).parent / "fixtures"
_RUN = "aegis_swr.backends.debug._base.subprocess.run"


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


def test_cdb_extracts_fault_class_and_fields(
    debug_settings: DebugSettings, dump_path: str
) -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)

    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "0xc0000005"
    assert result.exception_address == "0x00007ff8016a1c3f"
    assert result.faulting_module == "db_writer"
    assert result.faulting_function == "db_writer::serialize"


def test_cdb_extracts_stack_frames(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)

    assert len(result.stack_frames) == 5
    top = result.stack_frames[0]
    assert top.module == "db_writer"
    assert top.function == "db_writer::serialize"
    # Frame 3 in the fixture is a garbage (0xCCCCCCCC) frame — unresolved.
    assert result.stack_frames[3].function is None
    assert result.stack_frames[3].module is None


def test_cdb_symbol_resolution_score(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    # 4 of 5 frames resolve to a function.
    assert result.symbol_resolution_score == pytest.approx(0.8)


def test_cdb_noise_filter_applied(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert "DBGHELP" not in result.raw_text_excerpt
    assert "ModuleLoad" not in result.raw_text_excerpt


def test_cdb_parses_debug_timestamp(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_cdb_output.txt").read_text()
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert result.debug_timestamp is not None
    assert result.debug_timestamp.year == 2026


def test_cdb_command_sequence(debug_settings: DebugSettings, dump_path: str) -> None:
    backend = CdbBackend(debug_settings)
    cmd = backend._build_command_sequence(_source(dump_path), "C:/extra/syms")
    assert cmd[0] == "cdb.exe"
    assert "-z" in cmd and dump_path in cmd
    assert ".reload /f /i; !analyze -v; q" in cmd
    sym_chain = cmd[cmd.index("-y") + 1]
    assert sym_chain.startswith("srv*")
    assert "msdl.microsoft.com" in sym_chain
    assert sym_chain.endswith("C:/extra/syms")


@pytest.mark.parametrize(
    "raw",
    [
        "EXCEPTION_CODE: (NTSTATUS) 0xc0000005 - access violation",
        "ERROR_CODE: (NTSTATUS) 0xc0000005 - The instruction at 0x%p referenced memory",
        "EXCEPTION_CODE_STR:  c0000005",
        "ExceptionCode: c0000005 (Access violation)",
    ],
)
def test_cdb_extracts_exception_code_from_any_key(raw: str) -> None:
    # A NULL_POINTER_WRITE dump reports the code under ERROR_CODE /
    # EXCEPTION_CODE_STR rather than EXCEPTION_CODE; all must resolve.
    code = _extract_exception_code(raw)
    assert code == "0xc0000005"
    assert map_windows_ntstatus(code) == FaultClass.MEMORY_ACCESS_VIOLATION


def test_cdb_extracts_exception_code_absent() -> None:
    assert _extract_exception_code("no code here") == "0x0"


def test_cdb_frame_source_line_parsing() -> None:
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


def test_cdb_parses_analyze_stack_text_format() -> None:
    # Real `!analyze -v` STACK_TEXT: backtick 64-bit addresses, colon-delimited
    # argument columns, no leading frame number, plus a column header to skip.
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


def test_gdb_maps_sigsegv(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_gdb_bt.txt").read_text()
    backend = GdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "SIGSEGV"


def test_gdb_parses_frames(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_gdb_bt.txt").read_text()
    backend = GdbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert len(result.stack_frames) == 5
    assert result.faulting_function == "db_writer::serialize"
    assert result.stack_frames[0].source_line == 142
    # frame #3 is "?? ()" — unresolved.
    assert result.stack_frames[3].function is None
    assert result.symbol_resolution_score == pytest.approx(0.8)


def test_gdb_command_sequence(debug_settings: DebugSettings, dump_path: str) -> None:
    backend = GdbBackend(debug_settings)
    cmd = backend._build_command_sequence(_source(dump_path), None)
    assert cmd[0] == "gdb"
    assert "--batch" in cmd
    assert any(f"core-file {dump_path}" == part for part in cmd)


# ---------------------------------------------------------------------------
# LLDB
# ---------------------------------------------------------------------------


def test_lldb_maps_exc_bad_access(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_lldb_bt.txt").read_text()
    backend = LldbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert result.fault_class == FaultClass.MEMORY_ACCESS_VIOLATION
    assert result.exception_code_raw == "EXC_BAD_ACCESS"


def test_lldb_parses_frames(debug_settings: DebugSettings, dump_path: str) -> None:
    raw = (FIXTURES / "sample_lldb_bt.txt").read_text()
    backend = LldbBackend(debug_settings)
    with mock.patch(_RUN, return_value=_proc(raw)):
        result = backend.extract(_source(dump_path), None)
    assert len(result.stack_frames) == 5
    assert result.faulting_module == "libdbwriter.dylib"
    assert result.faulting_function == "db_writer::serialize"
    assert result.stack_frames[0].source_line == 142
    # frame #4 has no module backtick — unresolved.
    assert result.stack_frames[4].function is None
    assert result.symbol_resolution_score == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Validation & subprocess error handling
# ---------------------------------------------------------------------------


def test_extract_without_dump_path_raises(debug_settings: DebugSettings) -> None:
    backend = CdbBackend(debug_settings)
    with pytest.raises(DebugExtractionError):
        backend.extract(IncidentSource(mode=IncidentMode.CRASH_DUMP), None)


def test_extract_missing_file_raises(debug_settings: DebugSettings) -> None:
    backend = CdbBackend(debug_settings)
    source = IncidentSource(mode=IncidentMode.CRASH_DUMP, dump_path="/no/such/file.dmp")
    with pytest.raises(DebugExtractionError):
        backend.extract(source, None)


def test_missing_binary_raises_platform_error(
    debug_settings: DebugSettings, dump_path: str
) -> None:
    backend = CdbBackend(debug_settings)
    with mock.patch(_RUN, side_effect=FileNotFoundError()):  # noqa: SIM117
        with pytest.raises(PlatformNotSupportedError):
            backend.extract(_source(dump_path), None)


def test_timeout_raises_debug_error(debug_settings: DebugSettings, dump_path: str) -> None:
    backend = CdbBackend(debug_settings)
    err = subprocess.TimeoutExpired(cmd="cdb.exe", timeout=1)
    with mock.patch(_RUN, side_effect=err):  # noqa: SIM117
        with pytest.raises(DebugExtractionError):
            backend.extract(_source(dump_path), None)


# ---------------------------------------------------------------------------
# Factory & symbol path
# ---------------------------------------------------------------------------


_JS_AVAIL = "aegis_swr.backends.debug._windbg_js_available"


@pytest.mark.parametrize(
    "platform,expected",
    [("linux", GdbBackend), ("darwin", LldbBackend)],
)
def test_factory_selects_non_windows_backend(
    debug_settings: DebugSettings, platform: str, expected: type
) -> None:
    backend = create_debug_backend(debug_settings, platform=platform)
    assert isinstance(backend, expected)


def test_factory_unsupported_platform_raises(debug_settings: DebugSettings) -> None:
    with pytest.raises(PlatformNotSupportedError):
        create_debug_backend(debug_settings, platform="freebsd")


def test_resolve_symbol_path_explicit() -> None:
    assert resolve_symbol_path("D:/symbols") == Path("D:/symbols")


def test_resolve_symbol_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AEGIS_SYMBOL_CACHE", raising=False)
    path = resolve_symbol_path(None)
    assert "symbols" in str(path).lower()


def test_resolve_symbol_path_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AEGIS_SYMBOL_CACHE", "/tmp/mysyms")
    assert resolve_symbol_path(None) == Path("/tmp/mysyms")


# ---------------------------------------------------------------------------
# WinDbgJSBackend — callback bridge unit tests (real sockets, no subprocess)
# ---------------------------------------------------------------------------


def test_callback_bridge_assigns_ephemeral_port() -> None:
    """_CallbackBridge must bind to an OS-assigned non-zero port."""
    with _CallbackBridge(callback_timeout=2) as bridge:
        assert bridge.port > 0
        assert bridge.port < 65536


def test_callback_bridge_receives_payload() -> None:
    """A POST to the bridge port should be returned by wait_for_payload."""
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


def test_callback_bridge_per_instance_queue_isolation() -> None:
    """Two simultaneous bridges must not receive each other's payloads."""
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


def test_callback_bridge_timeout_raises() -> None:
    with _CallbackBridge(callback_timeout=0) as bridge:
        assert bridge.port > 0
        with pytest.raises(DebugExtractionError, match="Timed out"):
            bridge.wait_for_payload()


# ---------------------------------------------------------------------------
# WinDbgJSBackend — backend tests (subprocess + bridge mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def js_settings() -> DebugSettings:
    return DebugSettings(engine="windbg_js")


@pytest.fixture
def js_backend(js_settings: DebugSettings) -> WinDbgJSBackend:
    return WinDbgJSBackend(js_settings)


def _mock_bridge(payload: str) -> mock.MagicMock:
    """Return a mock _CallbackBridge instance that yields *payload*."""
    bridge = mock.MagicMock(spec=_CallbackBridge)
    bridge.__enter__ = mock.Mock(return_value=bridge)
    bridge.__exit__ = mock.Mock(return_value=None)
    bridge.port = 54321
    bridge.wait_for_payload.return_value = payload
    return bridge


_JS_PROVIDER_STDOUT = "Loaded extension DLL JsProvider.dll\nReady.\n"
_BRIDGE_PATH = "aegis_swr.backends.debug.windbg_js_worker._CallbackBridge"


def test_windbg_js_parses_ddm_json(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    payload = (FIXTURES / "sample_windbg_js_payload.json").read_text()
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge(payload)),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
    ):
        result = js_backend.extract(_source(dump_path), None)

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


def test_windbg_js_command_uses_scriptload(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    cmd = js_backend._js_command(_source(dump_path), None, "/tmp/test.js")
    assert cmd[0] == "cdb.exe"
    assert "-z" in cmd
    joined = " ".join(cmd)
    assert ".scriptload" in joined
    assert "test.js" in joined


def test_windbg_js_raises_on_missing_jsprovider(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    payload = (FIXTURES / "sample_windbg_js_payload.json").read_text()
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge(payload)),
        mock.patch(_RUN, return_value=_proc("CDB version 10.0\nReady.\n")),
        pytest.raises(DebugExtractionError, match="JsProvider"),
    ):
        js_backend.extract(_source(dump_path), None)


def test_windbg_js_raises_on_callback_timeout(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    bridge = _mock_bridge("")
    bridge.wait_for_payload.side_effect = DebugExtractionError("Timed out")
    with (
        mock.patch(_BRIDGE_PATH, return_value=bridge),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
        pytest.raises(DebugExtractionError, match="Timed out"),
    ):
        js_backend.extract(_source(dump_path), None)


def test_windbg_js_missing_asset_raises(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    with (
        mock.patch.object(js_backend, "_asset_path", return_value=Path("/no/such.js")),
        pytest.raises(DebugExtractionError, match="asset not found"),
    ):
        js_backend.extract(_source(dump_path), None)


def test_windbg_js_parses_invalid_json_raises(
    js_backend: WinDbgJSBackend, dump_path: str
) -> None:
    with (
        mock.patch(_BRIDGE_PATH, return_value=_mock_bridge("not json {")),
        mock.patch(_RUN, return_value=_proc(_JS_PROVIDER_STDOUT)),
        pytest.raises(DebugExtractionError, match="invalid JSON"),
    ):
        js_backend.extract(_source(dump_path), None)


def test_windbg_js_inject_params_substitutes_all_tokens(
    js_backend: WinDbgJSBackend,
) -> None:
    template = "URL=__CALLBACK_URL__ F=__MAX_FAULTING_FRAMES__ O=__MAX_OTHER_FRAMES__"
    result = js_backend._inject_params(template, port=12345)
    assert "127.0.0.1:12345" in result
    assert "__CALLBACK_URL__" not in result
    assert "__MAX_FAULTING_FRAMES__" not in result
    assert "__MAX_OTHER_FRAMES__" not in result


# ---------------------------------------------------------------------------
# Factory — Windows engine selection
# ---------------------------------------------------------------------------


def test_factory_returns_windbg_js_when_engine_forced(js_settings: DebugSettings) -> None:
    backend = create_debug_backend(js_settings, platform="win32")
    assert isinstance(backend, WinDbgJSBackend)


def test_factory_returns_cdb_when_engine_forced() -> None:
    backend = create_debug_backend(DebugSettings(engine="cdb"), platform="win32")
    assert isinstance(backend, CdbBackend)


def test_factory_auto_returns_cdb_when_js_unavailable() -> None:
    with mock.patch(_JS_AVAIL, return_value=False):
        backend = create_debug_backend(DebugSettings(engine="auto"), platform="win32")
    assert isinstance(backend, CdbBackend)


def test_factory_auto_returns_windbg_js_when_available() -> None:
    with mock.patch(_JS_AVAIL, return_value=True):
        backend = create_debug_backend(DebugSettings(engine="auto"), platform="win32")
    assert isinstance(backend, WinDbgJSBackend)
