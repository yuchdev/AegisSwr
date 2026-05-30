"""Tests for the Orchestrator pipeline."""
from unittest.mock import MagicMock

from wincrash_analyzer.core.orchestrator import Orchestrator
from wincrash_analyzer.core.data_sources import DumpSource, SymbolSource, LogSource, SourceCollection


def test_orchestrator_run_calls_pipeline():
    """Verify that run() calls all three backends in order."""
    debug_backend = MagicMock()
    ai_backend = MagicMock()
    storage_backend = MagicMock()

    debug_backend.engine_type = "mock-engine"
    ai_backend.model_name = "mock-model"
    storage_backend.find_report.return_value = None
    debug_backend.extract.return_value = {
        "raw": "stack trace\nline 2", 
        "exception_code": "0x123", 
        "faulting_module": "test.dll",
        "execution_log": [{"cmd": "test", "output": "log\nline 2"}],
        "raw_stdout": "stdout\nline 2"
    }
    ai_backend.analyze.return_value = "diagnosis"

    orchestrator = Orchestrator(debug_backend, ai_backend, storage_backend)
    sources = SourceCollection(
        dump=DumpSource("crash.dmp"),
        symbols=SymbolSource("C:\\symbols")
    )
    result = orchestrator.run(sources)

    debug_backend.extract.assert_called_once_with("crash.dmp", "C:\\symbols")
    ai_backend.analyze.assert_called_once_with("STACK TRACE:\nstack trace\nline 2\n\n", history=None, assumption=None)
    
    # Check that storage_backend.save was called with a record containing the expected fields.
    args, _ = storage_backend.save.call_args
    record = args[0]
    import os
    assert record["dump_path"] == os.path.abspath("crash.dmp")
    assert record["ai_analysis"] == "diagnosis"
    assert record["exception_code"] == "0x123"
    assert record["faulting_module"] == "test.dll"
    assert record["engine_type"] == "mock-engine"
    assert record["ai_model"] == "mock-model"
    assert record["raw_stack"] == ["stack trace", "line 2"]
    assert record["raw_stdout"] == ["stdout", "line 2"]
    assert record["execution_log"][0]["output"] == ["log", "line 2"]
    assert "report_id" in record
    assert "timestamp" in record
    
    assert result == "diagnosis"


def test_orchestrator_with_logs(tmp_path):
    """Verify that orchestrator includes logs in the unified context."""
    debug_backend = MagicMock()
    ai_backend = MagicMock()
    storage_backend = MagicMock()

    debug_backend.engine_type = "mock-engine"
    ai_backend.model_name = "mock-model"
    storage_backend.find_report.return_value = None
    
    debug_backend.extract.return_value = {
        "raw": "stack trace",
        "timestamp": "2026-03-23T18:00:00Z"
    }
    ai_backend.analyze.return_value = "diagnosis with logs"

    # Create a dummy log file
    log_file = tmp_path / "app.log"
    log_file.write_text("log line 1\nlog line 2", encoding="utf-8")

    orchestrator = Orchestrator(debug_backend, ai_backend, storage_backend)
    sources = SourceCollection(
        dump=DumpSource("crash.dmp"),
        logs=LogSource(str(log_file))
    )
    
    # Mocking exists because we are using a real tmp path but dump source is fake
    sources.dump.exists = MagicMock(return_value=True)

    result = orchestrator.run(sources)

    # Check that analyze was called with combined context
    called_context = ai_backend.analyze.call_args[0][0]
    assert "STACK TRACE:\nstack trace" in called_context
    assert "APPLICATION LOGS:" in called_context
    assert "log line 1" in called_context
    assert "log line 2" in called_context
    assert result == "diagnosis with logs"
