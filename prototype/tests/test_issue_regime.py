import pytest
from unittest.mock import MagicMock
from wincrash_analyzer.core.orchestrator import CrashOrchestrator
from wincrash_analyzer.core.data_sources import DumpSource, SymbolSource, SourceCollection, LogSource

def test_release_no_pdb_regime():
    """
    Test the regime where we have a Release crash dump without PDB, 
    no log file, and an assumption text.
    """
    debugger = MagicMock()
    ai = MagicMock()
    store = MagicMock()

    debugger.engine_type = "cdb"
    ai.model_name = "openai"
    
    # Mock a stack trace without symbols (just addresses and module names)
    no_pdb_stack = (
        "EXCEPTION_CODE: (NTSTATUS) 0xc0000005 - Access Violation\n"
        "FAULTING_IP: \n"
        "CrashUi+0x1234\n"
        "STACK_TEXT: \n"
        "00 CrashUi+0x1234\n"
        "01 CrashUi+0x5678\n"
        "02 kernel32!BaseThreadInitThunk+0x14\n"
        "03 ntdll!RtlUserThreadStart+0x21\n"
    )
    debugger.extract.return_value = {
        "raw": no_pdb_stack,
        "exception_code": "0xc0000005",
        "faulting_module": "CrashUi",
        "timestamp": "2026-03-24 21:20:00"
    }
    
    ai.analyze.return_value = "AI Analysis based on assumption"

    orch = CrashOrchestrator(debugger=debugger, ai=ai, store=store)
    
    # Sources without symbols and logs
    sources = SourceCollection(
        dump=DumpSource("CrashUi.exe.12188.dmp"), 
        symbols=None, 
        logs=None
    )
    
    assumption = "There's probability that the crash was deliberately injected. Check this theory"
    
    result = orch.process(sources, assumption=assumption)

    # Verify AI call
    ai.analyze.assert_called_once()
    args, kwargs = ai.analyze.call_args
    
    crash_data = args[0]
    passed_assumption = kwargs.get('assumption')
    
    assert "STACK TRACE:" in crash_data
    assert "CrashUi+0x1234" in crash_data
    assert passed_assumption == assumption
    assert result == "AI Analysis based on assumption"
    
    # Verify report persistence
    store.save.assert_called_once()
    saved_record = store.save.call_args[0][0]
    assert saved_record["faulting_module"] == "CrashUi"
    assert saved_record["exception_code"] == "0xc0000005"
