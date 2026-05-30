# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

All design, planning, and analysis documents are indexed in **[docs/README.md](docs/README.md)**.

## Project Overview

**Aegis SWR** (Synthetic War Room) is a cross-platform (in future) crash dump forensics platform. 

The prototype (`/prototype`) automates extraction of crash data from `.dmp` files and uses LLMs to generate Root Cause Analysis (RCA) reports. It supports both a CLI and a PySide6 GUI.

**System requirements** (for current Windows-only version): Windows 10/11 x64 *(, Python 3.10+, Debugging Tools for Windows (`cdb.exe` in PATH).

## Commands

All commands run from the `prototype/` directory.

```powershell
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/

# Run a single test file
uv run pytest tests/test_orchestrator.py

# Run CLI analysis
python -m wincrash_analyzer.cli analyze --dump <path.dmp> --sym <symbols_dir> --engine cdb --ai gemini

# Launch GUI
python -m wincrash_analyzer.gui.app
```

**Environment variables** needed for AI backends:
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

## Architecture

The application uses a **Factory-Strategy pattern** for all backend types. Every backend type has: an abstract base class, concrete implementations, and a factory function. The `Orchestrator` (`core/orchestrator.py`) wires them together.

### Pipeline

`INITIALIZING → EXTRACTING → PARSING → ANALYZING → STORING`

The orchestrator checks storage for an existing report (by dump hash) before invoking AI — cache hits skip the LLM call entirely.

### Backend Types

Each backend family lives under `backends/`:

- **Debug backends** (`backends/debug/`): Extract crash data from `.dmp` files.
  - `cdb.py` — wraps `cdb.exe` subprocess, runs `.reload /f /i` and `!analyze -v`
  - `js_provider.py` — loads a JavaScript diagnostic script into WinDbg, queries the Debugger Data Model, communicates back via a local HTTP bridge (`windbg_server.py`)

- **AI backends** (`backends/ai/`): Generate RCA from crash context.
  - `gemini.py` — Google Generative AI (large context, good for multi-thread analysis)
  - `openai.py` — OpenAI GPT (precise RIP deduction)

- **Storage backends** (`backends/store/`): Persist `CrashReportEntity` records.
  - `filesystem.py` — JSON files for rapid inspection
  - `sqlite.py` — SQLite for cross-dump trend analysis

### Universal Data Schema

All backends communicate via `CrashReportEntity` (TypedDict in `core/data_schema.py`). Key fields: `report_id` (UUID4), `exception_code`, `faulting_module`, `raw_stack`, `ai_analysis`, `engine_type`, `ai_model`, `dump_hash`.

### Configuration

`config/app_config.py` defines a single `ConfigOption` schema that drives both CLI (argparse) and GUI (PySide6 dynamic form generation). Config persists to `~/.crash_analyzer_config.json`.

### GUI

`gui/` uses PySide6. Long-running backend operations run in `gui/worker.py` (threading helper). The config form in `gui/widgets/config_form.py` is generated dynamically from `ConfigOption`.

## Key Conventions

- **RAII via context managers**: subprocess and socket resources are always managed with `with` blocks.
- **SensitiveFilter**: applied to all loggers to redact API keys from log output.
- **`SourceCollection`** (`core/data_sources.py`): container passed through the pipeline that holds the dump, symbol path, and optional log source.
- **Actions** (`actions/`): thin CLI action handlers that assemble sources and backends then call the orchestrator — keep business logic out of these.
