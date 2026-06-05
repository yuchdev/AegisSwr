"""Unit tests for CrashOrchestrator (orchestrator.py) and exceptions.py"""
import pytest
from unittest.mock import MagicMock

from wincrash_analyzer.core.orchestrator import CrashOrchestrator
from wincrash_analyzer.core.data_sources import DumpSource, SymbolSource, SourceCollection
from wincrash_analyzer.core.exceptions import (
    AIBackendError,
    DebuggerError,
    StorageBackendError,
    WinCrashError,
    SymbolMismatchError,
    ProviderCallbackError,
)


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------


def test_wincrasherror_has_code():
    err = WinCrashError("boom", code=503)
    assert err.code == 503
    assert str(err) == "boom"


def test_wincrasherror_default_code():
    err = WinCrashError("boom")
    assert err.code == 500


def test_debugger_error_is_wincrasherror():
    err = DebuggerError("cdb failed")
    assert isinstance(err, WinCrashError)


def test_symbol_mismatch_is_debugger_error():
    err = SymbolMismatchError("guid mismatch")
    assert isinstance(err, DebuggerError)


def test_provider_callback_error_is_wincrasherror():
    err = ProviderCallbackError("no callback")
    assert isinstance(err, WinCrashError)


def test_storage_backend_error_is_wincrasherror():
    err = StorageBackendError("disk full")
    assert isinstance(err, WinCrashError)


# ---------------------------------------------------------------------------
# Mocked pipeline test
# ---------------------------------------------------------------------------


def test_mocked_pipeline_passes_raw_data_to_ai():
    """Debugger output containing 'Access Violation' is forwarded to the AI"""
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "gemini"
    debugger.extract.return_value = {
        "raw": (
            "EXCEPTION_CODE: (HRESULT) 0xc0000005 (3221225477) - Access Violation\n"
            "STACK_TEXT:\n"
            "00 ntdll!RtlUserThreadStart\n"
            "01 kernel32!BaseThreadInitThunk\n"
        )
    }
    ai.analyze.return_value = "## Root Cause\nNull pointer dereference."

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    sources = SourceCollection(dump=DumpSource("crash.dmp"), symbols=SymbolSource("C:\\symbols"))
    result = orch.process(sources)

    # The text passed to AI must contain the original keyword.
    call_arg = ai.analyze.call_args[0][0]
    assert "Access Violation" in call_arg
    assert result == "## Root Cause\nNull pointer dereference."
    assert orch.state == "COMPLETED"


# ---------------------------------------------------------------------------
# Exception bubble test
# ---------------------------------------------------------------------------


def test_storage_oserror_raises_storage_backend_error():
    """An OSError from the storage backend is wrapped in StorageBackendError"""
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "gemini"
    debugger.extract.return_value = {"raw": "stack trace"}
    ai.analyze.return_value = "diagnosis"
    store.save.side_effect = OSError("No space left on device")

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    sources = SourceCollection(dump=DumpSource("crash.dmp"), symbols=SymbolSource("C:\\symbols"))
    with pytest.raises(StorageBackendError):
        orch.process(sources)


# ---------------------------------------------------------------------------
# Graceful degradation: AI failure still persists raw data
# ---------------------------------------------------------------------------


def test_ai_failure_persists_raw_data():
    """When the AI backend fails, raw data is still saved to the store"""
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "gemini"
    debugger.extract.return_value = {"raw": "raw stack trace"}
    ai.analyze.side_effect = AIBackendError("rate limit exceeded")

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    sources = SourceCollection(dump=DumpSource("crash.dmp"), symbols=SymbolSource("C:\\symbols"))
    with pytest.raises(AIBackendError):
        orch.process(sources)

    # Store must have been called with the raw data.
    store.save.assert_called_once()
    saved = store.save.call_args[0][0]
    assert saved["raw_stack"] == ["raw stack trace"]
    assert saved["ai_analysis"] == "AI Analysis Unavailable"


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


def test_sanitize_strips_fill_patterns():
    """Hex fill patterns like 0xCCCCCCCC are stripped before AI inference"""
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "gemini"
    debugger.extract.return_value = {
        "raw": "frame 00: 0xCCCCCCCC  Access Violation  0xcccccccc fill"
    }
    ai.analyze.return_value = "analysis"

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    sources = SourceCollection(dump=DumpSource("crash.dmp"), symbols=SymbolSource("C:\\symbols"))
    orch.process(sources)

    sanitized = ai.analyze.call_args[0][0]
    assert "0xCCCCCCCC" not in sanitized
    assert "0xcccccccc" not in sanitized
    assert "Access Violation" in sanitized


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_state_is_completed_after_successful_run():
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "gemini"
    debugger.extract.return_value = {"raw": "trace"}
    ai.analyze.return_value = "result"

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    assert orch.state == "IDLE"
    sources = SourceCollection(dump=DumpSource("crash.dmp"), symbols=SymbolSource("C:\\symbols"))
    orch.process(sources)
    assert orch.state == "COMPLETED"
