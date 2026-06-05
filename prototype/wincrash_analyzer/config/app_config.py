import json
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional, Dict

HOME_DIR = os.path.expanduser("~")
CONFIG_DEFAULT_PATH = os.path.join(HOME_DIR, '.crash_analyzer_config.json')


@dataclass
class ConfigOption:
    id: str  # internal identifier, e.g., "report_severity"
    type: str  # "str", "bool", "int", etc.
    readable_name: str  # user-friendly name, e.g., "Report Severity"
    help: str  # help text for CLI and GUI
    default: Any = None
    options: Optional[Dict[str, str]] = None  # Mapping of internal value -> user-friendly value

    @property
    def choices(self) -> Optional[List[str]]:
        """Returns the keys of options if present, which can be used for CLI choices"""
        if self.options:
            return list(self.options.keys())
        return None

    @property
    def cli_name(self) -> str:
        """Returns the CLI-style name, e.g., "--report-severity"""
        return "--" + self.id.replace("_", "-")


APP_CONFIG_SCHEMA = [
    ConfigOption(
        id="report_severity",
        type="str",
        readable_name="Report Severity",
        default="INFO",
        options={
            "DEBUG": "Debug",
            "INFO": "Info",
            "WARNING": "Warning",
            "ERROR": "Error"
        },
        help="Verbosity of console output and reporting (default: INFO)"
    ),
    ConfigOption(
        id="dump",
        type="str",
        readable_name="Dump Path",
        help="Path to the .dmp file (must have .dmp extension)"
    ),
    ConfigOption(
        id="sym",
        type="str",
        readable_name="Symbol Path",
        help="Symbol path"
    ),
    ConfigOption(
        id="log_source",
        type="str",
        readable_name="Log Source",
        help="Path to a log file or directory containing application logs"
    ),
    ConfigOption(
        id="engine",
        type="str",
        readable_name="Debug Engine",
        default="cdb",
        options={
            "cdb": "CDB (Console Debugger)",
            "js": "JavaScript Engine"
        },
        help="Debug engine (default: cdb)"
    ),
    ConfigOption(
        id="ai",
        type="str",
        readable_name="AI Backend",
        default="gemini",
        options={
            "gemini": "Google Gemini",
            "openai": "OpenAI"
        },
        help="AI backend (default: gemini)"
    ),
    ConfigOption(
        id="cdb_path",
        type="str",
        readable_name="CDB Path",
        default="cdb.exe",
        help="Path to cdb.exe (default: searches PATH)"
    ),
    ConfigOption(
        id="analyze_history",
        type="bool",
        readable_name="Analyze History",
        default=False,
        help="Analyze history of crashes before submitting conclusion"
    ),
    ConfigOption(
        id="store",
        type="str",
        readable_name="Storage Backend",
        default="filesystem",
        options={
            "filesystem": "File System",
            "sqlite": "SQLite Database"
        },
        help="Storage backend (default: filesystem)"
    ),
    ConfigOption(
        id="store_config",
        type="str",
        readable_name="Storage Configuration",
        help="Store destination"
    ),
    ConfigOption(
        id="to_store",
        type="str",
        readable_name="Destination Storage Backend",
        options={
            "filesystem": "File System",
            "sqlite": "SQLite Database"
        },
        help="Destination storage backend"
    ),
    ConfigOption(
        id="to_store_config",
        type="str",
        readable_name="Destination Storage Configuration",
        help="Destination store configuration"
    ),
    ConfigOption(
        id="assumption",
        type="str",
        readable_name="Assumption",
        help="Additional context or assumptions to be considered by the AI during analysis"
    ),
]


def get_option(option_id: str) -> Optional[ConfigOption]:
    """Helper to get a ConfigOption by its id"""
    for opt in APP_CONFIG_SCHEMA:
        if opt.id == option_id:
            return opt
    return None


def read_config(config_file: str = None) -> dict:
    """
    Read the application configuration from a JSON file.

    Config is a JSON file normally located in the users' $HOME directory,
    and overwrites defaults for the application.

    @param config_file: Absolute path to the config file.
    @return: A dictionary containing the configuration.
    """
    if config_file is None:
        config_file = CONFIG_DEFAULT_PATH
    if not os.path.isfile(config_file):
        return {}
    # read JSON file
    with open(config_file, 'r') as f:
        config = json.load(f)
    return config


def save_config(config: dict, config_file: str = None):
    """
    Save the given configuration to a file.

    @param config: Dictionary containing the configuration to save.
    @param config_file: Absolute path to the destination config file.
    """
    if config_file is None:
        config_file = CONFIG_DEFAULT_PATH
    with open(config_file, 'w+', encoding='utf8') as outfile:
        outfile.write(json.dumps(config, indent=2, sort_keys=True, ensure_ascii=False))
