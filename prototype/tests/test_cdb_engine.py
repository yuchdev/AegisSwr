"""Tests for the CDB debugger backend (cdb.py)"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wincrash_analyzer.backends.debug.cdb import CDBBackend
from wincrash_analyzer.core.exceptions import DebuggerEngineError, DebuggerNotFoundError

ASSETS_DIR = Path(__file__).parent / "assets"
RAW_CDB_OUTPUT = ASSETS_DIR / "raw_cdb_output.txt"


# ---------------------------------------------------------------------------
# Asset-based helpers
# ---------------------------------------------------------------------------

def _raw_output() -> str:
    return RAW_CDB_OUTPUT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Regex / noise-reduction tests
# ---------------------------------------------------------------------------

class TestParseRawOutput:
    """Verify the _parse_raw_output regex parser"""

    def setup_method(self):
        self.backend = CDBBackend()

    def test_asset_file_exists(self):
        assert RAW_CDB_OUTPUT.exists(), "tests/assets/raw_cdb_output.txt is missing"

    def test_asset_contains_fifty_file_not_found_lines(self):
        raw = _raw_output()
        count = raw.count("file not found")
        assert count == 50, f"Expected 50 'file not found' lines, found {count}"

    def test_file_not_found_lines_are_removed(self):
        raw = _raw_output()
        result = self.backend._parse_raw_output(raw)
        assert "file not found" not in result

    def test_stack_text_is_preserved(self):
        raw = _raw_output()
        result = self.backend._parse_raw_output(raw)
        assert "STACK_TEXT" in result

    def test_exception_record_is_preserved(self):
        raw = _raw_output()
        result = self.backend._parse_raw_output(raw)
        assert "EXCEPTION_CODE" in result

    def test_fallback_returns_first_10k_chars_when_no_match(self):
        raw = "x" * 20000
        result = self.backend._parse_raw_output(raw)
        assert len(result) == 10000

    def test_empty_input_returns_empty_fallback(self):
        result = self.backend._parse_raw_output("")
        assert result == ""


# ---------------------------------------------------------------------------
# Timeout test
# ---------------------------------------------------------------------------

class TestExtractTimeout:
    """Verify that a long-running CDB process raises DebuggerEngineError"""

    def test_timeout_raises_debugger_engine_error(self, tmp_path):
        dump_file = tmp_path / "test.dmp"
        dump_file.write_bytes(b"\x00")  # minimal readable file

        backend = CDBBackend()

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="cdb.exe", timeout=300)):
            with pytest.raises(DebuggerEngineError, match="timed out"):
                backend.extract(str(dump_file), "C:\\Symbols")


# ---------------------------------------------------------------------------
# FileNotFoundError (cdb.exe missing) and PermissionError (Access Denied) tests
# ---------------------------------------------------------------------------

class TestExtractCdbErrors:
    """Verify that cdb.exe errors raise appropriate exceptions"""

    def test_missing_cdb_raises_debugger_not_found_error(self, tmp_path):
        dump_file = tmp_path / "test.dmp"
        dump_file.write_bytes(b"\x00")

        backend = CDBBackend()

        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(DebuggerNotFoundError, match="'cdb.exe' not found"):
                backend.extract(str(dump_file), "C:\\Symbols")

    def test_access_denied_raises_debugger_engine_error(self, tmp_path):
        dump_file = tmp_path / "test.dmp"
        dump_file.write_bytes(b"\x00")

        custom_path = "C:\\Tools\\cdb.exe"
        backend = CDBBackend(cdb_path=custom_path)

        with patch("subprocess.run", side_effect=PermissionError("Access is denied")):
            with pytest.raises(DebuggerEngineError, match="Access Denied"):
                backend.extract(str(dump_file), "C:\\Symbols")


# ---------------------------------------------------------------------------
# Unreadable dump file test
# ---------------------------------------------------------------------------

class TestExtractUnreadableDump:
    """Verify that an unreadable dump raises DebuggerEngineError before spawning"""

    def test_unreadable_dump_raises_before_subprocess(self, tmp_path):
        dump_file = tmp_path / "locked.dmp"
        dump_file.write_bytes(b"\x00")

        backend = CDBBackend()

        with patch("os.access", return_value=False):
            with patch("subprocess.run") as mock_run:
                with pytest.raises(DebuggerEngineError, match="not readable"):
                    backend.extract(str(dump_file), "C:\\Symbols")
                mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Successful extraction (mocked subprocess) test
# ---------------------------------------------------------------------------

class TestExtractSuccess:
    """Verify happy-path extraction with a mocked subprocess"""

    def test_successful_extraction_returns_filtered_output(self, tmp_path):
        dump_file = tmp_path / "test.dmp"
        dump_file.write_bytes(b"\x00")

        raw = _raw_output()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = raw

        backend = CDBBackend()

        with patch("subprocess.run", return_value=mock_result):
            result = backend.extract(str(dump_file), "C:\\Symbols")

        assert "raw" in result
        assert "STACK_TEXT" in result["raw"]
        assert "file not found" not in result["raw"]
        assert result["exception_code"] == "0xc0000005"
        assert result["faulting_module"] == "MyApplication"

    def test_nonzero_returncode_still_returns_output(self, tmp_path):
        dump_file = tmp_path / "test.dmp"
        dump_file.write_bytes(b"\x00")

        raw = _raw_output()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = raw

        backend = CDBBackend()

        with patch("subprocess.run", return_value=mock_result):
            result = backend.extract(str(dump_file), "C:\\Symbols")

        # Output is still returned even when CDB exits non-zero
        assert isinstance(result, dict)
        assert "raw" in result
        assert len(result["raw"]) > 0
