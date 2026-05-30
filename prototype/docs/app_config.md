# Application Configuration Schema Decision

This document describes the architectural decision for implementing a centralized configuration schema for the WinCrash AI Analyzer.

## Rationale
To support both CLI and future GUI interfaces, it is essential to have a single source of truth for all configuration options. This schema defines option IDs, types, default values, help strings, and human-readable names for both settings and their possible choices.

## Schema Definition

The schema is implemented in `wincrash_analyzer/config/app_config.py` using the `ConfigOption` dataclass.

### ConfigOption Properties
- `id`: The internal identifier used in code (e.g., `report_severity`).
- `type`: The data type of the option (e.g., `str`, `bool`).
- `readable_name`: A user-friendly name for the setting (e.g., "Report Severity").
- `help`: Detailed help text describing the purpose of the option.
- `default`: The default value if not specified.
- `options`: A dictionary mapping internal values to user-friendly names (e.g., `{"gemini": "Google Gemini"}`).

### Helper Properties/Methods
- `choices`: Returns the internal keys from `options` for use in CLI `choices`.
- `cli_name`: Returns the CLI-style argument name (e.g., `--report-severity`).

## Usage

### In CLI (`wincrash_analyzer/cli.py`)
The `create_parser` function now uses `get_option(id)` to retrieve `ConfigOption` objects and build the `argparse` parser. This ensures that help messages, choices, and defaults are consistent between the CLI and any other interface.

### In GUI
The GUI iterates over `APP_CONFIG_SCHEMA` to dynamically generate configuration forms. It uses `readable_name` for labels, `options` for dropdown menus (using the user-friendly values), and `help` for tooltips.
This is implemented in `wincrash_analyzer/gui/widgets/config_form.py`.

## Schema Elements

Currently defined options include:
- `report_severity`: DEBUG, INFO, WARNING, ERROR.
- `dump`: Path to the .dmp file.
- `sym`: Symbol path.
- `log_source`: Path to application logs.
- `engine`: cdb, js.
- `ai`: gemini, openai.
- `cdb_path`: Path to cdb.exe.
- `analyze_history`: Boolean flag.
- `store`: filesystem, sqlite.
- `store_config`: Store destination.
- `to_store`: Destination storage backend (for export).
- `to_store_config`: Destination store configuration (for export).
- `assumption`: Optional user-provided assumption or theory to guide AI analysis.

## Maintenance
When adding new configuration options or choices, they MUST be added to the `APP_CONFIG_SCHEMA` in `wincrash_analyzer/config/app_config.py`. All parts of the application should refer to this schema for configuration-related metadata.
