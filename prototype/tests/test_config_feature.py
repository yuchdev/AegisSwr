import json
import os
import sys
from unittest.mock import patch, MagicMock
import pytest
from wincrash_analyzer.cli import main
from wincrash_analyzer.config import CONFIG_DEFAULT_PATH

def test_save_config(tmp_path, capsys):
    """Test that --save-config creates a config file and exits"""
    config_file = tmp_path / "test_config.json"
    
    # Mock CONFIG_DEFAULT_PATH to point to our temp file
    with patch("wincrash_analyzer.cli.CONFIG_DEFAULT_PATH", str(config_file)), \
         patch("wincrash_analyzer.core.crash_app.CONFIG_DEFAULT_PATH", str(config_file)), \
         patch("wincrash_analyzer.config.app_config.CONFIG_DEFAULT_PATH", str(config_file)), \
         patch("sys.argv", ["wincrash-analyzer", "--save-config", "analyze", "--engine", "js"]), \
         pytest.raises(SystemExit) as e:
        main()
    
    assert e.value.code == 0
    assert config_file.exists()
    
    with open(config_file, "r") as f:
        config = json.load(f)
    
    assert config["analyze"]["engine"] == "js"
    # Ensure save_config and config_file are NOT in the saved config
    assert "save_config" not in config
    assert "config_file" not in config

def test_config_file_loading(tmp_path):
    """Test that --config-file loads settings and ignores other CLI args"""
    config_file = tmp_path / "load_config.json"
    config_data = {
        "action": "analyze",
        "analyze": {
            "engine": "js",
            "ai": "openai",
            "dump": "test.dmp",
            "sym": "C:\\Symbols"
        },
        "report_severity": "DEBUG"
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
    
    # We also need to mock setup_logging to avoid side effects
    with patch("sys.argv", ["wincrash-analyzer", "--config-file", str(config_file), "analyze", "--engine", "cdb"]), \
         patch("wincrash_analyzer.core.crash_app.CrashApp._check_cdb", return_value="cdb.exe"), \
         patch("wincrash_analyzer.core.crash_app.run_analyze") as mock_run:
        
        # We also need to mock setup_logging to avoid side effects
        with patch("wincrash_analyzer.core.crash_app.CrashApp.setup_logging"):
            main()
            
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.engine == "js"
        assert args.ai == "openai"
        assert args.report_severity == "DEBUG"
        assert args.dump == "test.dmp"

def test_default_config_loading(tmp_path):
    """Test that default config file is loaded if it exists"""
    config_file = tmp_path / "default_config.json"
    config_data = {
        "action": "analyze",
        "analyze": {
            "engine": "js",
            "dump": "default.dmp",
            "sym": "C:\\Symbols"
        }
    }
    with open(config_file, "w") as f:
        json.dump(config_data, f)
        
    with patch("wincrash_analyzer.core.crash_app.read_config", return_value=config_data), \
         patch("sys.argv", ["wincrash-analyzer", "analyze"]), \
         patch("wincrash_analyzer.core.crash_app.CrashApp._check_cdb", return_value="cdb.exe"), \
         patch("wincrash_analyzer.core.crash_app.run_analyze") as mock_run:
        
        with patch("wincrash_analyzer.core.crash_app.CrashApp.setup_logging"):
            main()
            
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.engine == "js"
        assert args.dump == "default.dmp"

def test_flat_config_loading(tmp_path):
    """Test that a flat config (no 'analyze'/'export' keys) is loaded correctly"""
    config_data = {
        "action": "analyze",
        "engine": "js",
        "dump": "flat.dmp",
        "sym": "C:\\Symbols"
    }
    
    with patch("wincrash_analyzer.core.crash_app.read_config", return_value=config_data), \
         patch("sys.argv", ["wincrash-analyzer", "analyze"]), \
         patch("wincrash_analyzer.core.crash_app.CrashApp._check_cdb", return_value="cdb.exe"), \
         patch("wincrash_analyzer.core.crash_app.run_analyze") as mock_run:
        
        with patch("wincrash_analyzer.core.crash_app.CrashApp.setup_logging"):
            main()
            
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args.engine == "js"
        assert args.dump == "flat.dmp"
        assert args.sym == "C:\\Symbols"

def test_config_file_not_found(capsys):
    """Test that an error is raised if the specified config file is missing"""
    with patch("sys.argv", ["wincrash-analyzer", "--config-file", "nonexistent.json"]), \
         pytest.raises(SystemExit):
        main()
    
    # argparse error output is usually to stderr
    # but parser.error calls sys.exit(2)
