"""Tests for CLI helpers: SensitiveFilter, _validate_dump_path, check_environment"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from wincrash_analyzer.cli import _validate_dump_path, create_parser
from wincrash_analyzer.core.crash_app import SensitiveFilter, CrashApp


# ---------------------------------------------------------------------------
# SensitiveFilter
# ---------------------------------------------------------------------------


class TestSensitiveFilter:
    """Verify that API key values are redacted from log records"""

    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_gemini_key_redacted(self):
        f = SensitiveFilter()
        record = self._make_record("GEMINI_API_KEY=supersecret123")
        f.filter(record)
        assert "supersecret123" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_openai_key_redacted(self):
        f = SensitiveFilter()
        record = self._make_record("OPENAI_API_KEY=sk-abcdef")
        f.filter(record)
        assert "sk-abcdef" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_non_sensitive_message_unchanged(self):
        f = SensitiveFilter()
        record = self._make_record("Starting debugger extraction")
        f.filter(record)
        assert record.msg == "Starting debugger extraction"

    def test_filter_returns_true(self):
        """filter() must always return True so the record is not dropped"""
        f = SensitiveFilter()
        record = self._make_record("some message")
        assert f.filter(record) is True


# ---------------------------------------------------------------------------
# _validate_dump_path
# ---------------------------------------------------------------------------


class TestValidateDumpPath:
    """Verify that non-.dmp paths are rejected"""

    def test_valid_dmp_extension_passes(self):
        assert _validate_dump_path("crash.dmp") == "crash.dmp"

    def test_valid_dmp_extension_uppercase_passes(self):
        assert _validate_dump_path("crash.DMP") == "crash.DMP"

    def test_txt_extension_raises(self):
        with pytest.raises(argparse.ArgumentTypeError, match=r"\.dmp"):
            _validate_dump_path("crash.txt")

    def test_no_extension_raises(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _validate_dump_path("crash")

    def test_dmp_in_directory_path_passes(self):
        assert _validate_dump_path("C:\\Crashes\\app.dmp") == "C:\\Crashes\\app.dmp"


# ---------------------------------------------------------------------------
# check_environment
# ---------------------------------------------------------------------------


class TestCheckEnvironment:
    """Verify the pre-flight environment check"""

    @pytest.fixture
    def app(self):
        return CrashApp(None)

    def test_returns_false_when_cdb_missing(self, app):
        with patch("shutil.which", return_value=None):
            result = app.check_environment()
        assert result is False

    def test_returns_true_when_cdb_found(self, app):
        with (
            patch("shutil.which", return_value="/usr/bin/cdb.exe"),
            patch("subprocess.run") as mock_run,
            patch.dict(os.environ, {"GEMINI_API_KEY": "key"}),
        ):
            mock_run.return_value.returncode = 0
            result = app.check_environment()
        assert result is True

    def test_returns_false_when_cdb_access_denied(self, caplog, app):
        with (
            patch("shutil.which", return_value="C:\\Users\\user\\AppData\\Local\\Microsoft\\WindowsApps\\cdb.exe"),
            patch("subprocess.run", side_effect=PermissionError("Access is denied")),
            caplog.at_level(logging.ERROR, logger="wincrash_analyzer.crash_app"),
        ):
            result = app.check_environment()
        assert result is False
        assert "Access is denied" in caplog.text
        assert "WinDbg Preview" in caplog.text
        assert "--cdb-path" in caplog.text

    def test_custom_cdb_path_used(self, app):
        custom_path = "C:\\Debuggers\\cdb.exe"
        with (
            patch("shutil.which", return_value=custom_path),
            patch("subprocess.run") as mock_run,
            patch.dict(os.environ, {"GEMINI_API_KEY": "key"}),
        ):
            mock_run.return_value.returncode = 0
            result = app.check_environment(cdb_path=custom_path)
            assert result is True
            mock_run.assert_called_once()
            # Ensure the first arg to subprocess.run is our custom path
            assert mock_run.call_args[0][0][0] == custom_path

    def test_warns_when_no_api_keys(self, caplog, app):
        with (
            patch("shutil.which", return_value="/usr/bin/cdb.exe"),
            patch("subprocess.run") as mock_run,
            patch.dict(os.environ, {}, clear=True),
            caplog.at_level(logging.INFO, logger="wincrash_analyzer.crash_app"),
        ):
            mock_run.return_value.returncode = 0
            # Ensure keys are not set
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ.pop("OPENAI_API_KEY", None)
            result = app.check_environment()
        assert result is True
        assert any("API keys" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# e2e_mock_payload.json asset
# ---------------------------------------------------------------------------


def test_e2e_mock_payload_is_valid_json():
    """The e2e mock payload asset must be valid, well-formed JSON"""
    asset_path = Path(__file__).parent / "assets" / "e2e_mock_payload.json"
    assert asset_path.exists(), "e2e_mock_payload.json is missing from tests/assets/"
    data = json.loads(asset_path.read_text())
    assert "dump" in data
    assert "raw_stack" in data
    assert "ai_analysis" in data
    assert "metadata" in data


def test_e2e_mock_payload_contains_expected_fields():
    """Validate specific fields in the e2e mock payload"""
    asset_path = Path(__file__).parent / "assets" / "e2e_mock_payload.json"
    data = json.loads(asset_path.read_text())
    assert data["metadata"]["engine"] in ("cdb", "js")
    assert data["metadata"]["ai_backend"] in ("gemini", "openai")
    assert "0xc0000005" in data["raw_stack"]
    assert "Root Cause" in data["ai_analysis"]


# ---------------------------------------------------------------------------
# CLI Help
# ---------------------------------------------------------------------------


def test_main_help_contains_subparser_options():
    """Verify that the main help message includes options from subparsers"""
    parser, _, _ = create_parser()
    help_text = parser.format_help()
    
    # Check for main parser elements
    assert "WinCrash AI Analyzer" in help_text
    assert "--report-severity" in help_text
    
    # Check for 'analyze' section and its options
    assert "Help for 'analyze' action:" in help_text
    assert "--dump DUMP" in help_text
    assert "--engine {cdb,js}" in help_text
    assert "--ai {gemini,openai}" in help_text
    
    # Check for 'export' section and its options
    assert "Help for 'export' action:" in help_text
    assert "--to-store {filesystem,sqlite}" in help_text
    assert "--to-store-config TO_STORE_CONFIG" in help_text
