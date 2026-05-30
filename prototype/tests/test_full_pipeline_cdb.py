"""Integration tests: CDB debug backend → SQLite storage pipeline.

These tests use a mock-assisted approach: the CDB subprocess call is patched
so the suite runs without a Windows Debugging Tools installation.  The AI
layer is replaced with a ``MagicMock`` to avoid live API calls.  The SQLite
storage backend is wired up against a temporary file so persistence logic is
exercised for real.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from wincrash_analyzer.backends.store.sqlite import SQLiteBackend
from wincrash_analyzer.core.exceptions import AIBackendError
from wincrash_analyzer.core.orchestrator import CrashOrchestrator
from wincrash_analyzer.core.data_sources import DumpSource, SymbolSource, SourceCollection

# ---------------------------------------------------------------------------
# Asset paths
# ---------------------------------------------------------------------------

ASSETS_DIR = Path(__file__).parent / "assets"
ACCESS_VIOLATION_ASSET = ASSETS_DIR / "access_violation_cdb.txt"
CORRUPT_DUMP_ASSET = ASSETS_DIR / "corrupt_mini.dmp"


def _access_violation_output() -> str:
    return ACCESS_VIOLATION_ASSET.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_dump_session(tmp_path):
    """Create a temporary directory with a dummy .dmp file and symbol folder."""
    dump_file = tmp_path / "crash.dmp"
    dump_file.write_bytes(b"\x00" * 64)
    sym_dir = tmp_path / "symbols"
    sym_dir.mkdir()
    return dump_file, sym_dir, tmp_path


# ---------------------------------------------------------------------------
# Asset sanity checks
# ---------------------------------------------------------------------------


def test_access_violation_asset_exists():
    """The access_violation_cdb.txt asset must be present."""
    assert ACCESS_VIOLATION_ASSET.exists(), (
        f"Missing asset: {ACCESS_VIOLATION_ASSET}"
    )


def test_access_violation_asset_contains_exception_markers():
    """The asset must contain the key markers expected by the CDB parser."""
    raw = _access_violation_output()
    assert "Exception Analysis" in raw
    assert "EXCEPTION_CODE" in raw
    assert "0xc0000005" in raw
    assert "STACK_TEXT" in raw


def test_access_violation_asset_contains_cpp_template_chars():
    """The asset must include C++ template characters to exercise escaping."""
    raw = _access_violation_output()
    assert "<" in raw
    assert ">" in raw


def test_corrupt_dump_asset_exists():
    """The corrupt_mini.dmp asset must be present."""
    assert CORRUPT_DUMP_ASSET.exists(), f"Missing asset: {CORRUPT_DUMP_ASSET}"


def test_corrupt_dump_asset_has_mdmp_header():
    """The corrupt_mini.dmp asset must begin with the MDMP magic signature."""
    header = CORRUPT_DUMP_ASSET.read_bytes()[:4]
    assert header == b"MDMP", f"Expected MDMP header, got {header!r}"


# ---------------------------------------------------------------------------
# Pipeline integration tests
# ---------------------------------------------------------------------------


def test_cdb_to_sqlite_pipeline(mock_dump_session, tmp_path):
    """Verify that the CDB-to-SQLite pipeline persists exactly one record."""
    dump_file, sym_dir, _ = mock_dump_session
    db_path = str(tmp_path / "crash_reports.db")

    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "## RCA\nAccess violation summary."
    mock_ai.model_name = "gemini"

    mock_debugger = MagicMock()
    mock_debugger.extract.return_value = {"raw": _access_violation_output()}
    mock_debugger.engine_type = "cdb"

    store = SQLiteBackend(db_path=db_path)
    orch = CrashOrchestrator(debugger=mock_debugger, ai=mock_ai, store=store)
    sources = SourceCollection(dump=DumpSource(str(dump_file)), symbols=SymbolSource(str(sym_dir)))
    orch.process(sources)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM crash_reports")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 1


def test_state_machine_transitions_to_completed(mock_dump_session, tmp_path):
    """The orchestrator must reach the COMPLETED state on a successful run."""
    dump_file, sym_dir, _ = mock_dump_session
    db_path = str(tmp_path / "crash_reports.db")

    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "## Summary\nRCA: null pointer dereference."
    mock_ai.model_name = "gemini"

    mock_debugger = MagicMock()
    mock_debugger.extract.return_value = {
        "raw": "Exception Analysis\nSTACK_TEXT: ntdll!RtlUserThreadStart+0x21\n"
    }
    mock_debugger.engine_type = "cdb"

    store = SQLiteBackend(db_path=db_path)
    orch = CrashOrchestrator(debugger=mock_debugger, ai=mock_ai, store=store)
    assert orch.state == "IDLE"
    sources = SourceCollection(dump=DumpSource(str(dump_file)), symbols=SymbolSource(str(sym_dir)))
    orch.process(sources)
    assert orch.state == "COMPLETED"


def test_cpp_template_chars_forwarded_to_ai_unescaped(mock_dump_session, tmp_path):
    """Special characters (< > &&) in C++ templates must reach the AI verbatim."""
    dump_file, sym_dir, _ = mock_dump_session
    db_path = str(tmp_path / "crash_reports.db")

    raw_stack = (
        "Exception Analysis\n"
        "SampleApp!std::vector<int>::push_back+0x3f\n"
        "SampleApp!DataProcessor::process<std::string>+0x7c\n"
        "SampleApp!operator new(unsigned __int64)+0x28\n"
        "STACK_TEXT:\n"
        "ntdll!RtlUserThreadStart+0x21\n"
    )

    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "## RCA\nC++ template STL issue."
    mock_ai.model_name = "gemini"

    mock_debugger = MagicMock()
    mock_debugger.extract.return_value = {"raw": raw_stack}
    mock_debugger.engine_type = "cdb"

    store = SQLiteBackend(db_path=db_path)
    orch = CrashOrchestrator(debugger=mock_debugger, ai=mock_ai, store=store)
    sources = SourceCollection(dump=DumpSource(str(dump_file)), symbols=SymbolSource(str(sym_dir)))
    orch.process(sources)

    sanitized_arg = mock_ai.analyze.call_args[0][0]
    assert "<int>" in sanitized_arg
    assert "<std::string>" in sanitized_arg


def test_ai_backend_error_still_persists_raw_data(mock_dump_session, tmp_path):
    """If the AI stage raises AIBackendError, raw extraction data is still saved."""
    dump_file, sym_dir, _ = mock_dump_session
    db_path = str(tmp_path / "crash_reports.db")

    mock_ai = MagicMock()
    mock_ai.analyze.side_effect = AIBackendError("API timeout after 10 s")
    mock_ai.model_name = "gemini"

    mock_debugger = MagicMock()
    mock_debugger.extract.return_value = {
        "raw": "Exception Analysis\nSTACK_TEXT: ntdll!RtlUserThreadStart+0x21\n"
    }
    mock_debugger.engine_type = "cdb"

    store = SQLiteBackend(db_path=db_path)
    orch = CrashOrchestrator(debugger=mock_debugger, ai=mock_ai, store=store)

    sources = SourceCollection(dump=DumpSource(str(dump_file)), symbols=SymbolSource(str(sym_dir)))
    with pytest.raises(AIBackendError):
        orch.process(sources)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM crash_reports")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 1


def test_massive_trace_pipeline_does_not_raise(mock_dump_session, tmp_path):
    """A very large stack trace is processed without error; storage truncates it."""
    dump_file, sym_dir, _ = mock_dump_session
    db_path = str(tmp_path / "crash_reports.db")

    frame_line = "ntdll!RtlAllocateHeap+0x1234  kernel32!BaseThreadInitThunk+0x14\n"
    massive_trace = f"Exception Analysis\nSTACK_TEXT:\n{frame_line * 5_000}"

    mock_ai = MagicMock()
    mock_ai.analyze.return_value = "## RCA\nMemory exhaustion."
    mock_ai.model_name = "gemini"

    mock_debugger = MagicMock()
    mock_debugger.extract.return_value = {"raw": massive_trace}
    mock_debugger.engine_type = "cdb"

    store = SQLiteBackend(db_path=db_path)
    orch = CrashOrchestrator(debugger=mock_debugger, ai=mock_ai, store=store)
    sources = SourceCollection(dump=DumpSource(str(dump_file)), symbols=SymbolSource(str(sym_dir)))
    orch.process(sources)

    rows = store.load_all()
    assert len(rows) == 1
    # SQLiteBackend stores the whole JSON, truncation is no longer applied in saving
    assert "raw_stack" in rows[0]
