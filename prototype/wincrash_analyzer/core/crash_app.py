from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Callable

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel

from wincrash_analyzer.config import read_config, save_config, CONFIG_DEFAULT_PATH
from wincrash_analyzer.core.exceptions import DebuggerNotFoundError
from wincrash_analyzer.actions.analyze import run_analyze
from wincrash_analyzer.actions.export import run_export

# ---------------------------------------------------------------------------
# Sensitive-data log filter
# ---------------------------------------------------------------------------

_API_KEY_PATTERN = re.compile(
    r"(GEMINI_API_KEY|OPENAI_API_KEY|api[_-]?key)\s*[=:]\s*\S+",
    re.IGNORECASE,
)


class SensitiveFilter(logging.Filter):
    """
    Replace API key values in log records with ``[REDACTED]``.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log records to redact sensitive API keys.

        @param record: The log record to process.
        @return: Always returns True to allow the record to be logged (after modification).
        """
        record.msg = _API_KEY_PATTERN.sub(r"\1=[REDACTED]", str(record.msg))
        return True


console = Console()


class CrashApp:
    """
    Main application class for WinCrash Analyzer.
    Handles CLI argument parsing, logging setup, environment checks, and action dispatching.
    """

    def __init__(self, parser, analyze_parser=None, export_parser=None):
        """
        Initialize the CrashApp.

        @param parser: The main argparse.ArgumentParser instance.
        @param analyze_parser: The subparser for the 'analyze' action.
        @param export_parser: The subparser for the 'export' action.
        """
        self.parser = parser
        self.analyze_parser = analyze_parser
        self.export_parser = export_parser
        self.args = None
        self.actors: dict[str, Callable[[], None]] = {
            "analyze": self.handle_analyze,
            "export": self.handle_export,
        }

    def setup_logging(self, level: str = "INFO") -> None:
        """
        Configure rich-based logging with sensitive-data filtering.

        @param level: The logging level to set (e.g., "INFO", "DEBUG").
        """
        handler = RichHandler(console=console, show_path=False)
        handler.addFilter(SensitiveFilter())
        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[handler],
        )
        # Also ensure the root logger level is set for libraries using standard logging
        logging.getLogger().setLevel(level)

    def _check_cdb(self, cdb_path: str = "cdb.exe") -> str:
        """
        Verify that cdb.exe is available and executable on the system.

        @param cdb_path: Path to the cdb.exe executable.
        @return: The resolved absolute path to cdb.exe.
        @raises DebuggerNotFoundError: If cdb.exe is not found or cannot be executed.
        """
        resolved_path = shutil.which(cdb_path)
        if resolved_path is None:
            raise DebuggerNotFoundError(
                f"'{cdb_path}' not found on PATH. "
                "Install 'Debugging Tools for Windows' and add it to PATH, "
                "or provide the full path via --cdb-path."
            )

        try:
            subprocess.run(
                [resolved_path, "-?"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (PermissionError, OSError) as e:
            is_store = "WindowsApps" in resolved_path
            msg = f"cdb.exe found at '{resolved_path}' but execution failed: {e}\n"
            if is_store:
                msg += (
                    "This is the WinDbg Preview version from Microsoft Store, which "
                    "cannot be executed from this environment.\n"
                )
            msg += (
                "Please install the standalone 'Debugging Tools for Windows' from the "
                "Windows SDK and ensure its path is first in your PATH or provided "
                "via --cdb-path."
            )
            raise DebuggerNotFoundError(msg)

        return resolved_path

    def check_environment(self, cdb_path: str = "cdb.exe") -> bool:
        """
        Verify the system is ready for debugging.

        @param cdb_path: Path to the cdb.exe executable.
        @return: True if the environment is ready, False otherwise.
        """
        logger = logging.getLogger(__name__)
        try:
            self._check_cdb(cdb_path)
        except DebuggerNotFoundError as e:
            logger.error(e)
            return False

        # check for keys
        if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            logger.warning("No AI API keys found. Analysis will be skipped.")
        return True

    def _handle_config(self) -> Any:
        """
        Handle application configuration from CLI and config files.

        @return: The parsed argparse.Namespace object containing application arguments.
        """
        # Pre-parse to check for config-file or save-config
        temp_args, _ = self.parser.parse_known_args()

        if temp_args.config_file:
            config_path = temp_args.config_file
            if os.path.isfile(config_path):
                config_data = read_config(config_path)
                self._apply_config(config_data)
                # Re-parse to get the values, ignoring other CLI arguments as requested
                return self.parser.parse_args(["--config-file", config_path] + ([config_data.get("action")] if config_data.get("action") else []))
            else:
                self.parser.error(f"Config file not found: {config_path}")
        elif temp_args.save_config:
            self._save_app_config()
            sys.exit(0)
        else:
            # Normal CLI usage, but still check for default config file
            defaults_config = read_config()
            if defaults_config:
                # Do not apply the default 'action' from automatic config file,
                # as it might trigger an action the user didn't explicitly request.
                if "action" in defaults_config:
                    del defaults_config["action"]
                self._apply_config(defaults_config)
            return self.parser.parse_args()

    def _apply_config(self, config_data: dict) -> None:
        """
        Apply configuration data from a dictionary to the argument parsers.

        @param config_data: Dictionary containing configuration settings.
        """
        if "analyze" in config_data and isinstance(config_data["analyze"], dict) and self.analyze_parser:
            self.analyze_parser.set_defaults(**config_data["analyze"])
        if "export" in config_data and isinstance(config_data["export"], dict) and self.export_parser:
            self.export_parser.set_defaults(**config_data["export"])
        
        global_defaults = {k: v for k, v in config_data.items() if k not in ["analyze", "export"]}
        self.parser.set_defaults(**global_defaults)
        
        # Also apply global defaults to subparsers if they are not specifically configured
        if self.analyze_parser and "analyze" not in config_data:
            self.analyze_parser.set_defaults(**global_defaults)
        if self.export_parser and "export" not in config_data:
            self.export_parser.set_defaults(**global_defaults)

    def _save_app_config(self) -> None:
        """
        Save the current application configuration to the default config file.
        """
        args = self.parser.parse_args()
        new_config = {
            "report_severity": getattr(args, "report_severity", "INFO"),
            "action": args.action,
        }
        
        if args.action == "analyze":
            analyze_keys = [
                "dump", "sym", "log_source", "engine", "ai", 
                "cdb_path", "analyze_history", "store", "store_config", "assumption"
            ]
            new_config["analyze"] = {k: getattr(args, k, None) for k in analyze_keys}
        elif args.action == "export":
            export_keys = [
                "store", "store_config", "to_store", "to_store_config"
            ]
            new_config["export"] = {k: getattr(args, k, None) for k in export_keys}
        
        save_config(new_config)
        console.print(Panel(
            f"Config file `{CONFIG_DEFAULT_PATH}` has been created successfully.\n"
            "It will override command-line default values.\n"
            "Now you may remove unnecessary options from it, and leave the config with some meaningful defaults",
            title="Config Created",
            style="green"
        ))

    def _finalize_config(self) -> None:
        """
        Set default storage paths if they were not provided via CLI or config.
        """
        if self.args.store_config is None:
            self.args.store_config = self._get_default_store_path(self.args.store, "analysis_output")

        if self.args.action == "export":
            if getattr(self.args, "to_store_config", None) is None:
                self.args.to_store_config = self._get_default_store_path(self.args.to_store, "exported_output")

    def _get_default_store_path(self, store_type: str, basename: str) -> str:
        """
        Generate a default path for the storage backend.

        @param store_type: The type of storage backend.
        @param basename: The base name for the storage location.
        @return: The generated default path string.
        """
        if store_type == "filesystem":
            return os.path.join(os.getcwd(), basename)
        elif store_type == "sqlite":
            return os.path.join(os.getcwd(), f"{basename}.sqlite")
        return ""

    def handle_analyze(self) -> None:
        """
        Handle the 'analyze' action.
        Verifies required arguments and invokes the analysis pipeline.
        """
        if not self.args.dump:
            if self.analyze_parser:
                self.analyze_parser.error("--dump is required for 'analyze' action.")
            else:
                print("Error: --dump is required for 'analyze' action.")
                sys.exit(1)
        
        resolved_cdb = self._check_cdb(self.args.cdb_path)
        run_analyze(self.args, resolved_cdb)

    def handle_export(self) -> None:
        """
        Handle the 'export' action.
        Invokes the export process to migrate records between backends.
        """
        run_export(self.args)

    def run(self) -> None:
        """
        Run the main application logic.
        """
        self.setup_logging()
        self.args = self._handle_config()

        if not self.args.action:
            self.parser.print_help()
            sys.exit(0)

        self.setup_logging(self.args.report_severity)
        self._finalize_config()

        actor = self.actors.get(self.args.action)
        if actor:
            actor()
