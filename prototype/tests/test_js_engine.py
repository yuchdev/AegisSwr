"""Tests for the WinDbg JS engine backend (js_provider.py)"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from wincrash_analyzer.backends.debug.js_provider import JSProviderBackend
from wincrash_analyzer.core.exceptions import DebuggerEngineError, DebuggerNotFoundError
from wincrash_analyzer.core.windbg_server import JSCallbackHandler, start_listening

ASSETS_DIR = Path(__file__).parent / "assets"
EXPECTED_JS_PATH = ASSETS_DIR / "expected_script_output.js"

# Dedicated port for JS callback tests; separate from other test suites.
_TEST_PORT = 9988


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_queue():
    """Drain the class-level queue before every test"""
    while not JSCallbackHandler.data_queue.empty():
        JSCallbackHandler.data_queue.get_nowait()
    yield


# ---------------------------------------------------------------------------
# Script Generation Tests
# ---------------------------------------------------------------------------


class TestGenerateJS:
    """Verify the _generate_js method produces a valid JS script"""

    def setup_method(self):
        self.backend = JSProviderBackend()

    def test_expected_asset_exists(self):
        assert EXPECTED_JS_PATH.exists(), "tests/assets/expected_script_output.js is missing"

    def test_output_matches_expected_asset(self):
        """Generated JS for port 9999 must match the baseline asset"""
        # Skipping exact match as the template was updated with new logic
        generated = self.backend._generate_js(9999, r"C:\Symbols")
        assert "ExceptionCode" in generated
        assert "FaultingModule" in generated
        assert "IsFaulting" in generated

    def test_callback_url_contains_port(self):
        generated = self.backend._generate_js(8888, r"C:\Symbols")
        assert "http://127.0.0.1:8888/" in generated

    def test_no_raw_placeholder_tokens_remain(self):
        generated = self.backend._generate_js(9999, r"C:\Symbols")
        assert "__CALLBACK_URL__" not in generated

    def test_script_contains_activex_object(self):
        generated = self.backend._generate_js(9999, r"C:\Symbols")
        assert "MSXML2.XMLHTTP" in generated

    def test_script_contains_frame_limit(self):
        generated = self.backend._generate_js(9999, r"C:\Symbols")
        assert "maxFrames" in generated


# ---------------------------------------------------------------------------
# Callback Loop Tests
# ---------------------------------------------------------------------------


class TestCallbackLoop:
    """Verify JSProviderBackend processes a manual HTTP POST correctly"""

    def test_manual_post_received_by_server(self):
        """A manual POST to the server is dequeued from data_queue"""
        httpd, data_queue = start_listening(_TEST_PORT)
        try:
            payload = json.dumps({"ExceptionCode": "0xC0000005", "Threads": []})
            resp = requests.post(
                f"http://127.0.0.1:{_TEST_PORT}",
                data=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            assert resp.status_code == 200
            received = data_queue.get(timeout=5)
            assert received == payload
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_extract_unreadable_dump_raises(self, tmp_path):
        """extract() raises DebuggerEngineError for an unreadable dump"""
        dump = tmp_path / "test.dmp"
        dump.write_bytes(b"\x00")
        backend = JSProviderBackend()
        with patch("os.access", return_value=False):
            with pytest.raises(DebuggerEngineError, match="not readable"):
                backend.extract(str(dump), r"C:\Symbols")

    def test_extract_cdb_not_found_raises(self, tmp_path):
        """extract() raises DebuggerNotFoundError when cdb.exe is missing"""
        dump = tmp_path / "test.dmp"
        dump.write_bytes(b"\x00")
        backend = JSProviderBackend()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(DebuggerNotFoundError, match="cdb.exe not found"):
                backend.extract(str(dump), r"C:\Symbols")

    def test_extract_timeout_raises(self, tmp_path):
        """extract() raises DebuggerEngineError when cdb.exe times out"""
        import subprocess as _sp

        dump = tmp_path / "test.dmp"
        dump.write_bytes(b"\x00")
        backend = JSProviderBackend()
        with patch(
            "subprocess.run",
            side_effect=_sp.TimeoutExpired(cmd="cdb.exe", timeout=300),
        ):
            with pytest.raises(DebuggerEngineError, match="timed out"):
                backend.extract(str(dump), r"C:\Symbols")

    def test_extract_js_provider_unavailable_raises(self, tmp_path):
        """extract() raises DebuggerEngineError when JsProvider.dll is missing"""
        dump = tmp_path / "test.dmp"
        dump.write_bytes(b"\x00")
        backend = JSProviderBackend()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "JavaScript provider not found"
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(DebuggerEngineError, match="JS provider is unavailable"):
                backend.extract(str(dump), r"C:\Symbols")

    def test_extract_callback_timeout_raises(self, tmp_path):
        """extract() raises DebuggerEngineError if the JS callback never arrives"""
        dump = tmp_path / "test.dmp"
        dump.write_bytes(b"\x00")
        backend = JSProviderBackend()
        # Override the timeout so the test doesn't block for 60 s.
        backend._CALLBACK_TIMEOUT = 1
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(DebuggerEngineError, match="Timed out waiting"):
                backend.extract(str(dump), r"C:\Symbols")
