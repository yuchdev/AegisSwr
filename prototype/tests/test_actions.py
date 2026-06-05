"""Tests for wincrash_analyzer actions"""
import pytest
from unittest.mock import MagicMock, patch
from argparse import Namespace

from wincrash_analyzer.actions.analyze import run_analyze
from wincrash_analyzer.actions.export import run_export

class TestActions:
    
    @patch("wincrash_analyzer.actions.analyze.create_debug_backend")
    @patch("wincrash_analyzer.actions.analyze.create_ai_backend")
    @patch("wincrash_analyzer.actions.analyze.create_storage_backend")
    @patch("wincrash_analyzer.actions.analyze.Orchestrator")
    def test_run_analyze(self, mock_orchestrator_cls, mock_create_store, mock_create_ai, mock_create_debug):
        # Setup
        mock_orchestrator = MagicMock()
        mock_orchestrator_cls.return_value = mock_orchestrator
        mock_orchestrator.run.return_value = "Mock Diagnosis"
        
        args = Namespace(
            engine="cdb",
            ai="gemini",
            store="filesystem",
            store_config="config",
            dump="crash.dmp",
            sym="symbols",
            log_source=None,
            analyze_history=False
        )
        resolved_cdb = "cdb.exe"
        
        # Execute
        with patch("wincrash_analyzer.actions.analyze.console.print"):
            run_analyze(args, resolved_cdb)
        
        # Verify
        mock_create_debug.assert_called_once_with("cdb", cdb_path=resolved_cdb)
        mock_create_ai.assert_called_once_with("gemini")
        mock_create_store.assert_called_once_with("filesystem", "config")
        # sources = SourceCollection(...)
        mock_orchestrator.run.assert_called_once()
        call_args = mock_orchestrator.run.call_args[0][0]
        assert call_args.dump.path == "crash.dmp"
        assert call_args.symbols.path == "symbols"
        assert call_args.logs is None

    @patch("wincrash_analyzer.actions.export.create_storage_backend")
    def test_run_export(self, mock_create_store):
        # Setup
        mock_source = MagicMock()
        mock_dest = MagicMock()
        mock_create_store.side_effect = [mock_source, mock_dest]
        
        record1 = {"report_id": "1", "data": "foo"}
        record2 = {"report_id": "2", "data": "bar"}
        mock_source.load_all.return_value = [record1, record2]
        mock_dest.save.return_value = True
        
        args = Namespace(
            store="sqlite",
            store_config="source.sqlite",
            to_store="filesystem",
            to_store_config="dest_dir"
        )
        
        # Execute
        with patch("wincrash_analyzer.actions.export.console.print"):
            run_export(args)
        
        # Verify
        assert mock_create_store.call_count == 2
        mock_source.load_all.assert_called_once()
        assert mock_dest.save.call_count == 2
        mock_dest.save.assert_any_call(record1)
        mock_dest.save.assert_any_call(record2)

    @patch("wincrash_analyzer.actions.export.create_storage_backend")
    def test_run_export_failure(self, mock_create_store):
        # Setup
        mock_source = MagicMock()
        mock_dest = MagicMock()
        mock_create_store.side_effect = [mock_source, mock_dest]
        
        record1 = {"report_id": "1"}
        mock_source.load_all.return_value = [record1]
        mock_dest.save.return_value = False
        
        args = Namespace(
            store="sqlite",
            store_config="source.sqlite",
            to_store="filesystem",
            to_store_config="dest_dir"
        )
        
        # Execute
        with patch("wincrash_analyzer.actions.export.console.print") as mock_print:
            run_export(args)
        
        # Verify
        mock_dest.save.assert_called_once_with(record1)
        # Check that we reported 0 successful
        args, kwargs = mock_print.call_args
        assert "0 successful" in args[0]
